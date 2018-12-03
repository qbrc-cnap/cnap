"""
For downloads, the front end will send a list of Resource PKs which are cached
while the client does the oauth2 flow.  Once the oauth2 flow is complete, the backend
will have an access token.  The resource pk and the access token are then sent 
(With other params) to a worker VM

"""
import os
import hashlib
import httplib2
import urllib
import json
import datetime
import copy

from django.conf import settings
from django.shortcuts import render
from django.http import HttpResponseRedirect, HttpResponse, JsonResponse
from django.urls import reverse
from django.contrib.sites.models import Site
from django.contrib.auth import get_user_model
from rest_framework.exceptions import MethodNotAllowed

import dropbox.dropbox as dropbox_module
import google.oauth2.credentials as google_credentials_module
from googleapiclient.discovery import build

import helpers.utils as utils
from transfer_app.base import GoogleBase, AWSBase
from transfer_app import tasks as transfer_tasks
import transfer_app.exceptions as exceptions
from base.models import Resource
from transfer_app.models import Transfer, TransferCoordinator


class Downloader(object):

    @classmethod
    def get_config(cls, config_filepath):
        return utils.load_config(config_filepath, cls.config_keys)

    @classmethod
    def _check_format(cls, download_info, user_pk):

        # if we receive a single transfer, it might not be in a list
        if (type(download_info) is int) or (type(download_info) is str):
            download_info = [download_info,]
        
        # check that we have list of ints
        try:
            download_info = [int(x) for x in download_info]
        except ValueError as ex:
            raise exceptions.ExceptionWithMessage('''
                The request payload must only contain 
                integers for identifying resources to transfer.
                Received: %s''' % download_info)

        # check that all of those Resources are owned by the requester.
        # if the requester is admin, can do anything
        # otherwise, if ANY of the resources are invalid, reject everything
        # This also catches the case where the user gives a primary that does not exist
        try:
            requesting_user = get_user_model().objects.get(pk=user_pk)
        except ObjectDoesNotExist as ex:
            raise exceptions.ExceptionWithMessage(ex)
        if not requesting_user.is_staff:
            all_user_resources = Resource.objects.user_resources(requesting_user)
            all_user_resource_pks = [x.pk for x in all_user_resources if x.is_active]
            if len(set(download_info).difference(set(all_user_resource_pks))) > 0:
                raise exceptions.ExceptionWithMessage('''
                    Requesting to transfer a resource you do not own.                
                ''')    
        reformatted_info = []
        for pk in download_info:
            d = {}
            d['resource_pk'] = pk
            d['originator'] = user_pk
            d['destination'] = cls.destination
            reformatted_info.append(d)
        if len(reformatted_info) > 0:
            return reformatted_info
        else:
            raise exceptions.ExceptionWithMessage('''
               There were no valid resources to download.                
            ''')   

    def __init__(self, download_data):
        self.download_data = download_data

    def _transfer_setup(self):
        '''
        This creates the proper database instances for the downloads- it creates
        the proper Transfer and TransferCoordinator instances

        This function expects that self.upload_data is a list and each
        item in the list is a dict.  Each dict NEEDS to have certain keys (see code)

        '''
        if len(self.download_data) > 0:
            tc = TransferCoordinator()
            tc.save()
        else:
            return

        for item in self.download_data:
            originator = get_user_model().objects.get(pk=item['originator'])
            resource = Resource.objects.get(pk=item['resource_pk'])

            # we obviously need the path where the resource is:
            item['path'] = resource.path

            # since the resource instance has a size field, add that to our dict so we 
            # know how large to size the transfer VM
            item['size_in_bytes'] = resource.size

            t = Transfer(
                 download=True,
                 resource=resource,
                 destination=item['destination'],
                 coordinator=tc,
                 originator = originator
            )
            t.save()

            # finally add the transfer primary key to the dictionary so we will
            # be able to track the transfers
            item['transfer_pk'] = t.pk


class DropboxDownloader(Downloader):

    destination = settings.DROPBOX
    config_keys = ['dropbox',]
    
    @classmethod
    def check_format(cls, download_info, user_pk):
        return super()._check_format(download_info, user_pk)

    @classmethod
    def authenticate(cls, config_filepath, request):
        #config_params = super().get_config(config_filepath)

        code_request_uri = settings.CONFIG_PARAMS['dropbox_auth_endpoint']
        response_type = 'code'

        # for validating that we're not being spoofed
        state = hashlib.sha256(os.urandom(1024)).hexdigest()
        request.session['session_state'] = state

        # construct the callback URL for Dropbox to use:
        current_site = Site.objects.get_current()
        domain = current_site.domain
        code_callback_url = 'https://%s%s' % (domain, settings.CONFIG_PARAMS['dropbox_callback'])
        url = "{code_request_uri}?response_type={response_type}&client_id={client_id}&redirect_uri={redirect_uri}&force_reauthentication=true&state={state}".format(
            code_request_uri = code_request_uri,
            response_type = response_type,
            client_id = settings.CONFIG_PARAMS['dropbox_client_id'],
            redirect_uri = code_callback_url,
            state = state
        )
        return HttpResponseRedirect(url)

    @classmethod
    def finish_authentication_and_start_download(cls, request):
        if request.method == 'GET':
            parser = httplib2.Http()
            if 'error' in request.GET or 'code' not in request.GET:
                raise exceptions.RequestError('There was an error on the callback')
            if request.GET['state'] != request.session['session_state']:
                raise exceptions.RequestError('There was an error on the callback-- state mismatch')
	
            current_site = Site.objects.get_current()
            domain = current_site.domain
            code_callback_url = 'https://%s%s' % (domain, settings.CONFIG_PARAMS['dropbox_callback'])
            params = urllib.parse.urlencode({
                'code':request.GET['code'],
                'redirect_uri':code_callback_url,
                'client_id':settings.CONFIG_PARAMS['dropbox_client_id'],
                'client_secret':settings.CONFIG_PARAMS['dropbox_secret'],
                'grant_type':'authorization_code'
            })
            headers={'content-type':'application/x-www-form-urlencoded'}
            resp, content = parser.request(settings.CONFIG_PARAMS['dropbox_token_endpoint'], method = 'POST', body = params, headers = headers)
            c = json.loads(content.decode('utf-8'))
            try:
                access_token = c['access_token']
            except KeyError as ex:
                raise exceptions.ExceptionWithMessage('''
                    The response did not have the "access_token" key, so the OAuth2 flow did not succeed.
                    The response body was %s
                ''' % c)
            try:
                download_info = request.session['download_info']
            except KeyError as ex:
                raise exceptions.ExceptionWithMessage('There was no download_info registered with the session')

            # need to check that the user has enough space in their Dropbox account
            dbx = dropbox_module.Dropbox(access_token)
            space_usage = dbx.users_get_space_usage()
            if space_usage.allocation.is_team():
                used_in_bytes = space_usage.allocation.get_team().used
                space_allocation_in_bytes = space_usage.allocation.get_team().allocated
                space_remaining_in_bytes = space_allocation_in_bytes - used_in_bytes
            else:
                used_in_bytes = space_usage.used
                space_allocation_in_bytes = space_usage.allocation.get_individual().allocated
                space_remaining_in_bytes = space_allocation_in_bytes - used_in_bytes

            running_total = 0
            at_least_one_transfer = False

            # iterate through the transfers, add the token, and check a running total
            # note that we do not do any optimization to maximize the number of transfers
            # in the case that the space is not sufficient for all files.
            passing_items = []
            failed_items = []
            problem = False
            for item in download_info:
                size_in_bytes = Resource.objects.get(pk=item['resource_pk']).size
                running_total += size_in_bytes
                if running_total < space_remaining_in_bytes:
                    item['access_token'] = access_token
                    passing_items.append(item)
                else:
                    problem = True
                    failed_items.append(item)

            at_least_one_transfer = len(passing_items) > 0
            if not problem:
                # call async method:
                transfer_tasks.download.delay(passing_items, request.session['download_destination'])
                context = {'email_enabled': settings.EMAIL_ENABLED, 
                    'problem': problem, 
                    'at_least_one_transfer':at_least_one_transfer
                }
                return render(request, 'transfer_app/download_started.html', context)
            else:
                # if there was a problem-- could not fit all files
                # Still initiate the good transfers
                if len(passing_items) > 0:
                    transfer_tasks.download.delay(passing_items, request.session['download_destination'])
                warning_list = []
                for item in failed_items:
                    resource_name = Resource.objects.get(pk=item['resource_pk']).name
                    warning_list.append('Not enough space in your Dropbox for file %s' % resource_name)
                context = {
                    'email_enabled': settings.EMAIL_ENABLED,
                    'problem': problem,
                    'at_least_one_transfer':at_least_one_transfer,
                    'warnings': warning_list
                }
                return render(request, 'transfer_app/download_started.html', context)
        else:
            raise MethodNotAllowed('Method not allowed.')

    def _transfer_setup(self):
        '''
        about
        '''
        return super()._transfer_setup()


class DriveDownloader(Downloader):

    config_keys = ['google_drive',]
    destination = settings.GOOGLE_DRIVE

    @classmethod
    def check_format(cls, download_info, user_pk):
        return super()._check_format(download_info, user_pk)

    @classmethod
    def authenticate(cls, config_filepath, request):
        #config_params = super().get_config(config_filepath)

        code_request_uri = settings.CONFIG_PARAMS['drive_auth_endpoint']
        response_type = 'code'
        scope = settings.CONFIG_PARAMS['drive_scope']

        # for validating that we're not being spoofed
        state = hashlib.sha256(os.urandom(1024)).hexdigest()
        request.session['session_state'] = state

        # construct the callback URL for Drive to use:
        current_site = Site.objects.get_current()
        domain = current_site.domain
        code_callback_url = 'https://%s%s' % (domain, settings.CONFIG_PARAMS['drive_callback'])
        url = "{code_request_uri}?response_type={response_type}&client_id={client_id}&redirect_uri={redirect_uri}&scope={scope}&state={state}".format(
            code_request_uri = code_request_uri,
            response_type = response_type,
            client_id = settings.CONFIG_PARAMS['drive_client_id'],
            redirect_uri = code_callback_url,
            scope = scope,
            state = state
        )
        return HttpResponseRedirect(url)

    @classmethod
    def finish_authentication_and_start_download(cls, request):
        if request.method == 'GET':
            parser = httplib2.Http()
            if 'error' in request.GET or 'code' not in request.GET:
                raise exceptions.RequestError('There was an error on the callback')
            if request.GET['state'] != request.session['session_state']:
                raise exceptions.RequestError('There was an error on the callback-- state mismatch')
	
            current_site = Site.objects.get_current()
            domain = current_site.domain
            code_callback_url = 'https://%s%s' % (domain, settings.CONFIG_PARAMS['drive_callback'])
            params = urllib.parse.urlencode({
                'code':request.GET['code'],
                'redirect_uri':code_callback_url,
                'client_id':settings.CONFIG_PARAMS['drive_client_id'],
                'client_secret':settings.CONFIG_PARAMS['drive_secret'],
                'grant_type':'authorization_code'
            })
            headers={'content-type':'application/x-www-form-urlencoded'}
            resp, content = parser.request(settings.CONFIG_PARAMS['drive_token_endpoint'], method = 'POST', body = params, headers = headers)
            c = json.loads(content.decode('utf-8'))
            try:
                access_token = c['access_token']
            except KeyError as ex:
                raise exceptions.ExceptionWithMessage('''
                    The response did not have the "access_token" key, so the OAuth2 flow did not succeed.
                    The response body was %s
                ''' % c)
            try:
                download_info = request.session['download_info']
            except KeyError as ex:
                raise exceptions.ExceptionWithMessage('There was no download_info registered with the session')

            # ensure we have enough space to push the file(s):
            credentials = google_credentials_module.Credentials(access_token)
            drive_service = build('drive', 'v3', credentials=credentials)
            about = drive_service.about().get(fields='storageQuota').execute()
            try:
                total_bytes = int(about['storageQuota']['limit'])
                unlimited = False
            except KeyError as ex:
                # per the docs, if the 'limit' field is not there, there is "unlimited" storage
                unlimited = True
            used_bytes = int(about['storageQuota']['usage'])
            if not unlimited:
                space_remaining_in_bytes = total_bytes - used_bytes

            running_total = 0
            at_least_one_transfer = False
            failed_items = []
            passing_items = []
            problem = False

            if not unlimited:
                # iterate through the transfers, add the token, and check a running total
                # note that we do not do any optimization to maximize the number of transfers
                # in the case that the space is not sufficient for all files.
                for item in download_info:
                    size_in_bytes = Resource.objects.get(pk=item['resource_pk']).size
                    running_total += size_in_bytes
                    if (running_total < space_remaining_in_bytes):
                        passing_items.append(item)
                    else:
                        problem = True
                        failed_items.append(item)
            else: # if unlimited storage, just 'pass' all the downloads through
                passing_items = download_info

            for item in passing_items:
                item['access_token'] = access_token

            at_least_one_transfer = len(passing_items) > 0
            if not problem:
                # call async method:
                transfer_tasks.download.delay(passing_items, request.session['download_destination'])
                context = {'email_enabled': settings.EMAIL_ENABLED, 
                    'problem': problem, 
                    'at_least_one_transfer':at_least_one_transfer
                }
                return render(request, 'transfer_app/download_started.html', context)
            else:
                # if there was a problem-- could not fit all files
                # Still initiate the good transfers
                if len(passing_items) > 0:
                    transfer_tasks.download.delay(passing_items, request.session['download_destination'])
                warning_list = []
                for item in failed_items:
                    resource_name = Resource.objects.get(pk=item['resource_pk']).name
                    warning_list.append('Not enough space in your Google Drive for file %s' % resource_name)
                context = {
                    'email_enabled': settings.EMAIL_ENABLED,
                    'problem': problem,
                    'at_least_one_transfer':at_least_one_transfer,
                    'warnings': warning_list
                }
                return render(request, 'transfer_app/download_started.html', context)
        else:
            raise MethodNotAllowed('Method not allowed.')


class EnvironmentSpecificDownloader(object):

    config_keys = []
    config_file = settings.DOWNLOADER_CONFIG['CONFIG_PATH']

    def __init__(self, download_data):
        #instantiate the wrapped classes:
        self.downloader = self.downloader_cls(download_data)
        self.launcher = self.launcher_cls()

        # get the config params for the downloader:
        downloader_cfg = self.downloader_cls.get_config(self.config_file)
        additional_cfg = utils.load_config(self.config_file, self.config_keys)
        downloader_cfg.update(additional_cfg)
        self.config_params = downloader_cfg

    @classmethod
    def authenticate(cls, request):
        return cls.downloader_cls.authenticate(cls.config_file, request)

    @classmethod
    def finish_authentication_and_start_download(cls, request):
        return cls.downloader_cls.finish_authentication_and_start_download(request)
    

    def download(self):
        transfer_coordinator = self.downloader._transfer_setup()
        self.config_and_start_downloads()


class GoogleEnvironmentDownloader(EnvironmentSpecificDownloader, GoogleBase):

    config_keys = []
    config_keys.extend(GoogleBase.config_keys)
    config_keys.extend(EnvironmentSpecificDownloader.config_keys)

    gcloud_cmd_template = '''{gcloud} beta compute --project={google_project_id} instances \
                             create-with-container {instance_name} \
                             --zone={google_zone} \
                             --scopes={scopes} \
                             --container-privileged \
                             --machine-type={machine_type} \
                             --boot-disk-size={disk_size_gb}GB \
                             --metadata=google-logging-enabled=true \
                             --container-image={docker_image} \
                             --no-restart-on-failure --container-restart-policy=never'''
    @classmethod
    def check_format(cls, download_info, user_pk):
        '''
        Check the download request for formatting issues, etc. that are Google-specific here
        More general issues, such as those related to the downloader itself can be handled via
        the parent

        This happens before any asynchronous download behavior, so this is a good place
        to check things like filename length, etc. that are specific to google 
        '''

        # first run the format check that is dependent on the downloader:
        # This returns a list of dicts
        download_info = cls.downloader_cls.check_format(download_info, user_pk)

        # Finally, check that the file is not already being transferred:
        download_info, error_messages = cls._check_conflicts(download_info)

        return download_info, error_messages

    @classmethod
    def _check_conflicts(cls, download_data):
        '''
        Here we check if any of the requested downloads have already been started.
        Each item in self.download_data has a key of 'destination'.  If any existing, INCOMPLETE
        transfers have the same destination, then we block it.
        '''

        # by design, each download can only be started by a single originator
        # Thus, it's ok to grab the first element of the list and know that 
        # each download has the same originator
        originator_pk = download_data[0]['originator']
        originator = get_user_model().objects.get(pk=originator_pk)

        # get all the incomplete transfers started by this user:
        all_incomplete_transfers = Transfer.objects.filter(completed=False, originator=originator)
        resource_pks_for_incomplete_transfers = [x.resource.pk for x in all_incomplete_transfers]

        new_transfers = []
        error_messages = []
        for item in download_data:
            # check if this resource is already being transferred:
            if item['resource_pk'] in resource_pks_for_incomplete_transfers:
                resource = Resource.objects.get(pk = item['resource_pk'])
                filename = os.path.basename(resource.path)
                msg = '''The file with name %s is already in progress.  
                        If you wish to overwrite, please wait until the download is complete and
                        try again, if available.''' % filename
                error_messages.append(msg)
            else:
                new_transfers.append(item)
        # reassign self.upload_data now that we have checked for existing transfers:
        return new_transfers, error_messages

    def __init__(self, download_data):
        super().__init__(download_data)

    def _prep_single_download(self, custom_config, index, item):

        disk_size_factor = float(custom_config['disk_size_factor'])
        min_disk_size = int(float(custom_config['min_disk_size']))

        # construct a callback so the worker can communicate back to the application server:
        callback_url = reverse('transfer-complete')
        current_site = Site.objects.get_current()
        domain = current_site.domain
        full_callback_url = 'https://%s%s' % (domain, callback_url)

        docker_image = custom_config['docker_image']

        instance_name = '%s-%s-%s' % (custom_config['instance_name_prefix'], \
            datetime.datetime.now().strftime('%m%d%y%H%M%S'), \
            index
        )

        # approx size in Gb so we can size the VM appropriately
        size_in_gb = item['size_in_bytes']/1e9
        target_disk_size = int(disk_size_factor*size_in_gb)
        if target_disk_size < min_disk_size:
            target_disk_size = min_disk_size

        # fill out the template command:
        cmd = self.gcloud_cmd_template.format(gcloud=os.environ['GCLOUD'],
            google_project_id = settings.CONFIG_PARAMS['google_project_id'],
            google_zone = settings.CONFIG_PARAMS['google_zone'],
            instance_name = instance_name,
            scopes = custom_config['scopes'],
            machine_type = custom_config['machine_type'],
            disk_size_gb = target_disk_size,
            docker_image = custom_config['docker_image']
        )

        # Since these are passed via the gcloud command, the arg strings are a bit strange
        # These should be common to all google-environment activity.  
        # Args specific to the particular downloader should be handled in the subclass
        cmd += ' --container-arg="-token" --container-arg="%s"' % settings.CONFIG_PARAMS['token']
        cmd += ' --container-arg="-key" --container-arg="%s"' % settings.CONFIG_PARAMS['enc_key']
        cmd += ' --container-arg="-pk" --container-arg="%s"' % item['transfer_pk']
        cmd += ' --container-arg="-url" --container-arg="%s"' % full_callback_url
        cmd += ' --container-arg="-path" --container-arg="%s"' % item['path']
        cmd += ' --container-arg="-proj" --container-arg="%s"' % settings.CONFIG_PARAMS['google_project_id']
        cmd += ' --container-arg="-zone" --container-arg="%s"' % settings.CONFIG_PARAMS['google_zone']
        return cmd

class AWSEnvironmentDownloader(EnvironmentSpecificDownloader, AWSBase):
    pass


class GoogleDropboxDownloader(GoogleEnvironmentDownloader):
    downloader_cls = DropboxDownloader
    config_keys = ['dropbox_in_google',]
    config_keys.extend(GoogleEnvironmentDownloader.config_keys)

    def __init__(self, download_data):
        super().__init__(download_data)

    def config_and_start_downloads(self):

        custom_config = copy.deepcopy(self.config_params)

        for i, item in enumerate(self.downloader.download_data):
            cmd = self._prep_single_download(custom_config, i, item)
            cmd += ' --container-arg="-dropbox" --container-arg="%s"' % item['access_token']
            cmd += ' --container-arg="-d" --container-arg="%s"' % custom_config['dropbox_destination_folderpath']
            self.launcher.go(cmd)


class GoogleDriveDownloader(GoogleEnvironmentDownloader):

    downloader_cls = DriveDownloader
    config_keys = ['drive_in_google',]
    config_keys.extend(GoogleEnvironmentDownloader.config_keys)

    def __init__(self, download_data):
        super().__init__(download_data)

    def config_and_start_downloads(self):
        custom_config = copy.deepcopy(self.config_params)
        for i, item in enumerate(self.downloader.download_data):

            cmd = self._prep_single_download(custom_config, i, item)
            cmd += ' --container-arg="-access_token" --container-arg="%s"' % item['access_token'] # the oauth2 access token
            self.launcher.go(cmd)


class AWSDropboxDownloader(AWSEnvironmentDownloader):
    downloader_cls = DropboxDownloader
    config_keys = ['dropbox_in_aws',]


class AWSDriveDownloader(AWSEnvironmentDownloader):
    downloader_cls = DriveDownloader
    config_keys = ['drive_in_aws',]


def get_downloader(destination):
    '''
    Based on the compute environment and the destination of the download
    choose the appropriate class to use.
    '''

    # This defines a two-level dictionary from which we can choose
    # a class.  Additional sub-classes of EnvironmentSpecificUploader
    # need to be in this if they are to be used.  Otherwise, the application
    # will 'not know' about the class
    class_mapping = {
        settings.GOOGLE : {
            settings.GOOGLE_DRIVE : GoogleDriveDownloader,
            settings.DROPBOX : GoogleDropboxDownloader,
        },
        settings.AWS : {
            settings.GOOGLE_DRIVE : AWSDriveDownloader,
            settings.DROPBOX : AWSDropboxDownloader,
        }
    }
    environment = settings.CONFIG_PARAMS['cloud_environment']
    try:
        return class_mapping[environment][destination]
    except KeyError as ex:
        raise exceptions.ExceptionWithMessage('''
            You did not specify an uploader implementation for:
                Compute environment: %s
                Download destination: %s
        ''' % (environment, destination))
