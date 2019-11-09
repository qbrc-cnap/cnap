from django.test import TestCase
from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse, HttpResponseNotAllowed
from django.contrib.auth import get_user_model


from .tasks import transfer_google_bucket
from .views import import_bucket

# Create your tests here.

# a class that acts like a django request object.
# Doesn't need to have all the bells and whistles, just
# the attributes
class Request(object):
    pass


class TestGoogleBucketImport(TestCase):
    '''
    This tests the dashboard functionality where we provide a gs://
    link to a bucket and the backend copies all the files to our 
    own bucket.
    '''
    def setUp(self):

        self.admin_user = get_user_model().objects.create_user(email=settings.ADMIN_TEST_EMAIL, password='abcd123!', is_staff=True)
        self.regular_user = get_user_model().objects.create_user(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

    def test_no_user_pk_returns400(self):
        '''
        The payload does not include a user primary key
        '''
        request = Request()
        request.user = self.admin_user
        request.method = 'POST'
        request.POST = {
            'bucket_url': 'gs://foo-bar'
        }
        r = import_bucket(request)
        self.assertTrue(type(r) is JsonResponse)
        self.assertTrue(r.status == 400)


    def test_bad_user_pk_returns400(self):
        '''
        The payload contains an invalid user primary key
        '''
        request = Request()
        request.user = self.admin_user
        request.method = 'POST'
        all_user_pks = [x.pk for x in get_user_model().objects.all()]
        max_pk = max(all_user_pks)
        bad_pk = max_pk + 1 # just to ensure we are not actually getting a valid PK
        request.POST = {
            'bucket_url': 'gs://foo-bar',
            'bucket_user': bad_pk
        }
        r = import_bucket(request)
        self.assertTrue(type(r) is JsonResponse)
        self.assertTrue(r.status == 400)


    def test_bad_payload_returns400(self):
        '''
        The payload does not include the "bucket_url key
        '''
        pass

    def test_nonadmin_request_is_denied(self):
        '''
        A non-admin attempts to do this operation- it is blocked
        '''
        pass

    def test_unrecognized_prefix_rejected(self):
        '''
        Since this is a google import, we expect the google prefix "gs://"
        If it is missing this, we reject with a message
        '''
        pass
    
    def test_bad_bucketname(self):
        '''
        A bucket name is given that is not found
        '''
        pass
    
    def test_no_permissions_to_access_bucket(self):
        '''
        A valid bucket path is given, but we do not have access to it.
        '''
        pass

    def test_valid_entrypoints_trigger_async_process(self):
        '''
        If the inputs are all good, test that we call the asynchronous process
        '''
        pass

    @mock.patch('dashboard.tasks.get_zone_as_string')
    @mock.patch('dashboard.tasks.send_email')
    @mock.patch('dashboard.tasks.do_google_copy')
    @mock.patch('analysis.tasks.storage')
    def test_user_bucket_created_if_not_existing(self, 
        mock_storage, mock_copy, mock_email_send, mock_zone_as_str):
        '''
        We are effectively adding files for a user.  If that user does not
        already have a bucket, test that we create one here.
        '''
        import google

        mock_client = mock.MagicMock()
        mock_storage.Client.return_value = mock_client

        mock_dest_bucket = mock.MagicMock()
        mock_get_bucket = mock.MagicMock()
        mock_get_bucket.side_effect=google.api_core.exceptions.NotFound()
        mock_client.get_bucket = mock_get_bucket
        mock_client.create_bucket.return_value = mock_dest_bucket

        # the mock storage bucket we will create
        mock_bucket_create = mock.MagicMock()
        mock_storage.Bucket.return_value = mock_bucket_create
        mock_zone_as_str.return_value = 'junk-zone'

        
        # mock_blobs will represent the files we are transferring
        mock_blob1 = mock.MagicMock()
        mock_blob1.name = 'something.txt'
        mock_blob2 = mock.MagicMock()
        mock_blob2.name = 'baz.txt'
        mock_blobs = [mock_blob1, mock_blob2]
        mock_client.list_blobs.return_value = mock_blobs

        # confirm that we have no initial Resources in the database:
        # Note that even though we are mocking adding to a bucket
        # that already has some files, we don't care whether those
        # are in the database or not.  All we care is that the new
        # resource is added.
        existing_resources = Resource.objects.all()
        self.assertTrue(len(existing_resources) == 0)

        # call the function we are testing:
        transfer_google_bucket(self.admin_user.pk, 
            self.regular_user.pk, 
            'junk'
        ):
        self.assertTrue(mock_copy.call_count == 2)
        self.assertTrue(mock_email_send.called)

        # check that we created a Resource for the
        # file that was not already there
        existing_resources = Resource.objects.all()
        self.assertTrue(len(existing_resources) == 2)

    @mock.patch('dashboard.tasks.send_email')
    @mock.patch('dashboard.tasks.do_google_copy')
    @mock.patch('analysis.tasks.storage')
    def test_calls_copy_and_adds_resources(self, 
        mock_storage, mock_copy, mock_email_send):
        '''
        By mocking out the blobs that are in another bucket, check that
        the proper calls are made to the copy function, the resources
        are added to the database, and the email is sent
        '''
        uploads_folder = settings.CONFIG_PARAMS['uploads_folder_name']
        class SimpleObject(object):
            def __init__(self, name):
                self.name = name

        mock_client = mock.MagicMock()
        mock_storage.Client.return_value = mock_client

        mock_dest_bucket = mock.MagicMock()
        mock_dest_bucket.list_blobs.return_value = [
            SimpleObject('%s/foo.txt' % uploads_folder),
            SimpleObject('%s/bar.txt' % uploads_folder)
        ]
        mock_get_bucket = mock.MagicMock(side_effect=[mock_dest_bucket, ])
        mock_client.get_bucket = mock_get_bucket
        
        # mock_blobs will represent the files we are transferring
        mock_blob1 = mock.MagicMock()
        mock_blob1.name = 'something.txt'
        mock_blob2 = mock.MagicMock()
        mock_blob2.name = 'baz.txt'
        mock_blobs = [mock_blob1, mock_blob2]
        mock_client.list_blobs.return_value = mock_blobs

        # confirm that we have no initial Resources in the database:
        # Note that even though we are mocking adding to a bucket
        # that already has some files, we don't care whether those
        # are in the database or not.  All we care is that the new
        # resource is added.
        existing_resources = Resource.objects.all()
        self.assertTrue(len(existing_resources) == 0)

        # call the function we are testing:
        transfer_google_bucket(self.admin_user.pk, 
            self.regular_user.pk, 
            'junk'
        ):
        self.assertTrue(mock_copy.call_count == 2)
        self.assertTrue(mock_email_send.called)

        # check that we created a Resource for the
        # file that was not already there
        existing_resources = Resource.objects.all()
        self.assertTrue(len(existing_resources) == 2)


    @mock.patch('dashboard.tasks.send_email')
    @mock.patch('dashboard.tasks.do_google_copy')
    @mock.patch('analysis.tasks.storage')
    def test_avoids_overwrite(self, mock_storage, 
        mock_copy, 
        mock_email_send):
        '''
        Each time we copy a file, we are checking to see if a file of the same
        name already exists at the destination.  If it does, we do NOT transfer
        so we do not overwrite.  In that case, we want to ensure that the copy
        function is not called and that we add this entry to the "failed" paths
        '''
        uploads_folder = settings.CONFIG_PARAMS['uploads_folder_name']
        class SimpleObject(object):
            def __init__(self, name):
                self.name = name

        mock_client = mock.MagicMock()
        mock_storage.Client.return_value = mock_client

        mock_dest_bucket = mock.MagicMock()
        mock_dest_bucket.list_blobs.return_value = [
            SimpleObject('%s/foo.txt' % uploads_folder),
            SimpleObject('%s/bar.txt' % uploads_folder)
        ]
        mock_get_bucket = mock.MagicMock(side_effect=[mock_dest_bucket, ])
        mock_client.get_bucket = mock_get_bucket
        
        # mock_blobs will represent the files we are transferring
        mock_blob1 = mock.MagicMock()
        mock_blob1.name = 'something.txt'
        mock_blob2 = mock.MagicMock()
        mock_blob2.name = 'foo.txt' # this will end up matching an "existing file"
        mock_blobs = [mock_blob1, mock_blob2]
        mock_client.list_blobs.return_value = mock_blobs

        # confirm that we have no initial Resources in the database:
        existing_resources = Resource.objects.all()
        self.assertTrue(len(existing_resources) == 0)

        # call the function we are testing:
        transfer_google_bucket(self.admin_user.pk, 
            self.regular_user.pk, 
            'junk'
        ):
        self.assertTrue(mock_copy.call_count == 1)
        self.assertTrue(mock_email_send.called)

        # check that we created a Resource for the
        # file that was not already there
        existing_resources = Resource.objects.all()
        self.assertTrue(len(existing_resources) == 1)
        self.assertTrue(existing_resources[0].name == 'something.txt')


    