import configparser
import os
import sys
import datetime

from jinja2 import Environment, FileSystemLoader

from django.conf import settings
from django.http import Http404
from django.contrib.sites.models import Site

from base.models import Resource
from transfer_app.models import Transfer, TransferCoordinator
import transfer_app.launchers as _launchers

sys.path.append(os.path.realpath('helpers'))
from helpers.email_utils import send_email


def check_for_transfer_availability(config):
    '''
    This function checks whether new downloads are allowed giving our maximum allowable transfers
    '''
    
    nmax = int(config['max_transfers'])
    while True:
        # get all the incomplete TransferCoordinator instances.  
        incomplete_tc = TransferCoordinator.objects.filter(completed=False)

        all_transfers = []
        for tc in incomplete_tc:
            all_transfers.extend([x for x in Transfer.objects.filter(coordinator = tc)])

        # at this point we have a list of Transfer instances that are either queued, started, or completed
        # count how many of those have started but not completed
        currently_running_count = sum([all([x.started, not x.completed]) for x in all_transfers])

        if (nmax - currently_running_count) > 0:
            return
        else:
            time.sleep(int(config['sleep_period']))


def handle_launch_problems(failed_pks, launch_count):
    '''
    This function wraps common behavior for actions to take if one of the transfers did not launch 
    properly.
    '''
    # for those that instantly failed, mark them complete:
    tc_set = []
    for transfer_pk in failed_pks:
        transfer_obj = Transfer.objects.get(pk=transfer_pk)
        tc_set.append(transfer_obj.coordinator) # all the Transfers should have the same coordinator, but let's keep it general
        transfer_obj.completed = True
        transfer_obj.success = False
        tz = transfer_obj.start_time.tzinfo
        now = datetime.datetime.now(tz)
        duration = now - transfer_obj.start_time
        transfer_obj.duration = duration
        transfer_obj.finish_time = now
        transfer_obj.save()

    tc_set_pks = set([x.pk for x in tc_set])
    if launch_count == 0:
        for tc_pk in tc_set_pks:
            tc = TransferCoordinator.objects.get(pk=tc_pk)
            all_transfers = Transfer.objects.filter(coordinator = tc)
            all_originators = list(set([x.originator.email for x in all_transfers]))
            post_completion(tc, all_originators)


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
