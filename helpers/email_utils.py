import os
import json
import base64

from django.conf import settings
from django.contrib.auth import get_user_model

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr

from googleapiclient import discovery
from google.oauth2.credentials import Credentials


def notify_admins(message, subject):
    admin_users = get_user_model().objects.filter(is_staff=True)
    for u in admin_users:
        send_email(message, message, u.email, subject)

def send_email(plaintext_msg, message_html, recipient, subject):

    j = json.load(open(settings.EMAIL_CREDENTIALS_FILE))
    credentials = Credentials(j['token'],
                      refresh_token=j['refresh_token'], 
                      token_uri=j['token_uri'], 
                      client_id=j['client_id'], 
                      client_secret=j['client_secret'], 
                      scopes=j['scopes'])

    service = discovery.build('gmail', 'v1', credentials = credentials)

    sender = '---'
    message = MIMEMultipart('alternative')

    # create the plaintext portion
    part1 = MIMEText(plaintext_msg, 'plain')

    # create the html:
    part2 = MIMEText(message_html, 'html')

    message.attach(part1)
    message.attach(part2)

    message['To'] = recipient
    message['From'] = formataddr((str(Header('my app', 'utf-8')), sender))
    message['subject'] = subject
    msg = {'raw': base64.urlsafe_b64encode(message.as_string().encode()).decode()}
    sent_message = service.users().messages().send(userId='me', body=msg).execute()
