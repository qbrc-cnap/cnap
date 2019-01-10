import os
import datetime
import copy

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from django.contrib.sites.models import Site

from transfer_app.base import GoogleBase, AWSBase
import helpers.utils as utils

from base.models import Resource
from transfer_app.models import Transfer, TransferCoordinator
import transfer_app.serializers as serializers
import base.exceptions as exceptions
from transfer_app.launchers import GoogleLauncher, AWSLauncher

class Uploader(object):

    # these are keys required to be provided with the request.  Keys that are required regardless of
    # the upload source should be added to this list.  Those that are specific to a particular uploader
    # should be added to the child class under 'required_keys' class member
    required_keys = ['name', ]

    def __init__(self, upload_data):
        self.upload_data = upload_data

    @classmethod
    def get_config(cls, config_filepath):
        return utils.load_config(config_filepath, cls.config_keys)

    @classmethod
    def _validate_ownership(cls, data_dict, requesting_user):
        try:
            # if 'owner' was included in the object, check that the owner PK matches theirs
            # unless the request was issued by an admin
            intended_owner = data_dict['owner']
            if requesting_user.pk != intended_owner:
                if requesting_user.is_staff:
                    data_dict['originator'] = requesting_user.pk
                else:
                    raise exceptions.ExceptionWithMessage('''
                        Cannot assign ownership of an upload to someone other than yourself.''')
            else:
                data_dict['originator'] = data_dict['owner']
        except KeyError as ex:
            data_dict['owner'] = requesting_user.pk
            data_dict['originator'] = requesting_user.pk

    @classmethod
    def _check_keys(cls, data_dict):
        all_required_keys = list(set(Uploader.required_keys + cls.required_keys))
        for key in all_required_keys:
            try:
                data_dict[key]
            except KeyError as ex:
                raise exceptions.ExceptionWithMessage('The request payload did not contain the required key: %s' % key)

    @classmethod
    def _check_format(cls, upload_data, uploader_pk):

        try:
            requesting_user = get_user_model().objects.get(pk=uploader_pk)
        except ObjectDoesNotExist as ex:
            raise exceptions.ExceptionWithMessage(ex)

        # for consistent handling, take any single upload requests and
        # put inside a list
        if isinstance(upload_data, dict):
            upload_data = [upload_data,]

        for item in upload_data:
            cls._validate_ownership(item, requesting_user)
            cls._check_keys(item)
            item['user_uuid'] = requesting_user.user_uuid

        return upload_data

    def _transfer_setup(self):
        '''
        This creates the proper database instances for the uploads- it creates
        the proper Resource, Transfer, and TransferCoordinator instances

        This function expects that self.upload_data is a list and each
        item in the list is a dict.  Each dict NEEDS to have 'owner', 'destination', and
        'path' among the keys
        '''
        if len(self.upload_data) > 0:
            tc = TransferCoordinator()
            tc.save()
        else:
            return

        for item in self.upload_data:
            owner = get_user_model().objects.get(pk=item['owner'])
            originator = get_user_model().objects.get(pk=item['originator'])

            try:
                filesize_in_bytes = item['size_in_bytes']
            except KeyError as e:
                filesize_in_bytes =  0
                item['size_in_bytes'] = 0

            r = Resource(
                source = self.source,
                path = item['path'],
                name = item['name'],
                owner = owner,
                size = filesize_in_bytes,
                is_active=False # otherwise it will present the file for re-download
            )
            r.save()

            t = Transfer(
                 download=False,
                 resource=r,
                 destination=item['destination'],
                 coordinator=tc,
                 originator = originator
            )
            t.save()

            # finally add the transfer primary key to the dictionary so we will
            # be able to track the transfers
            item['transfer_pk'] = t.pk


class DropboxUploader(Uploader):
    '''
    The Dropbox upload works by using Dropbox's browser-based chooser (javascript based).
    The front-end will send a POST request containing URLs for the files to transfer (and
    other information like file size).  From there, we can parallelize the upload to our 
    storage system.

    The wrapped launcher attribute is specific to the service being used (GCP, AWS)
    so the logic of starting a VM to do the transfer is contained there
    '''

    config_keys = ['dropbox',]
    source = settings.DROPBOX

    # the only required keys (as part of the request payload for specifying an upload):
    required_keys = ['path',]

    @classmethod
    def check_format(cls, upload_data, uploader_pk):
        '''
        This class method checks that the data is in the expected format

        For Dropbox data, the front-end sends a list of direct links, which we can
        directly access (e.g. via a wget request to the URL).  No other information
        is required, although one may include ownership info as well.

        If a list is sent, then it is a list of json-objects, like:
        upload_data = [{'path':'<some dropbox url>'},{'path':'<some dropbox url>'},{'path':'<some dropbox url>'}]
    
        Check each one for the required keys isted above

        If only a single item is being transferred, an object can be sent:
        upload_data = {'path':'<some dropbox url>'}
        (this object will ultimately be placed inside a list of length 1 for consistent handling)

        uploader_pk is the primary key for the User requesting the upload.  In the case that
        the transfers specify an intended owner, we have to verify that the requesting user has permissions.
        For example, an admin may initiate an upload on someone else's behalf, and hence the request would
        contain someone other user's PK.  However, if a non-admin user tries to do the same, we need to
        reject the request
        '''
        return cls._check_format(upload_data, uploader_pk)
        

    def _transfer_setup(self):
        '''
        For the case of a Dropbox upload, self.upload_data is already 
        in the correct format for using in the parent method since it has 'path'
        and 'owner' keys

        
        '''
        return super()._transfer_setup()

        

class DriveUploader(Uploader):
    '''
    The Google Drive upload works by using Google Picker, which is a javascript based
    tool that handles the oauth2 flow.  The client-side UI (provided by Google) allows
    the user to select files.  After selecting files, a callback function will send an 
    access token and the "primary keys" (a unique identifier on Google Drive's end) 
    of the files the user has selected. 
    '''
    
    config_keys = ['google_drive',]
    source = settings.GOOGLE_DRIVE
    required_keys = ['file_id', 'drive_token']

    @classmethod
    def check_format(cls, upload_data, uploader_pk):
        '''
        This class method checks that the data is in the expected format

        For Drive data, the front-end sends a list of json-objects.  Each has an oauth2
        token and a file ID.  The token is needed to access the user's content and the file ID
        uniquely identifies the file when we use the Drive API.

        If a list is sent, then it is a list of json-objects, like:
        upload_data = [{'file_id':'<some ID string>', 'drive_token': '<some access token>'},
                       {'file_id':'<some ID string>', 'drive_token': '<some access token>'}, ...]
   

        If only a single item is being transferred, an object can be sent:
        upload_data = {'file_id':'<some ID string>', 'drive_token': '<some access token>'}

        uploader_pk is the primary key for the User requesting the upload.  In the case that
        the transfers specify an intended owner, we have to verify that the requesting user has permissions.
        For example, an admin may initiate an upload on someone else's behalf, and hence the request would
        contain someone other user's PK.  However, if a non-admin user tries to do the same, we need to
        reject the request
        '''
        return cls._check_format(upload_data, uploader_pk)

    def _reformat_data(self):
        '''
        For GoogleDrive uploads, we receive the required keys as given in the 'required_keys' variable above
        In the process of validating the request info (already performed- and looks good), we added the 'owner' 
        primary key.  Hence, self.upload_data looks like:
            [
                {'file_id':'<some ID string>', 'drive_token': '<some access token>' , 'owner': <pk>},
                {'file_id':'<some ID string>', 'drive_token': '<some access token>', 'owner': <pk>},
                ...
            ] 
        To properly work with Uploader._transfer_setup, we need to massage the keys in each dict of that list
        In this case, we need to add a 'path' key.  Since the file_id is an analog of a path (in the sense that
        it uniquely identifies something), we just use that.
        '''
        for item in self.upload_data:
            item['path'] = item['file_id']

    def _transfer_setup(self):
        self._reformat_data()
        return super()._transfer_setup()



class EnvironmentSpecificUploader(object):

    config_keys = []
    config_file = settings.UPLOADER_CONFIG['CONFIG_PATH']

    def __init__(self, upload_data):
        #instantiate the wrapped classes:
        self.uploader = self.uploader_cls(upload_data)
        self.launcher = self.launcher_cls()

        # get the config params for the uploader:
        uploader_cfg = self.uploader_cls.get_config(self.config_file)
        additional_cfg = utils.load_config(self.config_file, self.config_keys)
        uploader_cfg.update(additional_cfg)
        self.config_params = uploader_cfg

    @classmethod
    def check_format(cls, upload_info, uploader_pk):
        return cls.uploader_cls.check_format(upload_info, uploader_pk)

    def upload(self):
        self.uploader._transfer_setup()
        self.config_and_start_uploads()     


class GoogleEnvironmentUploader(EnvironmentSpecificUploader, GoogleBase):

    config_keys = []
    config_keys.extend(GoogleBase.config_keys)
    config_keys.extend(EnvironmentSpecificUploader.config_keys)

    gcloud_cmd_template = '''{gcloud} beta compute --project={google_project_id} instances \
                             create-with-container {instance_name} \
                             --zone={google_zone} \
                             --scopes={scopes} \
                             --machine-type={machine_type} \
                             --boot-disk-size={disk_size_gb}GB \
                             --metadata=google-logging-enabled=true \
                             --container-image={docker_image} \
                             --no-restart-on-failure --container-restart-policy=never \
                           '''

    @classmethod
    def check_format(cls, upload_info, uploader_pk):
        '''
        Check the upload request for formatting issues, etc. that are Google-specific here
        More general issues, such as those related to the uploader itself can be handled via
        the parent

        This happens before any asynchronous upload behavior, so this is a good place
        to check things like filename length, etc. that are specific to google 
        '''

        # first run the format check that is dependent on the uploader:
        # This returns a list of dicts
        upload_info = cls.uploader_cls.check_format(upload_info, uploader_pk)

        # the following section determines the final location in Google Storage for each file.
        # It places a 'destination' key in the dictionary for later use.
        # If the filenames are invalid, it throws an exception.
        for item_dict in upload_info:
            bucket_name = os.path.join(settings.CONFIG_PARAMS['storage_bucket_prefix'], str(item_dict['user_uuid']))
            item_name = item_dict['name']
            full_item_name = os.path.join(bucket_name, item_name)
        
            # check the validity.  GoogleStorage requires that objects are 1-1024 bytes when UTF-8 encoded
            # more info: https://cloud.google.com/storage/docs/naming
            min_length = 1
            max_length = 1024
            bytes = len(full_item_name.encode('utf-8'))
            if bytes < min_length:
                error_msg = 'The file with name %s is too short.  Please change it and try again.' % item_name
                raise exceptions.FilenameException(error_msg)
            elif bytes > max_length:
                error_msg = 'The file with name %s is too long for our storage system.  Please change and try again.' % item_name
                raise exceptions.FilenameException(error_msg)
            else:
                item_dict['destination'] = full_item_name

        # Finally, check that the file is not already being transferred:
        upload_info, error_messages = cls._check_conflicts(upload_info)

        return upload_info, error_messages

    @classmethod
    def _check_conflicts(cls, upload_data):
        '''
        Here we check if any of the requested uploads have already been started.
        Each item in self.upload_data has a key of 'destination'.  If any existing, INCOMPLETE
        transfers have the same destination, then we block it.
        '''
        all_incomplete_transfers = Transfer.objects.filter(completed=False)
        destinations = [x.destination for x in all_incomplete_transfers]
        new_transfers = []
        error_messages = []
        for item in upload_data:
            if item['destination'] in destinations:
                msg = '''The file with name %s is already in progress.  
                        If you wish to overwrite, please wait until the upload is complete and
                        try again''' % item['name']
                error_messages.append(msg)
            else:
                new_transfers.append(item)

        return new_transfers, error_messages

    def __init__(self, upload_data):
        super().__init__(upload_data)

    def _prep_single_upload(self, custom_config, index, item):

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
        # Args specific to the particular uploader should be handled in the subclass
        cmd += ' --container-arg="-token" --container-arg="%s"' % settings.CONFIG_PARAMS['token']
        cmd += ' --container-arg="-key" --container-arg="%s"' % settings.CONFIG_PARAMS['enc_key']
        cmd += ' --container-arg="-pk" --container-arg="%s"' % item['transfer_pk']
        cmd += ' --container-arg="-url" --container-arg="%s"' % full_callback_url
        cmd += ' --container-arg="-proj" --container-arg="%s"' % settings.CONFIG_PARAMS['google_project_id']
        cmd += ' --container-arg="-zone" --container-arg="%s"' % settings.CONFIG_PARAMS['google_zone']
        return cmd

class GoogleDropboxUploader(GoogleEnvironmentUploader):

    uploader_cls = DropboxUploader
    config_keys = ['dropbox_in_google',]
    config_keys.extend(GoogleEnvironmentUploader.config_keys)

    def __init__(self, upload_data):
        super().__init__(upload_data)

    def config_and_start_uploads(self):

        custom_config = copy.deepcopy(self.config_params)

        for i, item in enumerate(self.uploader.upload_data):
            cmd = self._prep_single_upload(custom_config, i, item)
            cmd += ' --container-arg="-path" --container-arg="%s"' % item['path'] # the special Dropbox link
            cmd += ' --container-arg="-destination" --container-arg="%s"' % item['destination'] # the destination (in storage)
            self.launcher.go(cmd)
 

class GoogleDriveUploader(GoogleEnvironmentUploader):

    uploader_cls = DriveUploader
    config_keys = ['drive_in_google',]
    config_keys.extend(GoogleEnvironmentUploader.config_keys)

    def __init__(self, upload_data):
        super().__init__(upload_data)

    def config_and_start_uploads(self):

        custom_config = copy.deepcopy(self.config_params)

        for i, item in enumerate(self.uploader.upload_data):
            cmd = self._prep_single_upload(custom_config, i, item)
            cmd += ' --container-arg="-drive_token" --container-arg="%s"' % item['drive_token'] # the token for accessing drive
            cmd += ' --container-arg="-file_id" --container-arg="%s"' % item['file_id'] # the unique file ID
            cmd += ' --container-arg="-destination" --container-arg="%s"' % item['destination'] # the destination (in storage)
            self.launcher.go(cmd)


class AWSEnvironmentUploader(EnvironmentSpecificUploader):
    pass


class AWSDropboxUploader(AWSEnvironmentUploader):
    uploader_cls = DropboxUploader
    config_keys = ['dropbox_in_aws',]


class AWSDriveUploader(AWSEnvironmentUploader):
    uploader_cls = DriveUploader
    config_keys = ['drive_in_aws',]


def get_uploader(source):
    '''
    Based on the compute environment and the source of the upload
    choose the appropriate class to use.
    '''

    # This defines a two-level dictionary from which we can choose
    # a class.  Additional sub-classes of EnvironmentSpecificUploader
    # need to be in this if they are to be used.  Otherwise, the application
    # will 'not know' about the class
    class_mapping = {
        settings.GOOGLE : {
            settings.GOOGLE_DRIVE : GoogleDriveUploader,
            settings.DROPBOX : GoogleDropboxUploader,
        },
        settings.AWS : {
            settings.GOOGLE_DRIVE : AWSDriveUploader,
            settings.DROPBOX : AWSDropboxUploader,
        }
    }
    environment = settings.CONFIG_PARAMS['cloud_environment']
    try:
        return class_mapping[environment][source]
    except KeyError as ex:
        raise exceptions.ExceptionWithMessage('''
            You did not specify an uploader implementation for:
                Compute environment: %s
                Upload source: %s
        ''' % (environment, source))

