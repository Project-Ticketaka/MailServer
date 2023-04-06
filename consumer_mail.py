import base64
import json
import os
import smtplib
from email.mime.image import MIMEImage

import qrcode
import logging
from io import BytesIO
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Environment, PackageLoader, select_autoescape
from pika import BlockingConnection
from pika import PlainCredentials
from pika import ConnectionParameters

logging.addLevelName(15, "DATA")
logging.DATA = 15

logger = logging.getLogger("mail")
logger.setLevel("DATA")
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

env = Environment(
    loader=PackageLoader('consumer_mail', 'templates'),
    autoescape=select_autoescape(['html', 'xml'])
)

html_template = 'ticket.html'
title = "[Ticketaka] 예약 정보 발송해 드립니다."

mail_server = os.environ['MAIL_SERVER']
mail_port = int(os.environ['MAIL_PORT'])
mail_user = os.environ['MAIL_USERNAME']
mail_password = os.environ['MAIL_PASSWORD']

rabbitmq_host = os.environ['RABBITMQ_HOST']
rabbitmq_port = int(os.environ['RABBITMQ_PORT'])
rabbitmq_id = os.environ['RABBITMQ_ID']
rabbitmq_password = os.environ['RABBITMQ_PASSWORD']
rabbitmq_cred = PlainCredentials(rabbitmq_id, rabbitmq_password)

server = smtplib.SMTP_SSL(mail_server, mail_port)
server.login(mail_user, mail_password)


def make(sender, receiver, content):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = title
    msg['From'] = sender
    msg['To'] = receiver
    html = MIMEText(content, 'html')
    msg.attach(html)

    assert os.path.isfile("./qrcode.png"), 'image file does not exist.'
    with open("./qrcode.png", 'rb') as img_file:
        mime_img = MIMEImage(img_file.read())
        mime_img.add_header('Content-ID', '<' + 'qrcode' + '>')
    msg.attach(mime_img)

    return msg


def template(data):
    t = env.get_template(html_template)
    return t.render(data=data)


def send(receiver, data):
    html_message = template(data)
    body = make(mail_user, receiver, html_message)
    server.send_message(body)
    logger.info("[SUCCESS SEND MAIL]")


def make_qr(reservation_id):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=0,
        image_factory=None,
    )
    buffered = BytesIO()

    qr.add_data("reservation_id: " + str(reservation_id))
    qr.make(fit=True)
    qr_img = qr.make_image()
    qr_img.save("./qrcode.png")


def on_message(to_channel, method_frame, header_frame, body):
    body = body.decode()
    data = json.loads(body)
    make_qr(data['reservationId'])

    logger.log(logging.DATA, data)
    send(data['memberEmail'], data)
    to_channel.basic_ack(delivery_tag=method_frame.delivery_tag)


if __name__ == '__main__':
    connection = BlockingConnection(
        ConnectionParameters(host=rabbitmq_host, port=rabbitmq_port, credentials=rabbitmq_cred)
    )
    channel = connection.channel()

    argument = {
        "x-queue-type": "quorum"
    }

    channel.basic_consume(queue='mail.queue', on_message_callback=on_message, arguments=argument)

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        server.quit()
        channel.stop_consuming()
    except StopIteration:
        server.quit()
        channel.stop_consuming()
