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

        params = {'domain': domain}
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


def create_resource(serializer, user):
    '''
    This function is used to get around making API calls
    between different endpoints.  Namely, when a user requests
    the "upload" endpoint, we have to create Resource objects.
    To keep Resource creation in a central location, we extracted the logic
    out of the API view and put it here.  Then, any API endpoint needing to
    create one or more Resource instances can use this function instead of
    having to call the endpoint for creating a Resource.

    serializer is an instance of rest_framework.serializers.ModelSerializer
    user is a basic Django User (or subclass)
    '''
    serializer.is_valid(raise_exception=True)

    # if the user is NOT staff, we only let them
    # create a Resource for themself.
    if not user.is_staff:
        # if the owner specified in the request is the requesting user
        # then we approve
        try:
            many = serializer.many
        except AttributeError as ex:
            many = False
        if many:
            owner_status = []
            for item in serializer.validated_data:
                try:
                    properly_owned = item['owner'] == user
                    owner_status.append(properly_owned)
                except KeyError as ex:
                    item['owner'] = user
                    owner_status.append(True)
            if all(owner_status):
                return serializer.save()
            else:
                raise exceptions.RequestError('Tried to create a Resource attributed to someone else.')  
        else:
            try:
                if serializer.validated_data['owner'] == user:
                    return serializer.save()
                # here we block any effort to create a Resource for anyone else.
                #Raise 404 so we do not give anything away
                else:
                    raise Http404
            except KeyError as ex:
                return serializer.save(owner=user)

    # Otherwsie (if the user IS staff), we trust them to create
    # Resources for themselves or others.
    else:
        return serializer.save()

