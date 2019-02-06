import configparser
import os
import sys

from jinja2 import Environment, FileSystemLoader

from django.conf import settings
from django.http import Http404
from django.contrib.sites.models import Site

from base.models import Resource
from transfer_app.models import Transfer, TransferCoordinator
import transfer_app.launchers as _launchers

sys.path.append(os.path.realpath('helpers'))
from helpers.email_utils import send_email


def post_completion(transfer_coordinator, originator_emails):
    '''
    transfer_coordinator is a TransferCoordinator instance
    originator_emails is a list of email addresses for the originator(s) of
      the transfers
    '''

    all_transfers = Transfer.objects.filter(coordinator = transfer_coordinator)
    failed_transfers = []
    for t in all_transfers:
        if not t.success:
            resource = t.resource
            failed_transfers.append(resource.name)

    if settings.EMAIL_ENABLED:
        current_site = Site.objects.get_current()
        domain = current_site.domain
    
        template_dir = os.path.join(settings.MAIN_TEMPLATE_DIR, 'transfer_app') 

        email_subject = open(os.path.join( template_dir, 
            'transfer_complete_subject.txt')
        ).read().strip()

        # get the templates and fill them out:
        env = Environment(loader=FileSystemLoader(template_dir))
        plaintext_template = env.get_template('transfer_complete_message.txt')
        html_template = env.get_template('transfer_complete_message.html')

        params = {'domain': domain, 'failed_transfers': failed_transfers}
        plaintext_msg = plaintext_template.render(params)
        html_msg = html_template.render(params)
    
        for email in originator_emails:
            send_email(plaintext_msg, html_msg, email, email_subject)


def get_or_create_upload_location(user):
    '''
    user is an instance of User
    TODO: write this
    '''
    return 'users-bucket'
