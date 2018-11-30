import json
import urllib

from django.test import TestCase
from django.contrib.sites.models import Site
import unittest.mock as mock
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.exceptions import MethodNotAllowed

from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.conf import settings

from base.models import Resource
from transfer_app.models import Transfer, TransferCoordinator
import transfer_app.downloaders as downloaders
import transfer_app.exceptions as exceptions

'''
Tests for download transfer (Resources already exist in this case)
  - Transfers created, TransferCoordinator created
  - reject malformed request (missing data in post payload)
  - all bad resources (invalid PKs): reject request
  - some good, some bad PKs for Resource: reject request
  - reject transfer of Resources that are valid, but not owned by requester (unless admin)
  - If admin, can send anyone's Resources (if all valid)
'''
class GoogleEnvironmentDownloadTestCase(TestCase):
    def _setUp(self):
        '''
        In a download, users are transferring away from our systems, downloading it to another storage 
        The Resource instances already exist.
        '''
        self.admin_user = get_user_model().objects.create_user(email='admin@admin.com', password='abcd123!', is_staff=True)
        self.regular_user = get_user_model().objects.create_user(email='reguser@gmail.com', password='abcd123!')
        self.other_user = get_user_model().objects.create_user(email='otheruser@gmail.com', password='abcd123!')

        # create a couple of resources owned by the regular user:
        r1 = Resource.objects.create(
            source='google_storage',
            path='gs://a/b/reg_owned1.txt',
            size=2e9,
            owner=self.regular_user,
        )
        r2 = Resource.objects.create(
            source='google_storage',
            path='gs://a/b/reg_owned2.txt',
            size=2.1e9,
            owner=self.regular_user,
        )

        r3 = Resource.objects.create(
            source='google_storage',
            path='gs://a/b/other_owned.txt',
            size=5e9,
            owner=self.other_user,
        )

        r4 = Resource.objects.create(
            source='google_storage',
            path='gs://a/b/other_owned.txt',
            size=5e9,
            owner=self.regular_user,
            is_active=False
        )
        settings.CONFIG_PARAMS['cloud_environment'] = settings.GOOGLE
      
        site = Site.objects.get(pk=1)
        site.domain = 'example.org'
        site.name = 'example.org'
        site.save()

    def _test_rejects_if_missing_data_case1(self):
        '''
        Here, we leave out the destination as part of the request.
        '''
        client = APIClient()
        client.login(email='reguser@gmail.com', password='abcd123!')

        reguser = get_user_model().objects.get(email='reguser@gmail.com')

        url = reverse('download-transfer-initiation')
        d = {}
        d['resource_pks'] = [1,2]
        response = client.post(url, {"data":json.dumps(d)}, format='json')
        self.assertEqual(response.status_code, 400)

    def _test_rejects_if_missing_data_case2(self):
        '''
        Here, we leave out the resource primary keys as part of the request.
        '''
        client = APIClient()
        client.login(email='reguser@gmail.com', password='abcd123!')

        reguser = get_user_model().objects.get(email='reguser@gmail.com')

        url = reverse('download-transfer-initiation')
        d = {}
        d['destination'] = self.destination
        response = client.post(url, {"data":json.dumps(d)}, format='json')
        self.assertEqual(response.status_code, 400)

    def _test_rejects_if_invalid_payload_case1(self):
        '''
        Here, one of the primary keys is NOT an integer
        '''
        client = APIClient()
        client.login(email='reguser@gmail.com', password='abcd123!')

        reguser = get_user_model().objects.get(email='reguser@gmail.com')

        url = reverse('download-transfer-initiation')
        d = {}
        d['resource_pks'] = [1,'a', 2]
        d['destination'] = self.destination
        response = client.post(url, {"data":json.dumps(d)}, format='json')
        self.assertEqual(response.status_code, 400)

    def _test_rejects_if_invalid_payload_case2(self):
        '''
        Here, the resource pk list is empty
        '''
        client = APIClient()
        client.login(email='reguser@gmail.com', password='abcd123!')

        reguser = get_user_model().objects.get(email='reguser@gmail.com')

        url = reverse('download-transfer-initiation')
        d = {}
        d['resource_pks'] = []
        d['destination'] = self.destination
        response = client.post(url, {"data":json.dumps(d)}, format='json')
        self.assertEqual(response.status_code, 400)

    def _test_rejects_if_invalid_payload_case3(self):
        '''
        Here, one of the primary keys does not exist-- reject
        '''
        client = APIClient()
        client.login(email='reguser@gmail.com', password='abcd123!')

        reguser = get_user_model().objects.get(email='reguser@gmail.com')

        url = reverse('download-transfer-initiation')
        d = {}
        d['resource_pks'] = [1, 500, 2] # 500 does not exist as a primary key
        d['destination'] = self.destination
        response = client.post(url, {"data":json.dumps(d)}, format='json')
        self.assertEqual(response.status_code, 400)

    def _test_rejects_download_request_based_on_ownership_case1(self):
        '''
        Here, a user requests to download a Resource that does NOT belong to them
        '''
        client = APIClient()
        client.login(email='reguser@gmail.com', password='abcd123!')

        reguser = get_user_model().objects.get(email='reguser@gmail.com')

        url = reverse('download-transfer-initiation')
        d = {}
        d['resource_pks'] = [1, 2, 3] # 3 is owned by someone other user
        d['destination'] = self.destination
        response = client.post(url, {"data":json.dumps(d)}, format='json')
        self.assertEqual(response.status_code, 400)

    def _test_rejects_download_request_based_on_expired_resource(self):
        '''
        Here, a user requests to download a Resource that has expired
        '''
        client = APIClient()
        client.login(email='reguser@gmail.com', password='abcd123!')

        reguser = get_user_model().objects.get(email='reguser@gmail.com')

        url = reverse('download-transfer-initiation')
        d = {}
        d['resource_pks'] = [1, 2, 4] # 4 has expired
        d['destination'] = self.destination
        response = client.post(url, {"data":json.dumps(d)}, format='json')
        self.assertEqual(response.status_code, 400)

    def _test_admin_requests_transfer_of_other_user_resources(self):
        '''
        Here, we test that an admin can transfer others resource without issue 
        '''
        downloader_cls = downloaders.get_downloader(self.destination)
        originator_pk = self.admin_user.pk
        resource_pks = [1,2,3]
        expected_return = [
            {
                'resource_pk':x,  
                'originator':originator_pk,
                'destination':self.destination
             } for x in resource_pks]
        download_info, errors = downloader_cls.check_format(resource_pks, originator_pk)
        self.assertEqual(download_info, expected_return)


    def _test_reformats_request_for_download(self):
        '''
        Here, we assure that the request is reformatted to eventually create
        a proper download.
        '''
        downloader_cls = downloaders.get_downloader(self.destination)
        originator_pk = 2
        resource_pks = [1,2]
        expected_return = [
            {
                'resource_pk':x,  
                'originator':originator_pk,
                'destination':self.destination
             } for x in resource_pks]
        download_info, errors = downloader_cls.check_format(resource_pks, originator_pk)
        self.assertEqual(download_info, expected_return)


    def _test_download_auth_error_exchanging_code(self):
        '''
        Here we intentionally omit the 'code' key in the dictionary
        "returned" by the OAuth2 service.  Thus, error
        '''

        download_info = [{'resource_pk':1, 'owner':2},{'resource_pk':2, 'owner':2}]

        # make a mock request and add a session dictionary, which is required by the method
        state = 'abc123'
        code = 'mycode'
        mock_request = mock.MagicMock()
        mock_request.method = 'GET'
        mock_request.session = {
            'session_state': state,
            'download_info': download_info,
            'download_destination': self.destination
        }
        mock_request.GET = {
            'state': state
        }

        downloader_cls = downloaders.get_downloader(self.destination)
        with self.assertRaises(exceptions.RequestError):
            downloader_cls.finish_authentication_and_start_download(mock_request)

    def _test_download_wrong_auth_http_request(self):
        '''
        Here, instead of a GET request, we have it reject other types of http requests
        '''

        download_info = [{'resource_pk':1, 'owner':2},{'resource_pk':2, 'owner':2}]

        # make a mock request and add a session dictionary, which is required by the method
        state = 'abc123'
        code = 'mycode'
        mock_request = mock.MagicMock()
        mock_request.method = 'POST'
        mock_request.session = {
            'session_state': state,
            'download_info': download_info,
            'download_destination': self.destination
        }
        mock_request.GET = {
            'state': state
        }

        downloader_cls = downloaders.get_downloader(self.destination)
        with self.assertRaises(MethodNotAllowed):
            downloader_cls.finish_authentication_and_start_download(mock_request)

    #@mock.patch('transfer_app.downloaders.os')
    @mock.patch.dict('transfer_app.downloaders.os.environ', {'GCLOUD': '/mock/bin/gcloud'})
    def _test_dropbox_downloader_on_google_params(self):
        '''
        This test takes a properly formatted request and checks that the database objects have been properly
        created.  
        '''
        #mock_os.environ['GCLOUD'] = '/mock/bin/gcloud'

        downloader_cls = downloaders.get_downloader(self.destination)
        
        # prep the download info as is usually performed:
        originator_pk = 2
        resource_pks = [1,2]
        download_info = [
            {
                'resource_pk':x,  
                'originator':originator_pk,
                'destination':self.destination,
                'access_token': 'abc123'
             } for x in resource_pks]
        
        # instantiate the class, but mock out the launcher.
        # Recall the launcher is the class that actually creates the worker VMs, which
        # we do not want to do as part of the test
        downloader = downloader_cls(download_info)
        m = mock.MagicMock()
        downloader.launcher = m

        # now that the launcher has been mocked, call the download method which
        # constructs the request to start a new VM.  It is difficult to check that, so
        # we only check that the proper database objects have been created
        downloader.download()
        self.assertTrue(m.go.called)
        self.assertEqual(len(resource_pks), m.go.call_count)

        # check database objects:
        all_transfers = Transfer.objects.all()
        all_tc = TransferCoordinator.objects.all()
        self.assertTrue(len(all_transfers) == 2)
        self.assertTrue(len(all_tc) == 1)
        self.assertTrue(all([not x.completed for x in all_transfers])) # no transfer is complete
        self.assertFalse(all_tc[0].completed) # the transfer coord is also not completed

    def _test_warn_of_conflict_case1(self):
        '''
        Here, we pretend that a user has previously started a download that is still going.
        Then they try to download that same file again (and also add a new one).  Here, we check that we block appropriately.
        '''

        downloader_cls = downloaders.get_downloader(self.destination)
        
        # create a Transfer that is ongoing:
        tc = TransferCoordinator.objects.create()
        resource_pk = 1
        resource = Resource.objects.get(pk=resource_pk)
        t = Transfer.objects.create(
            download=True,
            resource = resource,
            destination = 'dropbox',
            coordinator = tc,
            originator = self.regular_user
        )

        # prep the download info as is usually performed:
        originator_pk = self.regular_user.pk
        resource_pks = [1,2] # note that we are requesting the same transfer with pk=1

        download_info, errors = downloader_cls.check_format(resource_pks, originator_pk)
        self.assertTrue(len(download_info) == 1)
        self.assertTrue(len(errors) == 1)

    def _test_simultaneous_download_by_two_originators(self):
        '''
        Here, we pretend that two users (e.g. an admin and a regular user) are trying to download the same resource at the same time
        This should be allowed.
        '''

        downloader_cls = downloaders.get_downloader(self.destination)
        
        # create a Transfer that is ongoing:
        tc = TransferCoordinator.objects.create()
        resource_pk = 1
        resource = Resource.objects.get(pk=resource_pk)
        t = Transfer.objects.create(
            download=True,
            resource = resource,
            destination = 'dropbox',
            coordinator = tc,
            originator = self.regular_user
        )

        # prep the download info as is usually performed:
        originator_pk = self.admin_user.pk
        resource_pks = [1,2] # note that we are requesting the same transfer with pk=1

        download_info, errors = downloader_cls.check_format(resource_pks, originator_pk)
        self.assertTrue(len(download_info) == 2)
        self.assertTrue(len(errors) == 0)

class GoogleDropboxDownloadTestCase(GoogleEnvironmentDownloadTestCase):

    def setUp(self):
        super()._setUp()
        self.destination = settings.DROPBOX

    def test_rejects_if_missing_data_case1(self):
        super()._test_rejects_if_missing_data_case1()

    def test_rejects_if_missing_data_case2(self):
        super()._test_rejects_if_missing_data_case2()

    def test_rejects_if_invalid_payload_case1(self):
        super()._test_rejects_if_invalid_payload_case1()

    def test_rejects_if_invalid_payload_case2(self):
        super()._test_rejects_if_invalid_payload_case2()

    def test_rejects_if_invalid_payload_case3(self):
        super()._test_rejects_if_invalid_payload_case3()

    def test_rejects_download_request_based_on_ownership_case1(self):
        super()._test_rejects_download_request_based_on_ownership_case1()

    def test_rejects_download_request_based_on_expired_resource(self):
        super()._test_rejects_download_request_based_on_expired_resource()

    def test_admin_requests_transfer_of_other_user_resources(self):
        super()._test_admin_requests_transfer_of_other_user_resources()

    def test_reformats_request_for_download(self):
        super()._test_reformats_request_for_download()

    @mock.patch('transfer_app.downloaders.os')
    @mock.patch('transfer_app.downloaders.hashlib')
    @mock.patch('transfer_app.downloaders.HttpResponseRedirect')
    def test_download_initial_auth(self, mock_redirect, mock_hashlib, mock_os):
        '''
        Here, we check that the proper request is constructed for the Dropbox OAuth2 service
        '''
        # setup elements on the mocks:

        # first, we need to mock out the random state we create.
        # in the code, we have `state = hashlib.sha256(os.urandom(1024)).hexdigest()`
        # so we have to mock all those elements
        state = 'abc123'
        mock_hex = mock.MagicMock()
        mock_hex.hexdigest.return_value = state
        mock_os.urandom.return_value = 100 # doesn't matter what this is, since it does not go to a 'real' method
        mock_hashlib.sha256.return_value = mock_hex

        downloader_cls = downloaders.get_downloader(self.destination)

        # make a mock request and add a session dictionary, which is required by the method
        mock_request = mock.MagicMock()
        mock_request.session = {}

        settings.CONFIG_PARAMS['dropbox_auth_endpoint'] = 'https://fake-auth.com/oauth2/authorize'
        settings.CONFIG_PARAMS['dropbox_callback'] = '/dropbox/callback/'
        settings.CONFIG_PARAMS['dropbox_client_id'] = 'mockclient'
        response_type = 'code'
        
        # construct the callback URL for Dropbox to use:
        current_site = Site.objects.get_current()
        domain = current_site.domain
        code_callback_url = 'https://%s%s' % (domain, settings.CONFIG_PARAMS['dropbox_callback'])

        expected_url = "{code_request_uri}?response_type={response_type}&client_id={client_id}&redirect_uri={redirect_uri}&force_reauthentication=true&state={state}".format(
            code_request_uri = settings.CONFIG_PARAMS['dropbox_auth_endpoint'],
            response_type = response_type,
            client_id = settings.CONFIG_PARAMS['dropbox_client_id'],
            redirect_uri = code_callback_url,
            state = state
        )

        downloader_cls.authenticate(mock_request)
        mock_redirect.assert_called_once_with(expected_url)
        self.assertEqual(mock_request.session['session_state'], state)


    @mock.patch('transfer_app.downloaders.dropbox_module')
    @mock.patch('transfer_app.downloaders.httplib2')
    @mock.patch('transfer_app.downloaders.transfer_tasks')
    def test_download_finish_auth(self, mock_tasks, mock_httplib, mock_dropbox_mod):
        download_info = [{'resource_pk':1, 'owner':2},{'resource_pk':2, 'owner':2}]

        mock_parser = mock.MagicMock()
        content = b'{"access_token": "foo"}' # a json-format string
        mock_parser.request.return_value = (None, content)
        mock_httplib.Http.return_value = mock_parser

        mock_dropbox_obj = mock.MagicMock()

        mock_individual = mock.MagicMock(allocated=1e10)
        mock_team = mock.MagicMock(allocated=1e10)

        mock_allocation = mock.MagicMock()
        mock_allocation.is_team.return_value = False
        mock_allocation.get_individual.return_value = mock_individual
        mock_allocation.get_team.return_value = mock_team
        mock_space_usage = mock.MagicMock(allocation=mock_allocation, used=1000)
        
        mock_dropbox_obj.users_get_space_usage.return_value = mock_space_usage
        mock_dropbox_mod.Dropbox.return_value = mock_dropbox_obj
        
        mock_download = mock.MagicMock()
        mock_tasks.download = mock_download

        # make a mock request and add a session dictionary, which is required by the method
        state = 'abc123'
        code = 'mycode'
        mock_request = mock.MagicMock()
        mock_request.method = 'GET'
        mock_request.session = {
            'session_state': state,
            'download_info': download_info,
            'download_destination': self.destination
        }
        mock_request.GET = {
            'code': code,
            'state': state
        }

        token_url = 'https://fake-auth.com/oauth2/token'

        callback_url = '/dropbox/callback/'
        client_id = 'mockclient'
        secret = 'somesecret'
        settings.CONFIG_PARAMS['dropbox_auth_endpoint'] = 'https://fake-auth.com/oauth2/authorize'
        settings.CONFIG_PARAMS['dropbox_token_endpoint'] = token_url
        settings.CONFIG_PARAMS['dropbox_callback'] = callback_url
        settings.CONFIG_PARAMS['dropbox_client_id'] = client_id
        settings.CONFIG_PARAMS['dropbox_secret'] = secret
        headers={'content-type':'application/x-www-form-urlencoded'}

        current_site = Site.objects.get_current()
        domain = current_site.domain
        full_callback_url = 'https://%s%s' % (domain, settings.CONFIG_PARAMS['dropbox_callback'])
        expected_params = urllib.parse.urlencode({
                'code':code,
                'redirect_uri': full_callback_url,
                'client_id': client_id,
                'client_secret': secret,
                'grant_type':'authorization_code'
            })

        downloader_cls = downloaders.get_downloader(self.destination)
        downloader_cls.finish_authentication_and_start_download(mock_request)
        [x.update({'access_token': 'foo'}) for x in download_info]

        mock_parser.request.assert_called_once_with(token_url, 
            method='POST', 
            body=expected_params, 
            headers=headers)

        mock_download.delay.assert_called_once_with(download_info, self.destination)

    def test_download_auth_error_exchanging_code(self):
        super()._test_download_auth_error_exchanging_code()

    def test_download_wrong_auth_http_request(self):
        super()._test_download_wrong_auth_http_request()

    def test_dropbox_downloader_on_google_params(self):
        super()._test_dropbox_downloader_on_google_params()

    def test_warn_of_conflict_case1(self):
        super()._test_warn_of_conflict_case1()

    def test_simultaneous_download_by_two_originators(self):
        super()._test_simultaneous_download_by_two_originators()


class GoogleDriveDownloadTestCase(GoogleEnvironmentDownloadTestCase):

    def setUp(self):
        super()._setUp()
        self.destination = settings.GOOGLE_DRIVE

    def test_rejects_if_missing_data_case1(self):
        super()._test_rejects_if_missing_data_case1()

    def test_rejects_if_missing_data_case2(self):
        super()._test_rejects_if_missing_data_case2()

    def test_rejects_if_invalid_payload_case1(self):
        super()._test_rejects_if_invalid_payload_case1()

    def test_rejects_if_invalid_payload_case2(self):
        super()._test_rejects_if_invalid_payload_case2()

    def test_rejects_if_invalid_payload_case3(self):
        super()._test_rejects_if_invalid_payload_case3()

    def test_rejects_download_request_based_on_ownership_case1(self):
        super()._test_rejects_download_request_based_on_ownership_case1()

    def test_rejects_download_request_based_on_expired_resource(self):
        super()._test_rejects_download_request_based_on_expired_resource()

    def test_admin_requests_transfer_of_other_user_resources(self):
        super()._test_admin_requests_transfer_of_other_user_resources()

    def test_reformats_request_for_download(self):
        super()._test_reformats_request_for_download()

    @mock.patch('transfer_app.downloaders.os')
    @mock.patch('transfer_app.downloaders.hashlib')
    @mock.patch('transfer_app.downloaders.HttpResponseRedirect')
    def test_download_initial_auth(self, mock_redirect, mock_hashlib, mock_os):
        '''
        Here, we check that the proper request is constructed for the Dropbox OAuth2 service
        '''
        # setup elements on the mocks:

        # first, we need to mock out the random state we create.
        # in the code, we have `state = hashlib.sha256(os.urandom(1024)).hexdigest()`
        # so we have to mock all those elements
        state = 'abc123'
        mock_hex = mock.MagicMock()
        mock_hex.hexdigest.return_value = state
        mock_os.urandom.return_value = 100 # doesn't matter what this is, since it does not go to a 'real' method
        mock_hashlib.sha256.return_value = mock_hex

        downloader_cls = downloaders.get_downloader(self.destination)

        # make a mock request and add a session dictionary, which is required by the method
        mock_request = mock.MagicMock()
        mock_request.session = {}

        settings.CONFIG_PARAMS['drive_auth_endpoint'] = 'https://fake-auth.com/oauth2/authorize'
        settings.CONFIG_PARAMS['drive_callback'] = 'dropbox/callback/'
        settings.CONFIG_PARAMS['drive_client_id'] = 'mockclient'

        scope = 'some scope'
        settings.CONFIG_PARAMS['drive_scope'] = scope
        response_type = 'code'
        
        # construct the callback URL for Dropbox to use:
        current_site = Site.objects.get_current()
        domain = current_site.domain
        code_callback_url = 'https://%s%s' % (domain, settings.CONFIG_PARAMS['drive_callback'])

        expected_url = "{code_request_uri}?response_type={response_type}&client_id={client_id}&redirect_uri={redirect_uri}&scope={scope}&state={state}".format(
            code_request_uri = settings.CONFIG_PARAMS['drive_auth_endpoint'],
            response_type = response_type,
            client_id = settings.CONFIG_PARAMS['drive_client_id'],
            redirect_uri = code_callback_url,
            scope=scope,
            state = state
        )

        downloader_cls.authenticate(mock_request)
        mock_redirect.assert_called_once_with(expected_url)
        self.assertEqual(mock_request.session['session_state'], state)


    @mock.patch('transfer_app.downloaders.build')
    @mock.patch('transfer_app.downloaders.google_credentials_module')
    @mock.patch('transfer_app.downloaders.httplib2')
    @mock.patch('transfer_app.downloaders.transfer_tasks')
    def test_download_finish_auth(self, mock_tasks, \
        mock_httplib, \
        mock_google_credentials_module, \
        mock_build):
        download_info = [{'resource_pk':1, 'owner':2},{'resource_pk':2, 'owner':2}]

        mock_parser = mock.MagicMock()
        content = b'{"access_token": "foo"}' # a json-format string
        mock_parser.request.return_value = (None, content)
        mock_httplib.Http.return_value = mock_parser

        mock_credentials_obj = mock.MagicMock()
        mock_google_credentials_module.Credentials.return_value = mock_credentials_obj
        mock_service = mock.MagicMock()
        quota_dict = {'limit': 1e10, 'usage': 1000}
        about_dict = {'storageQuota': quota_dict}
        mock_service.about.return_value.get.return_value.execute.return_value = about_dict
        mock_build.return_value = mock_service

        mock_download = mock.MagicMock()
        mock_tasks.download = mock_download

        # make a mock request and add a session dictionary, which is required by the method
        state = 'abc123'
        code = 'mycode'
        mock_request = mock.MagicMock()
        mock_request.method = 'GET'
        mock_request.session = {
            'session_state': state,
            'download_info': download_info,
            'download_destination': self.destination
        }
        mock_request.GET = {
            'code': code,
            'state': state
        }

        token_url = 'https://fake-auth.com/oauth2/token'
        callback_url = 'google_drive/callback/'
        client_id = 'mockclient'
        secret = 'somesecret'
        scope = 'some scope'
        settings.CONFIG_PARAMS['drive_auth_endpoint'] = 'https://fake-auth.com/oauth2/authorize'
        settings.CONFIG_PARAMS['drive_token_endpoint'] = token_url
        settings.CONFIG_PARAMS['drive_callback'] = callback_url
        settings.CONFIG_PARAMS['drive_client_id'] = client_id
        settings.CONFIG_PARAMS['drive_secret'] = secret

        current_site = Site.objects.get_current()
        domain = current_site.domain
        full_callback_url = 'https://%s%s' % (domain, settings.CONFIG_PARAMS['drive_callback'])
        headers={'content-type':'application/x-www-form-urlencoded'}
        expected_params = urllib.parse.urlencode({
                'code':code,
                'redirect_uri': full_callback_url,
                'client_id': client_id,
                'client_secret': secret,
                'grant_type':'authorization_code'
            })

        downloader_cls = downloaders.get_downloader(self.destination)
        downloader_cls.finish_authentication_and_start_download(mock_request)
        [x.update({'access_token': 'foo'}) for x in download_info]

        mock_parser.request.assert_called_once_with(token_url, 
            method='POST', 
            body=expected_params, 
            headers=headers)

        mock_download.delay.assert_called_once_with(download_info, self.destination)

    def test_download_auth_error_exchanging_code(self):
        super()._test_download_auth_error_exchanging_code()

    def test_download_wrong_auth_http_request(self):
        super()._test_download_wrong_auth_http_request()

    def test_warn_of_conflict_case1(self):
        super()._test_warn_of_conflict_case1()

    def test_simultaneous_download_by_two_originators(self):
        super()._test_simultaneous_download_by_two_originators()




