import json
import uuid

from django.test import TestCase
import unittest.mock as mock
from rest_framework.test import APIClient
from rest_framework import status

from django.urls import reverse
from django.contrib.auth import get_user_model
from django.conf import settings

from base.models import Resource
from transfer_app.models import Transfer, TransferCoordinator
import transfer_app.uploaders as uploaders
import base.exceptions as exceptions


class GeneralUploadInitTestCase(TestCase):

    def test_uploader_mod_returns_correct_uploader_implementation(self):
    
        # first try dropbox uploader on google:
        settings.CONFIG_PARAMS['cloud_environment'] = settings.GOOGLE
        source = settings.DROPBOX
        result_cls = uploaders.get_uploader(source)
        self.assertEqual(result_cls, uploaders.GoogleDropboxUploader)

        settings.CONFIG_PARAMS['cloud_environment'] = settings.GOOGLE
        source = settings.GOOGLE_DRIVE
        result_cls = uploaders.get_uploader(source)
        self.assertEqual(result_cls, uploaders.GoogleDriveUploader)

        settings.CONFIG_PARAMS['cloud_environment'] = settings.AWS
        source = settings.DROPBOX
        result_cls = uploaders.get_uploader(source)
        self.assertEqual(result_cls, uploaders.AWSDropboxUploader)

        settings.CONFIG_PARAMS['cloud_environment'] = settings.AWS
        source = settings.GOOGLE_DRIVE
        result_cls = uploaders.get_uploader(source)
        self.assertEqual(result_cls, uploaders.AWSDriveUploader)


class DropboxGoogleUploadInitTestCase(TestCase):
    '''
    This is the test suite for transfers FROM Dropbox into Google storage
    '''

    def setUp(self):
        '''
        In an upload, users are transferring TO our system.  Resource objects do NOT exist up front.

        Below, we setup all tests such that we have one admin and two regular users
        In addition, we setup appropriate environment variables that would be there in the
        implementation
        '''
        self.admin_user = get_user_model().objects.create_user(email=settings.ADMIN_TEST_EMAIL, password='abcd123!', is_staff=True, user_uuid=uuid.uuid4())
        self.regular_user = get_user_model().objects.create_user(email=settings.REGULAR_TEST_EMAIL, password='abcd123!', user_uuid=uuid.uuid4())
        self.other_user = get_user_model().objects.create_user(email=settings.OTHER_TEST_EMAIL, password='abcd123!', user_uuid=uuid.uuid4())

        settings.CONFIG_PARAMS['cloud_environment'] = settings.GOOGLE
        self.bucket_name = 'gs://user-storage-bucket'
        settings.CONFIG_PARAMS['storage_bucket_prefix'] = self.bucket_name

    def test_reject_malformed_upload_request_for_dropbox_google_case1(self):
        '''
        This tests that improperly formatted requests are rejected
        Here, the upload_source key is not recognized
        '''
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        reguser = get_user_model().objects.get(email=settings.REGULAR_TEST_EMAIL)

        # a list of dicts to be used in the request
        upload_info = []
        upload_info.append({'path': 'https://dropbox-link.com/1', 'name':'f1.txt'})
        upload_info.append({'path': 'https://dropbox-link.com/2', 'name':'f2.txt'})
        upload_info = json.dumps(upload_info)
        request_dict = {'upload_source':'junk', 'upload_info': upload_info}
        url = reverse('upload-transfer-initiation')
        response = client.post(url, request_dict, format='json')
        self.assertEqual(response.status_code, 400)

    def test_reject_malformed_upload_request_for_dropbox_google_case2(self):
        '''
        This tests that improperly formatted requests are rejected
        Here, a required key is missing ('pathS' is used instead of 'path')
        '''
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        reguser = get_user_model().objects.get(email=settings.REGULAR_TEST_EMAIL)

        # a list of dicts to be used in the request
        upload_info = []
        upload_info.append({'pathS': 'https://dropbox-link.com/1', 'name':'f1.txt'})
        upload_info.append({'path': 'https://dropbox-link.com/2', 'name':'f2.txt'})
        upload_info = json.dumps(upload_info)
        request_dict = {'upload_source':settings.DROPBOX, 'upload_info': upload_info}
        url = reverse('upload-transfer-initiation')
        response = client.post(url, request_dict, format='json')
        self.assertEqual(response.status_code, 400)

    def test_reject_malformed_upload_request_for_dropbox_google_case3(self):
        '''
        This tests that improperly formatted requests are rejected
        Here, the request is missing the upload_source key
        '''
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        reguser = get_user_model().objects.get(email=settings.REGULAR_TEST_EMAIL)

        # a list of dicts to be used in the request
        upload_info = []
        upload_info.append({'pathS': 'https://dropbox-link.com/1', 'name':'f1.txt'})
        upload_info.append({'path': 'https://dropbox-link.com/2', 'name':'f2.txt'})
        upload_info = json.dumps(upload_info)
        request_dict = {'upload_info': upload_info}
        url = reverse('upload-transfer-initiation')
        response = client.post(url, request_dict, format='json')
        self.assertEqual(response.status_code, 400)

    def test_reject_malformed_upload_request_for_dropbox_google_case4(self):
        '''
        This tests that improperly formatted requests are rejected
        Here, the upload info (i.e. which files are being transferred) is missing
        from the request
        '''
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        reguser = get_user_model().objects.get(email=settings.REGULAR_TEST_EMAIL)

        request_dict = {'upload_source':settings.DROPBOX}
        url = reverse('upload-transfer-initiation')
        response = client.post(url, request_dict, format='json')
        self.assertEqual(response.status_code, 400)

    def test_dropbox_upload_format_checker(self):
        '''
        Asserts that the "prep" done on the request adds the expected fields.
        This bypasses the client/request and directly tests the method

        Here we test that the prep work adds the proper keys to the upload info
        so that the spawned workers have all the information they need.
        '''
        upload_info = []
        upload_info.append({'path': 'https://dropbox-link.com/1', 'name':'f1.txt'})
        upload_info.append({'path': 'https://dropbox-link.com/2', 'name':'f2.txt'})
        user_pk = 1
        user = get_user_model().objects.get(pk=user_pk)
        user_uuid = user.user_uuid

        # since the method below modifies the upload_info in-place, we need to copy the result
        # BEFORE running the method we are testing:
        expected_list = []
        for item in upload_info:
            edited_item = item.copy()
            edited_item['owner'] = user_pk
            edited_item['originator'] = user_pk
            edited_item['user_uuid'] = user_uuid
            edited_item['destination'] = '%s/%s/%s' % (self.bucket_name, str(user_uuid), edited_item['name'])
            expected_list.append(edited_item)

        response, error_messages = uploaders.GoogleDropboxUploader.check_format(upload_info, user_pk)
        self.assertEqual(response, expected_list)

    def test_dropbox_upload_format_checker_case2(self):
        '''
        Asserts that the "prep" done on the request adds the expected fields.
        This bypasses the client/request and directly tests the method

        Here we test that a single upload is handled appropriately.  Instead of a
        list, the upload_info is a dict.  HOWEVER, the prep work should put this into 
        a list so that downstream methods can handle both cases consistently.
        '''
        upload_info = {'path': 'https://dropbox-link.com/1', 'name':'f1.txt'}
        user_pk = 1
        user = get_user_model().objects.get(pk=user_pk)
        user_uuid = user.user_uuid        

        # since the method below modifies the upload_info in-place, we need to copy the result
        # BEFORE running the method we are testing:
        expected = [
            {'path': 'https://dropbox-link.com/1', 
            'name':'f1.txt',
            'owner': user_pk,
            'originator': user_pk,
            'user_uuid': user_uuid,
            'destination': '%s/%s/%s' % (self.bucket_name, str(user_uuid), upload_info['name'])
            },
        ]

        response, error_messages = uploaders.GoogleDropboxUploader.check_format(upload_info, user_pk)
        self.assertEqual(response, expected)

    def test_dropbox_upload_format_checker_rejects_poor_format_case1(self):
        '''
        Checks if request is missing the 'path' key
        This is likely a double-test of the one above, but does not hurt
        '''
        upload_info = []
        upload_info.append({'name':'f1.txt'})
        upload_info.append({'path': 'https://dropbox-link.com/2', 'name':'f2.txt'})
        user_pk = 1
        with self.assertRaises(exceptions.ExceptionWithMessage):
            uploaders.DropboxUploader.check_format(upload_info, user_pk)

    def test_dropbox_upload_format_checker_rejects_poor_format_case2(self):
        '''
        Checks if request is missing the 'name' key
        '''
        upload_info = []
        upload_info.append({'path': 'https://dropbox-link.com/1'})
        upload_info.append({'path': 'https://dropbox-link.com/2', 'name':'f2.txt'})
        user_pk = 1
        with self.assertRaises(exceptions.ExceptionWithMessage):
            uploaders.DropboxUploader.check_format(upload_info, user_pk)

    def test_dropbox_upload_format_checker_rejects_owner_case1(self):
        '''
        Checks that user's cannot upload as someone else
        Here, the request specifices the owner with pk=2.  However, someone with user_pk=3
        is making the request.  Since they are are not admin, they can only assign to themself
        '''
        upload_info = []
        upload_info.append({'path': 'https://dropbox-link.com/1', 'name':'f1.txt', 'owner':2})
        upload_info.append({'path': 'https://dropbox-link.com/2', 'name':'f2.txt', 'owner':2})
        user_pk = 3
        with self.assertRaises(exceptions.ExceptionWithMessage):
            uploaders.DropboxUploader.check_format(upload_info, user_pk)

    def test_dropbox_upload_format_checker_rejects_owner_case2(self):
        '''
        Checks that cannot use the primary key of a non-existant user
        '''
        upload_info = []
        upload_info.append({'path': 'https://dropbox-link.com/1', 'name':'f1.txt', 'owner':5})
        upload_info.append({'path': 'https://dropbox-link.com/2', 'name':'f2.txt', 'owner':5})
        user_pk = 5
        with self.assertRaises(exceptions.ExceptionWithMessage):
            uploaders.DropboxUploader.check_format(upload_info, user_pk)

    def test_dropbox_upload_format_checker_accepts_owner(self):
        '''
        Checks that self-assignment works when the request contains the user's pk
        '''
        upload_info = []
        upload_info.append({'path': 'https://dropbox-link.com/1', 'name':'f1.txt', 'owner':2})
        upload_info.append({'path': 'https://dropbox-link.com/2', 'name':'f2.txt', 'owner':2})
        user_pk = 2
        expected_dict = upload_info.copy()
        for item in expected_dict:
            item['originator'] = user_pk
        response = uploaders.DropboxUploader.check_format(upload_info, user_pk)
        self.assertEqual(response, expected_dict)

    def test_dropbox_upload_format_checker_accepts_owner_specified_by_admin(self):
        '''
        Here, an admin can assign ownership to someone else
        '''
        upload_info = []
        upload_info.append({'path': 'https://dropbox-link.com/1', 'name':'f1.txt', 'owner':2})
        upload_info.append({'path': 'https://dropbox-link.com/2', 'name':'f2.txt', 'owner':2})
        user_pk = 1
        expected_dict = upload_info.copy()
        for item in expected_dict:
            item['originator'] = user_pk
        response = uploaders.DropboxUploader.check_format(upload_info, user_pk)
        self.assertEqual(response, expected_dict)

    @mock.patch.dict('transfer_app.uploaders.os.environ', {'GCLOUD': '/mock/bin/gcloud'})
    def test_dropbox_uploader_on_google_params(self):
        '''
        This test takes a properly formatted request and checks that the database objects have been properly
        created.  
        '''
        
        source = settings.DROPBOX
        uploader_cls = uploaders.get_uploader(source)
        self.assertEqual(uploader_cls, uploaders.GoogleDropboxUploader)
        
        # prep the upload info as is usually performed:
        upload_info = []
        upload_info.append({'path': 'https://dropbox-link.com/1', 'name':'f1.txt', 'owner':2})
        upload_info.append({'path': 'https://dropbox-link.com/2', 'name':'f2.txt', 'owner':2})
        upload_info, error_messages = uploader_cls.check_format(upload_info, 2)
        
        # instantiate the class, but mock out the launcher.
        # Recall the launcher is the class that actually creates the worker VMs, which
        # we do not want to do as part of the test
        uploader = uploader_cls(upload_info)
        m = mock.MagicMock()
        uploader.launcher = m

        # now that the launcher has been mocked, call the upload method which
        # constructs the request to start a new VM.  It is difficult to check that, so
        # we only check that the proper database objects have been created
        uploader.upload()
        self.assertTrue(m.go.called)
        self.assertEqual(2, m.go.call_count)

        # check database objects:
        all_transfers = Transfer.objects.all()
        all_resources = Resource.objects.all()
        all_tc = TransferCoordinator.objects.all()
        self.assertTrue(len(all_transfers) == 2)
        self.assertTrue(len(all_resources) == 2)
        self.assertTrue(len(all_tc) == 1)
        self.assertTrue(all([not x.completed for x in all_transfers])) # no transfer is complete
        self.assertFalse(all_tc[0].completed) # the transfer coord is also not completed

    @mock.patch.dict('transfer_app.uploaders.os.environ', {'GCLOUD': '/mock/bin/gcloud'})
    def test_dropbox_uploader_on_google_params_single(self):
        
        source = settings.DROPBOX
        uploader_cls = uploaders.get_uploader(source)
        self.assertEqual(uploader_cls, uploaders.GoogleDropboxUploader)

        upload_info = {'path': 'https://dropbox-link.com/1', 'name':'f1.txt', 'owner':2}

        upload_info, error_messages = uploader_cls.check_format(upload_info, 2)
        
        uploader = uploader_cls(upload_info)
        m = mock.MagicMock()
        uploader.launcher = m

        uploader.upload()
        self.assertTrue(m.go.called)
        self.assertEqual(1, m.go.call_count)

        # check database objects:
        all_transfers = Transfer.objects.all()
        all_resources = Resource.objects.all()
        all_tc = TransferCoordinator.objects.all()
        self.assertTrue(len(all_transfers) == 1)
        self.assertTrue(len(all_resources) == 1)
        self.assertTrue(len(all_tc) == 1)
        self.assertTrue(all([not x.completed for x in all_transfers])) # no transfer is complete
        self.assertFalse(all_tc[0].completed) # the transfer coord is also not completed

    @mock.patch.dict('transfer_app.uploaders.os.environ', {'GCLOUD': '/mock/bin/gcloud'})
    def test_dropbox_uploader_on_google_disk_sizing(self):
        
        source = settings.DROPBOX
        uploader_cls = uploaders.get_uploader(source)
        self.assertEqual(uploader_cls, uploaders.GoogleDropboxUploader)
        
        upload_info = []
        filesize = 100e9 # 100GB
        upload_info.append({
                        'path': 'https://dropbox-link.com/1', 
                        'name':'f1.txt', 
                        'owner':2, 
                        'size_in_bytes': filesize})

        upload_info, error_messages = uploader_cls.check_format(upload_info, 2)
        
        uploader = uploader_cls(upload_info)
        uploader.config_params['disk_size_factor'] = 3
        m = mock.MagicMock()
        uploader.launcher = m

        uploader.upload()
        self.assertTrue(m.go.called)
        self.assertEqual(1, m.go.call_count)

        call_arg = m.go.call_args
        the_call = call_arg.call_list()[0]
        import re
        target = '--boot-disk-size=300GB'
        matches = re.findall(target, str(the_call))
        self.assertEqual(len(matches), 1)


class DriveGoogleUploadInitTestCase(TestCase):
    '''
    This is the test suite for transfers FROM Google Drive into Google storage
    '''

    def setUp(self):
        '''
        In an upload, users are transferring TO our system.  Resource objects do NOT exist up front.

        Below, we setup all tests such that we have one admin and two regular users
        In addition, we setup appropriate environment variables that would be there in the
        implementation
        '''
        self.admin_user = get_user_model().objects.create_user(email=settings.ADMIN_TEST_EMAIL, password='abcd123!', is_staff=True)
        self.regular_user = get_user_model().objects.create_user(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')
        self.other_user = get_user_model().objects.create_user(email=settings.OTHER_TEST_EMAIL, password='abcd123!')

        settings.CONFIG_PARAMS['cloud_environment'] = settings.GOOGLE
        self.bucket_name = 'gs://user-storage-bucket'
        settings.CONFIG_PARAMS['storage_bucket_prefix'] = self.bucket_name

    def test_reject_malformed_upload_request_for_drive_google_case1(self):
        '''
        This tests that improperly formatted requests are rejected
        Here, the upload_source key is not recognized
        '''
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        reguser = get_user_model().objects.get(email=settings.REGULAR_TEST_EMAIL)

        # a list of dicts to be used in the request
        upload_info = []
        upload_info.append({'file_id': 'abc123', 'name':'f1.txt', 'drive_token': 'fooToken'})
        upload_info.append({'file_id': 'def123', 'name':'f2.txt', 'drive_token': 'fooToken'})
        upload_info = json.dumps(upload_info)
        request_dict = {'upload_source':'junk', 'upload_info': upload_info}
        url = reverse('upload-transfer-initiation')
        response = client.post(url, request_dict, format='json')
        self.assertEqual(response.status_code, 400)

    def test_reject_malformed_upload_request_for_drive_google_case2(self):
        '''
        This tests that improperly formatted requests are rejected
        Here, a required key is missing ('file_idS' is used instead of 'file_id')
        '''
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        reguser = get_user_model().objects.get(email=settings.REGULAR_TEST_EMAIL)

        # a list of dicts to be used in the request
        upload_info = []
        upload_info.append({'file_idS': 'abc123', 'name':'f1.txt', 'drive_token': 'fooToken'})
        upload_info.append({'file_id': 'def123', 'name':'f2.txt', 'drive_token': 'fooToken'})
        upload_info = json.dumps(upload_info)
        request_dict = {'upload_source':settings.GOOGLE_DRIVE, 'upload_info': upload_info}
        url = reverse('upload-transfer-initiation')
        response = client.post(url, request_dict, format='json')
        self.assertEqual(response.status_code, 400)

    def test_reject_malformed_upload_request_for_drive_google_case3(self):
        '''
        This tests that improperly formatted requests are rejected
        Here, the request is missing the upload_source key
        '''
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        reguser = get_user_model().objects.get(email=settings.REGULAR_TEST_EMAIL)

        # a list of dicts to be used in the request
        upload_info = []
        upload_info.append({'file_id': 'abc123', 'name':'f1.txt', 'drive_token': 'fooToken'})
        upload_info.append({'file_id': 'def123', 'name':'f2.txt', 'drive_token': 'fooToken'})
        upload_info = json.dumps(upload_info)
        request_dict = {'upload_info': upload_info}
        url = reverse('upload-transfer-initiation')
        response = client.post(url, request_dict, format='json')
        self.assertEqual(response.status_code, 400)

    def test_reject_malformed_upload_request_for_drive_google_case4(self):
        '''
        This tests that improperly formatted requests are rejected
        Here, the upload info (i.e. which files are being transferred) is missing
        from the request
        '''
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        reguser = get_user_model().objects.get(email=settings.REGULAR_TEST_EMAIL)

        request_dict = {'upload_source':settings.GOOGLE_DRIVE}
        url = reverse('upload-transfer-initiation')
        response = client.post(url, request_dict, format='json')
        self.assertEqual(response.status_code, 400)

    def test_reject_malformed_upload_request_for_drive_google_case5(self):
        '''
        This tests that improperly formatted requests are rejected
        Here, we are missing the oauth access token
        '''
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        reguser = get_user_model().objects.get(email=settings.REGULAR_TEST_EMAIL)

        upload_info = []
        # named 'token' instead of drive_token
        upload_info.append({'file_id': 'abc123', 'name':'f1.txt', 'token': 'fooToken'})
        upload_info.append({'file_id': 'def123', 'name':'f2.txt', 'token': 'fooToken'})
        upload_info = json.dumps(upload_info)
        request_dict = {'upload_source':settings.GOOGLE_DRIVE, 'upload_info': upload_info}
        url = reverse('upload-transfer-initiation')
        response = client.post(url, request_dict, format='json')
        self.assertEqual(response.status_code, 400)


    def test_drive_upload_format_checker(self):
        '''
        Asserts that the "prep" done on the request adds the expected fields.
        This bypasses the client/request and directly tests the method

        Here we test that the prep work adds the proper keys to the upload info
        so that the spawned workers have all the information they need.
        '''
        upload_info = []
        upload_info.append({'file_id': 'abc123', 'name':'f1.txt', 'drive_token': 'fooToken'})
        upload_info.append({'file_id': 'def123', 'name':'f2.txt', 'drive_token': 'fooToken'})
        user = get_user_model().objects.get(pk=1)
        user_pk = 1
        user_uuid = user.user_uuid

        # since the method below modifies the upload_info in-place, we need to copy the result
        # BEFORE running the method we are testing:
        expected_list = []
        for item in upload_info:
            edited_item = item.copy()
            edited_item['owner'] = user_pk
            edited_item['originator'] = user_pk
            edited_item['user_uuid'] = user_uuid
            edited_item['destination'] = '%s/%s/%s' % (self.bucket_name, str(user_uuid), edited_item['name'])
            expected_list.append(edited_item)

        response, error_messages = uploaders.GoogleDriveUploader.check_format(upload_info, user_pk)
        self.assertEqual(response, expected_list)

    def test_drive_upload_format_checker_case2(self):
        '''
        Asserts that the "prep" done on the request adds the expected fields.
        This bypasses the client/request and directly tests the method

        Here we test that a single upload is handled appropriately.  Instead of a
        list, the upload_info is a dict.  HOWEVER, the prep work should put this into 
        a list so that downstream methods can handle both cases consistently.
        '''
        upload_info = {'file_id': 'abc123', 'name':'f1.txt', 'drive_token': 'fooToken'}
        user = get_user_model().objects.get(pk=1)
        user_pk = user.pk
        user_uuid = user.user_uuid

        # since the method below modifies the upload_info in-place, we need to copy the result
        # BEFORE running the method we are testing:
        expected = [
            {'file_id': 'abc123',
            'name':'f1.txt',
            'owner': user_pk,
            'originator': user_pk,
            'drive_token': 'fooToken',
            'user_uuid': user_uuid,
            'destination': '%s/%s/%s' % (self.bucket_name, str(user_uuid), upload_info['name'])
            },
        ]

        response, error_messages = uploaders.GoogleDriveUploader.check_format(upload_info, user_pk)
        self.assertEqual(response, expected)

    def test_drive_upload_format_checker_rejects_poor_format_case1(self):
        '''
        Checks if request is missing the 'file_id' key
        This is likely a double-test of the one above, but does not hurt
        '''
        upload_info = []
        upload_info.append({'name':'f1.txt', 'token': 'fooToken'})
        upload_info.append({'file_id': 'def123', 'name':'f2.txt', 'drive_token': 'fooToken'})
        user_pk = 1
        with self.assertRaises(exceptions.ExceptionWithMessage):
            uploaders.DriveUploader.check_format(upload_info, user_pk)

    def test_drive_upload_format_checker_rejects_poor_format_case2(self):
        '''
        Checks if request is missing the 'name' key
        '''
        upload_info = []
        upload_info.append({'file_id': 'abc123', 'drive_token': 'fooToken'})
        upload_info.append({'file_id': 'def123', 'name':'f2.txt', 'drive_token': 'fooToken'})
        user_pk = 1
        with self.assertRaises(exceptions.ExceptionWithMessage):
            uploaders.DriveUploader.check_format(upload_info, user_pk)

    def test_drive_upload_format_checker_rejects_owner_case1(self):
        '''
        Checks that user's cannot upload as someone else
        Here, the request specifices the owner with pk=2.  However, someone with user_pk=3
        is making the request.  Since they are are not admin, they can only assign to themself
        '''
        upload_info = []
        upload_info.append({'file_id': 'abc123', 'name':'f1.txt', 'drive_token': 'fooToken', 'owner':2})
        upload_info.append({'file_id': 'def123', 'name':'f2.txt', 'drive_token': 'fooToken', 'owner':2})
        user_pk = 3
        with self.assertRaises(exceptions.ExceptionWithMessage):
            uploaders.DriveUploader.check_format(upload_info, user_pk)

    def test_drive_upload_format_checker_rejects_owner_case2(self):
        '''
        Checks that cannot use the primary key of a non-existant user
        '''
        upload_info = []
        upload_info.append({'file_id': 'abc123', 'name':'f1.txt', 'drive_token': 'fooToken', 'owner':5})
        upload_info.append({'file_id': 'def123', 'name':'f2.txt', 'drive_token': 'fooToken', 'owner':5})
        user_pk = 5
        with self.assertRaises(exceptions.ExceptionWithMessage):
            uploaders.DriveUploader.check_format(upload_info, user_pk)

    def test_drive_upload_format_checker_accepts_owner(self):
        '''
        Checks that self-assignment works when the request contains the user's pk
        '''
        upload_info = []
        upload_info.append({'file_id': 'abc123', 'name':'f1.txt', 'drive_token': 'fooToken', 'owner':2})
        upload_info.append({'file_id': 'def123', 'name':'f2.txt', 'drive_token': 'fooToken', 'owner':2})
        user_pk = 2
        expected_dict = upload_info.copy()
        for item in expected_dict:
            item['originator'] = user_pk
        response = uploaders.DriveUploader.check_format(upload_info, user_pk)
        self.assertEqual(response, expected_dict)

    def test_drive_upload_format_checker_accepts_owner_specified_by_admin(self):
        '''
        Here, an admin can assign ownership to someone else
        '''
        upload_info = []
        upload_info.append({'file_id': 'abc123', 'name':'f1.txt', 'drive_token': 'fooToken', 'owner':2})
        upload_info.append({'file_id': 'def123', 'name':'f2.txt', 'drive_token': 'fooToken', 'owner':2})
        user_pk = 1
        expected_dict = upload_info.copy()
        for item in expected_dict:
            item['originator'] = user_pk
        response = uploaders.DriveUploader.check_format(upload_info, user_pk)
        self.assertEqual(response, expected_dict)

    @mock.patch.dict('transfer_app.uploaders.os.environ', {'GCLOUD': '/mock/bin/gcloud'})
    def test_drive_uploader_on_google_params(self):
        '''
        This test takes a properly formatted request and checks that the database objects have been properly
        created.  
        '''
        
        source = settings.GOOGLE_DRIVE
        uploader_cls = uploaders.get_uploader(source)
        self.assertEqual(uploader_cls, uploaders.GoogleDriveUploader)
        # prep the upload info as is usually performed:
        upload_info = []
        upload_info.append({'file_id': 'abc123', 'name':'f1.txt', 'drive_token': 'fooToken', 'owner':2})
        upload_info.append({'file_id': 'def123', 'name':'f2.txt', 'drive_token': 'fooToken', 'owner':2})
        upload_info, error_messages = uploader_cls.check_format(upload_info, 2)
        
        # instantiate the class, but mock out the launcher.
        # Recall the launcher is the class that actually creates the worker VMs, which
        # we do not want to do as part of the test
        uploader = uploader_cls(upload_info)

        m = mock.MagicMock()
        uploader.launcher = m

        # now that the launcher has been mocked, call the upload method which
        # constructs the request to start a new VM.  It is difficult to check that, so
        # we only check that the proper database objects have been created
        uploader.upload()
        self.assertTrue(m.go.called)
        self.assertEqual(2, m.go.call_count)

        # check database objects:
        all_transfers = Transfer.objects.all()
        all_resources = Resource.objects.all()
        all_tc = TransferCoordinator.objects.all()
        self.assertTrue(len(all_transfers) == 2)
        self.assertTrue(len(all_resources) == 2)
        self.assertTrue(len(all_tc) == 1)
        self.assertTrue(all([x.source == settings.GOOGLE_DRIVE for x in all_resources]))
        self.assertTrue(all([not x.completed for x in all_transfers])) # no transfer is complete
        self.assertFalse(all_tc[0].completed) # the transfer coord is also not completed

    @mock.patch.dict('transfer_app.uploaders.os.environ', {'GCLOUD': '/mock/bin/gcloud'})
    def test_drive_uploader_on_google_params_single(self):
        
        source = settings.GOOGLE_DRIVE
        uploader_cls = uploaders.get_uploader(source)
        self.assertEqual(uploader_cls, uploaders.GoogleDriveUploader)

        upload_info = {'file_id': 'abc123', 'name':'f1.txt', 'drive_token': 'fooToken', 'owner':2}
        upload_info, error_messages = uploader_cls.check_format(upload_info, 2)
        
        uploader = uploader_cls(upload_info)
        m = mock.MagicMock()
        uploader.launcher = m

        uploader.upload()
        self.assertTrue(m.go.called)
        self.assertEqual(1, m.go.call_count)

        # check database objects:
        all_transfers = Transfer.objects.all()
        all_resources = Resource.objects.all()
        all_tc = TransferCoordinator.objects.all()
        self.assertTrue(len(all_transfers) == 1)
        self.assertTrue(len(all_resources) == 1)
        self.assertTrue(len(all_tc) == 1)
        self.assertTrue(all([not x.completed for x in all_transfers])) # no transfer is complete
        self.assertFalse(all_tc[0].completed) # the transfer coord is also not completed

    @mock.patch.dict('transfer_app.uploaders.os.environ', {'GCLOUD': '/mock/bin/gcloud'})
    def test_drive_uploader_on_google_disk_sizing(self):

        
        source = settings.GOOGLE_DRIVE
        uploader_cls = uploaders.get_uploader(source)
        self.assertEqual(uploader_cls, uploaders.GoogleDriveUploader)
        
        upload_info = []
        filesize = 100e9 # 100GB
        upload_info.append({
                        'file_id': 'abc123',
                        'drive_token': 'fooToken', 
                        'name':'f1.txt', 
                        'owner':2, 
                        'size_in_bytes': filesize})

        upload_info, error_messages = uploader_cls.check_format(upload_info, 2)
        
        uploader = uploader_cls(upload_info)
        uploader.config_params['disk_size_factor'] = 3
        m = mock.MagicMock()
        uploader.launcher = m

        uploader.upload()
        self.assertTrue(m.go.called)
        self.assertEqual(1, m.go.call_count)

        call_arg = m.go.call_args
        the_call = call_arg.call_list()[0]
        import re
        target = '--boot-disk-size=300GB'
        matches = re.findall(target, str(the_call))
        self.assertEqual(len(matches), 1)


class GoogleEnvironmentUploadInitTestCase(TestCase):
    '''
    This is the test suite for transfers FROM Dropbox into Google storage
    '''

    def setUp(self):
        '''
        In an upload, users are transferring TO our system.  Resource objects do NOT exist up front.
        '''
        self.admin_user = get_user_model().objects.create_user(email=settings.ADMIN_TEST_EMAIL, password='abcd123!', is_staff=True)
        self.regular_user = get_user_model().objects.create_user(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')
        self.other_user = get_user_model().objects.create_user(email=settings.OTHER_TEST_EMAIL, password='abcd123!')

        settings.CONFIG_PARAMS['cloud_environment'] = settings.GOOGLE
        self.bucket_name = 'gs://user-storage-bucket'
        settings.CONFIG_PARAMS['storage_bucket_prefix'] = self.bucket_name

    def test_reject_long_name_in_google(self):
        source = settings.DROPBOX
        uploader_cls = uploaders.get_uploader(source)
        self.assertEqual(uploader_cls, uploaders.GoogleDropboxUploader)
        
        upload_info = []
        long_name = 'x'*2000 + '.txt'
        upload_info.append({'path': 'https://dropbox-link.com/1', 'name':long_name, 'owner':2})
        upload_info.append({'path': 'https://dropbox-link.com/2', 'name':'f2.txt', 'owner':2})

        with self.assertRaises(exceptions.FilenameException):
            upload_info, error_messages = uploader_cls.check_format(upload_info, 2)

    @mock.patch.dict('transfer_app.uploaders.os.environ', {'GCLOUD': '/mock/bin/gcloud'})
    def test_warn_of_conflict_case1(self):
        '''
        Here, we pretend that a user has previously started an upload that is still going.
        Then they try to upload that same file again (and also add a new one).  Here, we check that we block appropriately.
        '''
        
        source = settings.DROPBOX
        uploader_cls = uploaders.get_uploader(source)
        self.assertEqual(uploader_cls, uploaders.GoogleDropboxUploader)
        
        # prep the upload info as is usually performed:
        upload_info = []
        upload_info.append({'path': 'https://dropbox-link.com/1', 'name':'f1.txt', 'owner':2})
        upload_info.append({'path': 'https://dropbox-link.com/2', 'name':'f2.txt', 'owner':2})
        upload_info, error_messages = uploader_cls.check_format(upload_info, 2)

        self.assertEqual(len(upload_info), 2)
        self.assertEqual(len(error_messages), 0)
        
        # instantiate the class, but mock out the launcher.
        # Recall the launcher is the class that actually creates the worker VMs, which
        # we do not want to do as part of the test
        uploader = uploader_cls(upload_info)
        m = mock.MagicMock()
        uploader.launcher = m

        # mock launch of transfers, which creates the database objects
        uploader.upload()

        # prep the upload info as is usually performed:
        additional_uploads = []
        additional_uploads.append({'path': 'https://dropbox-link.com/3', 'name':'f3.txt', 'owner':2}) #new
        additional_uploads.append({'path': 'https://dropbox-link.com/2', 'name':'f2.txt', 'owner':2}) # same as above- so reject!
        processed_uploads, error_messages = uploader_cls.check_format(additional_uploads, 2)

        self.assertEqual(len(processed_uploads), 1)
        self.assertEqual(len(error_messages), 1)

        uploader = uploader_cls(processed_uploads)
        m2 = mock.MagicMock()
        uploader.launcher = m2

        uploader.upload()
        self.assertTrue(m2.go.called)
        self.assertEqual(1, m2.go.call_count)

        # check database objects:
        all_transfers = Transfer.objects.all()
        all_resources = Resource.objects.all()
        all_tc = TransferCoordinator.objects.all()
        self.assertTrue(len(all_transfers) == 3)
        self.assertTrue(len(all_resources) == 3)
        self.assertTrue(len(all_tc) == 2)
        self.assertTrue(all([not x.completed for x in all_transfers])) # no transfer is complete
        self.assertTrue(all([not tc.completed for tc in all_tc])) # no transfer_coordinators are complete

    @mock.patch.dict('transfer_app.uploaders.os.environ', {'GCLOUD': '/mock/bin/gcloud'})
    def test_warn_of_conflict_case2(self):
        '''
        Here, we pretend that a user has previously started an upload that is still going.
        Then they try to upload the same files again
        '''
        
        source = settings.DROPBOX
        uploader_cls = uploaders.get_uploader(source)
        self.assertEqual(uploader_cls, uploaders.GoogleDropboxUploader)
        
        # prep the upload info as is usually performed:
        upload_info = []
        upload_info.append({'path': 'https://dropbox-link.com/1', 'name':'f1.txt', 'owner':2})
        upload_info.append({'path': 'https://dropbox-link.com/2', 'name':'f2.txt', 'owner':2})
        upload_info, error_messages = uploader_cls.check_format(upload_info, 2)

        self.assertEqual(len(upload_info), 2)
        self.assertEqual(len(error_messages), 0)
        
        # instantiate the class, but mock out the launcher.
        # Recall the launcher is the class that actually creates the worker VMs, which
        # we do not want to do as part of the test
        uploader = uploader_cls(upload_info)
        m = mock.MagicMock()
        uploader.launcher = m

        # mock launch of transfers, which creates the database objects
        uploader.upload()

        # prep the upload info as is usually performed:
        additional_uploads = []
        additional_uploads.append({'path': 'https://dropbox-link.com/2', 'name':'f2.txt', 'owner':2}) # same as above- so reject!
        additional_uploads.append({'path': 'https://dropbox-link.com/1', 'name':'f1.txt', 'owner':2})# same as above- reject
        processed_uploads, error_messages = uploader_cls.check_format(additional_uploads, 2)

        self.assertEqual(len(processed_uploads), 0)
        self.assertEqual(len(error_messages), 2)

        uploader = uploader_cls(processed_uploads)
        m2 = mock.MagicMock()
        uploader.launcher = m2

        uploader.upload()
        self.assertFalse(m2.go.called)

        # check database objects:
        all_transfers = Transfer.objects.all()
        all_resources = Resource.objects.all()
        all_tc = TransferCoordinator.objects.all()
        self.assertTrue(len(all_transfers) == 2)
        self.assertTrue(len(all_resources) == 2)
        self.assertTrue(len(all_tc) == 1) # this means no NEW coordinators were created for the 'empty' case
        self.assertTrue(all([not x.completed for x in all_transfers])) # no transfer is complete
        self.assertTrue(all([not tc.completed for tc in all_tc])) # no transfer_coordinators are complete

    @mock.patch.dict('transfer_app.uploaders.os.environ', {'GCLOUD': '/mock/bin/gcloud'})
    def test_warn_of_conflict_case3(self):
        '''
        Here, we initiate two transfers.  We mock one being completed, and THEN the user uploads another to the same
        as an overwrite.  We want to allow this.
        '''
        
        source = settings.DROPBOX
        uploader_cls = uploaders.get_uploader(source)
        self.assertEqual(uploader_cls, uploaders.GoogleDropboxUploader)
        
        # prep the upload info as is usually performed:
        upload_info = []
        upload_info.append({'path': 'https://dropbox-link.com/1', 'name':'f1.txt', 'owner':2})
        upload_info.append({'path': 'https://dropbox-link.com/2', 'name':'f2.txt', 'owner':2})
        upload_info, error_messages = uploader_cls.check_format(upload_info, 2)

        self.assertEqual(len(upload_info), 2)
        self.assertEqual(len(error_messages), 0)
        
        # instantiate the class, but mock out the launcher.
        # Recall the launcher is the class that actually creates the worker VMs, which
        # we do not want to do as part of the test
        uploader = uploader_cls(upload_info)
        m = mock.MagicMock()
        uploader.launcher = m

        # mock launch of transfers, which creates the database objects
        uploader.upload()

        # check database objects:
        all_transfers = Transfer.objects.all()
        all_resources = Resource.objects.all()
        all_tc = TransferCoordinator.objects.all()
        self.assertTrue(len(all_transfers) == 2)
        self.assertTrue(len(all_resources) == 2)
        self.assertTrue(len(all_tc) == 1) # this means no NEW coordinators were created for the 'empty' case
        self.assertTrue(all([not x.completed for x in all_transfers])) # no transfer is complete
        self.assertTrue(all([not tc.completed for tc in all_tc])) # no transfer_coordinators are complete

        # make the transfers 'complete'
        for t in all_transfers:
            t.completed = True
            t.save()
        for tc in all_tc:
            tc.completed = True
            tc.save()
        

        # prep the upload info as is usually performed:
        additional_uploads = []
        additional_uploads.append({'path': 'https://dropbox-link.com/2', 'name':'f2.txt', 'owner':2}) # same as above
        processed_uploads, error_messages = uploader_cls.check_format(additional_uploads, 2)

        self.assertEqual(len(processed_uploads), 1)
        self.assertEqual(len(error_messages), 0)

        uploader = uploader_cls(processed_uploads)
        m2 = mock.MagicMock()
        uploader.launcher = m2

        uploader.upload()
        self.assertTrue(m2.go.called)
        self.assertEqual(1, m2.go.call_count)

        # check database objects:
        all_transfers = Transfer.objects.all()
        all_resources = Resource.objects.all()
        all_tc = TransferCoordinator.objects.all()
        self.assertTrue(len(all_transfers) == 3)
        self.assertTrue(len(all_resources) == 3)
        self.assertTrue(len(all_tc) == 2)

        # count complete and incomplete:
        self.assertTrue(sum([not x.completed for x in all_transfers]) == 1)
        self.assertTrue(sum([x.completed for x in all_transfers]) == 2)
        self.assertTrue(sum([not tc.completed for tc in all_tc])==1)
        self.assertTrue(sum([tc.completed for tc in all_tc])==1)

