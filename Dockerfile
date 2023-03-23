FROM python:3.9.0-slim

COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . ./MailServer

CMD ["python", "./MailServer/consumer_mail.py"]