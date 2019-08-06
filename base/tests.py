import unittest.mock as mock
import os
import string
import random
import json

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from django.conf import settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.conf import settings

from base.models import Resource
from base.tasks import manage_files

import datetime

# a method for creating a reasonable test dataset:
def create_data(testcase_obj):

    # create two users-- one is admin, other is regular
    testcase_obj.regular_user = get_user_model().objects.create_user(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')
    testcase_obj.admin_user = get_user_model().objects.create_user(email=settings.ADMIN_TEST_EMAIL, password='abcd123!', is_staff=True)
    testcase_obj.other_user = get_user_model().objects.create_user(email=settings.OTHER_TEST_EMAIL, password='abcd123!')

    # create a couple of Resources owned by admin:
    r1 = Resource.objects.create(
        source = 'google_bucket',
        path='gs://a/b/admin_owned1.txt',
        size=500,
        name = 'admin_owned1.txt',
        owner=testcase_obj.admin_user,
    )

    r2 = Resource.objects.create(
        source='google_storage',
        path='in some user dropbox1',
        size=500,
        owner=testcase_obj.admin_user,
    )

    # create a couple of resources owned by the regular user:
    r3 = Resource.objects.create(
        source='google_storage',
        path='gs://a/b/reg_owned1.txt',
        size=500,
        name = 'reg_owned1.txt',
        owner=testcase_obj.regular_user,
    )
    r4 = Resource.objects.create(
        source='google_storage',
        path='gs://a/b/reg_owned2.txt',
        size=500,
        name = 'reg_owned2.txt',
        owner=testcase_obj.regular_user,
    )
    r5 = Resource.objects.create(
        source='google_storage',
        path='in some user dropbox2',
        size=500,
        owner=testcase_obj.regular_user
    )

# Tests related to Resource listing/creation/retrieval:

'''
Tests for listing Resources:
  -lists all Resources for admin user
  -lists Resources specific to a non-admin user
  - only admin can access the UserResourceList endpoint
    which allows admins to query all Resource objects owned by
    a particular user
'''
class ResourceListTestCase(TestCase):
    def setUp(self):
        create_data(self)

    def test_admin_can_list_all_resources(self):
        r = Resource.objects.all()
        client = APIClient()
        client.login(email=settings.ADMIN_TEST_EMAIL, password='abcd123!') 
        url = reverse('resource-list')
        response = client.get(url)
        self.assertEqual(response.status_code,200) 
        self.assertEqual(len(response.data), len(r))

    def test_regular_user_can_list_only_their_resources(self):
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')
        u = get_user_model().objects.filter(email=settings.REGULAR_TEST_EMAIL)[0]
        reguser_pk = u.pk
        url = reverse('resource-list')
        response = client.get(url)
        data = response.data

        # test that we received 200, there are two resources, and they both
        # are owned by the 'regular' user
        self.assertEqual(response.status_code,200) 
        self.assertEqual(len(response.data), 3)
        self.assertTrue(all([x.get('owner') == reguser_pk for x in data]))

    def test_unauthenticated_user_gets_403_for_basic_list(self):
        client = APIClient()
        url = reverse('resource-list')
        response = client.get(url)
        self.assertEqual(response.status_code, 403)

'''

Tests for creation of Resource:
  - Admin user can create Resource for themself
  - Non-admin user can create Resource for themself
  - Admin user can create Resource for someone else
  - Non-admin user is blocked from creating Resource
    for others
'''
class ResourceCreateTestCase(TestCase):
    def setUp(self):
        self.regular_user = get_user_model().objects.create_user(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')
        self.admin_user = get_user_model().objects.create_user(email=settings.ADMIN_TEST_EMAIL, password='abcd123!', is_staff=True)

    def test_admin_can_create_resource_for_self(self):
        # establish the admin client:
        client = APIClient()
        client.login(email=settings.ADMIN_TEST_EMAIL, password='abcd123!')

        # get the admin user's pk:
        u = get_user_model().objects.filter(email=settings.ADMIN_TEST_EMAIL)[0]
        adminuser_pk = u.pk
        url = reverse('resource-list')
        data = {'source': 'google_bucket', \
                'path': 'gs://foo/bar/baz.txt', \
                'name': 'baz.txt', \
                'size':500, \
                'owner': adminuser_pk, \
                'is_active': True
        }
        response = client.post(url, data, format='json')
        self.assertEqual(response.status_code, 201)  

        r = Resource.objects.all()
        self.assertEqual(len(r), 1)
        self.assertTrue(all([x.get_owner() == u for x in r]))

    def test_admin_can_create_resource_for_other(self):
        # establish the admin client:
        client = APIClient()
        client.login(email=settings.ADMIN_TEST_EMAIL, password='abcd123!')

        # get the regular user's pk:
        u = get_user_model().objects.filter(email=settings.REGULAR_TEST_EMAIL)[0]
        reguser_pk = u.pk
        url = reverse('resource-list')
        data = {'source': 'google_bucket', \
                'path': 'gs://foo/bar/baz.txt', \
                'name': 'baz.txt', \
                'size':500, \
                'owner': reguser_pk, \
                'is_active': True
        }
        response = client.post(url, data, format='json')
        self.assertEqual(response.status_code, 201)  

        r = Resource.objects.all()
        self.assertEqual(len(r), 1)
        self.assertTrue(all([x.get_owner() == u for x in r]))

    def test_regular_user_can_create_resource_for_self(self):
        # establish the regular client:
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        # initial number of Resource objects:
        r_orig = Resource.objects.all()
        r_orig_len = len(r_orig)

        # get the regular user's pk:
        u = get_user_model().objects.filter(email=settings.REGULAR_TEST_EMAIL)[0]
        reguser_pk = u.pk
        url = reverse('resource-list')
        data = {'source': 'google_bucket', \
                'path': 'gs://foo/bar/baz.txt', \
                'name': 'baz.txt', \
                'size':500, \
                'owner': reguser_pk, \
                'is_active': True
        }
        response = client.post(url, data, format='json')
        self.assertEqual(response.status_code, 201)  

        r = Resource.objects.all()
        self.assertEqual(r_orig_len + 1, len(r))
        self.assertTrue(all([x.get_owner() == u for x in r]))

    def test_regular_user_cannot_create_resource_for_other(self):
        # establish the regular client:
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        # initial number of Resource objects:
        r_orig = Resource.objects.all()

        # get the admin user's pk:
        u = get_user_model().objects.filter(email=settings.ADMIN_TEST_EMAIL)[0]
        adminuser_pk = u.pk
        url = reverse('resource-list')
        data = {'source': 'google_bucket', \
                'path': 'gs://foo/bar/baz.txt', \
                'name': 'baz.txt', \
                'size':500, \
                'owner': adminuser_pk, \
                'is_active': True
        }
        response = client.post(url, data, format='json')
        self.assertEqual(response.status_code, 404)  

        r = Resource.objects.all()
        self.assertEqual(len(r_orig), len(r))



'''
Test for listing specific Resource:
  - returns 404 if the pk does not exist regardless of user
  - returns 404 if a non-admin user requests a Resource
    owned by someone else
  - returns correctly if admin requests Resource owned by someone else
  - returns correctly if admin requests Resource owned by themself
'''
class ResourceDetailTestCase(TestCase):
    def setUp(self):
        create_data(self)

    def test_return_404_for_missing_resource(self):

        admin_client = APIClient()
        admin_client.login(email=settings.ADMIN_TEST_EMAIL, password='abcd123!') 
        url = reverse('resource-detail', args=[666,]) # some non-existant pk
        response = admin_client.get(url)
        self.assertEqual(response.status_code,404) 

        reg_client = APIClient()
        reg_client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!') 
        url = reverse('resource-detail', args=[666,]) # some non-existant pk
        response = reg_client.get(url)
        self.assertEqual(response.status_code,404)

    def test_admin_user_can_query_own_resource(self):
        admin_user = get_user_model().objects.get(email=settings.ADMIN_TEST_EMAIL)
        r = Resource.objects.filter(owner = admin_user)
        instance = r[0]
        admin_client = APIClient()
        admin_client.login(email=settings.ADMIN_TEST_EMAIL, password='abcd123!') 
        url = reverse('resource-detail', args=[instance.pk,])
        response = admin_client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_admin_user_can_query_others_resource(self):
        reg_user = get_user_model().objects.get(email=settings.REGULAR_TEST_EMAIL)
        r = Resource.objects.filter(owner = reg_user)
        instance = r[0]
        admin_client = APIClient()
        admin_client.login(email=settings.ADMIN_TEST_EMAIL, password='abcd123!')
        url = reverse('resource-detail', args=[instance.pk,])
        response = admin_client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_regular_user_denied_access_to_others_resource(self):
        admin_user = get_user_model().objects.get(email=settings.ADMIN_TEST_EMAIL)
        r = Resource.objects.filter(owner = admin_user)
        instance = r[0]
        reg_client = APIClient()
        reg_client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!') 
        url = reverse('resource-detail', args=[instance.pk,])
        response = reg_client.get(url)
        self.assertEqual(response.status_code,404)

    def test_regular_user_given_access_to_own_resource(self):
        reg_user = get_user_model().objects.get(email=settings.REGULAR_TEST_EMAIL)
        r = Resource.objects.filter(owner = reg_user)
        instance = r[0]
        reg_client = APIClient()
        reg_client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!') 
        url = reverse('resource-detail', args=[instance.pk,])
        response = reg_client.get(url)
        self.assertEqual(response.status_code, 200)

'''
Tests for UserResourceList:
  - non-admin receives 403
  - using a pk that does not exist returns a 404
  - properly returns a list of Resources for a particular owner
'''
class UserResourceListTestCase(TestCase):
    def setUp(self):
        create_data(self)

    def test_404_from_nonexistent_user(self):

        # query all existing users, get the max pk, then add 1
        # to guarantee a non-existent user's pk
        all_users = get_user_model().objects.all()
        all_user_pks = [x.pk for x in all_users]
        max_pk = max(all_user_pks)
        nonexistent_user_pk = max_pk + 1

        admin_client = APIClient()
        admin_client.login(email=settings.ADMIN_TEST_EMAIL, password='abcd123!') 
        url = reverse('user-resource-list', args=[nonexistent_user_pk,])
        response = admin_client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_non_admin_user_gets_403_for_user_specific_list(self):
        '''
        regular users cannot access the /resources/user/<user pk>/ endpoint
        which lists the resources belonging to a specific user.  That
        functionality is already handled by a request to the /resources/ endpoint
        '''
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        # get the regular user's pk:
        u = get_user_model().objects.filter(email=settings.REGULAR_TEST_EMAIL)[0]
        reguser_pk = u.pk

        url = reverse('user-resource-list', args=[reguser_pk])
        response = client.get(url)
        self.assertEqual(response.status_code,403)

    def test_admin_user_correctly_can_get_user_specific_list(self):

        # establish the admin client:
        client = APIClient()
        client.login(email=settings.ADMIN_TEST_EMAIL, password='abcd123!')

        # get the regular user's pk:
        u = get_user_model().objects.filter(email=settings.REGULAR_TEST_EMAIL)[0]
        reguser_pk = u.pk

        url = reverse('user-resource-list', args=[reguser_pk])
        response = client.get(url)
        data = response.data
        self.assertEqual(response.status_code,200) 
        self.assertEqual(len(response.data), 3)
        self.assertTrue(all([x.get('owner') == reguser_pk for x in data]))  


class ResourceExpirationTestCase(TestCase):

    def setUp(self):
        self.regular_user = get_user_model().objects.create_user(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        today = datetime.date.today()

        # create a Resource that will remain active
        r1 = Resource.objects.create(
            source = 'google_bucket',
            path='gs://a/b/f1.txt',
            name = 'f1.txt',
            size=500,
            owner=self.regular_user
        )
    
        # create a Resource that will remain end up being marked inactive
        r2 = Resource.objects.create(
            source = 'google_bucket',
            path='gs://a/b/f2.txt',
            name = 'f2.txt',
            size=500,
            owner=self.regular_user,
            expiration_date = today - datetime.timedelta(days=3)
        )

        # create a couple of Resources that will be removed on one of the notification dates:
        d = settings.EXPIRATION_REMINDER_DAYS[0]
        r3 = Resource.objects.create(
            source = 'google_bucket',
            path='gs://a/b/f3.txt',
            name = 'f3.txt',
            size=500,
            owner=self.regular_user,
            expiration_date = today + datetime.timedelta(days=d)
        )
        r4 = Resource.objects.create(
            source = 'google_bucket',
            path='gs://a/b/f4.txt',
            name = 'f4.txt',
            size=500,
            owner=self.regular_user,
            expiration_date = today + datetime.timedelta(days=d)
        )

        # another Resource marked for the other notification date:
        d = settings.EXPIRATION_REMINDER_DAYS[1]
        r5 = Resource.objects.create(
            source = 'google_bucket',
            path='gs://a/b/f5.txt',
            name = 'f5.txt',
            size=500,
            owner=self.regular_user,
            expiration_date = today + datetime.timedelta(days=d)
        )
        
    @mock.patch('base.tasks.send_reminder')
    def test_marks_expired(self, mock_reminder):
        r = Resource.objects.filter(is_active = False)
        self.assertEqual(len(r), 0)
        manage_files()
        r = Resource.objects.filter(is_active = False)
        self.assertEqual(len(r), 1)

    @mock.patch('base.tasks.send_reminder')
    def test_notifies_of_pending_removal(self, mock_reminder):
        manage_files()
        expected_data = {
            settings.EXPIRATION_REMINDER_DAYS[0]: ['f3.txt', 'f4.txt'],
            settings.EXPIRATION_REMINDER_DAYS[1]: ['f5.txt',],
        }
        mock_reminder.assert_called_with(self.regular_user, expected_data)


class ResourceRenamingTestCase(TestCase):

    def setUp(self):
        create_data(self)

    def test_cannot_rename_others_files(self):
        other_client = APIClient()
        other_client.login(email=settings.OTHER_TEST_EMAIL, password='abcd123!')

        # get a resource owned by the 'regular' user:
        resources = Resource.objects.filter(owner=self.regular_user)
        r = resources[0]
        pk = r.pk
        original_name = r.name
        original_path = r.path
        data = {'new_name': 'foo.txt'}
        url = reverse('resource-rename', args=[pk,])
        response = other_client.post(url, data, format='json')
        self.assertEqual(response.status_code, 404)

        # query to ensure that nothing was changed:
        r2 = Resource.objects.get(pk=pk)
        self.assertEqual(r2.path, original_path)
        self.assertEqual(r2.name, original_name)

    def test_bad_pk_issues_error(self):
        '''
        The primary key is part of the URL, but if it does not exist, issue error
        '''
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        # get all resources
        all_resources = Resource.objects.all()
        all_pks = [x.pk for x in all_resources]
        nonexistent_pk = max(all_pks) + 1

        data = {'new_name': 'foo.txt'}
        url = reverse('resource-rename', args=[nonexistent_pk,])
        response = client.post(url, data, format='json')
        self.assertEqual(response.status_code, 404)


    def test_returns_error_if_name_violates_length_constraint_case1(self):
        '''
        If the name is too long for the storage service, return an error
        '''
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        # get all resources owned by the regular user
        all_user_resources = Resource.objects.filter(owner = self.regular_user)
        pk = all_user_resources[0].pk

        # for google, length needs to be 1-1024 bytes when UTF-8 encoded
        N = 2000
        very_long_name = ''.join([random.choice(string.ascii_lowercase) for x in range(N)])
        data = {'new_name': very_long_name}
        url = reverse('resource-rename', args=[pk,])
        response = client.post(url, data, format='json')
        self.assertEqual(response.status_code, 400)


    def test_returns_error_if_name_violates_length_constraint_case2(self):
        '''
        If the name is too short/empty for the storage service, return an error
        '''
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        # get all resources owned by the regular user
        all_user_resources = Resource.objects.filter(owner = self.regular_user)
        pk = all_user_resources[0].pk

        url = reverse('resource-rename', args=[pk,])

        # for google, length needs to be 1-1024 bytes when UTF-8 encoded
        data = {'new_name': 'a'}
        response = client.post(url, data, format='json')
        self.assertEqual(response.status_code, 400)

        data = {'new_name': ''}
        response = client.post(url, data, format='json')
        self.assertEqual(response.status_code, 400)


    def test_returns_error_if_name_is_not_alnum(self):
        '''
        If the name has non-alphanumeric chars, issue error
        '''
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        # get all resources owned by the regular user
        all_user_resources = Resource.objects.filter(owner = self.regular_user)
        pk = all_user_resources[0].pk

        url = reverse('resource-rename', args=[pk,])

        data = {'new_name': 'a+.txt'}
        response = client.post(url, data, format='json')
        self.assertEqual(response.status_code, 400)


    @mock.patch('base.views.storage')
    def test_normalizes_path(self, mock_storage):
        '''
        Tests cases where users put space in the name-- make them underscores
        '''
        mock_storage_client = mock.MagicMock()
        mock_bucket = mock.MagicMock()
        mock_bucket.get_blob.return_value = mock.MagicMock()
        mock_bucket.rename_blob.return_value = None
        mock_storage_client.get_bucket.return_value = mock_bucket
        mock_storage.Client.return_value = mock_storage_client

        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        # get all resources owned by the regular user
        all_user_resources = Resource.objects.filter(owner = self.regular_user)
        pk = all_user_resources[0].pk
        original_name = all_user_resources[0].name 
        original_path = all_user_resources[0].path 

        url = reverse('resource-rename', args=[pk,])

        data = {'new_name': 'some name.txt'}
        response = client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200)

        # check that rename happened with normalization:
        r = Resource.objects.get(pk=pk)
        new_name = r.name 
        new_path = r.path
        expected_new_name = 'some_name.txt'
        expected_new_path = os.path.join(os.path.dirname(original_path), expected_new_name)
        self.assertEqual(new_name, expected_new_name)
        self.assertEqual(new_path, expected_new_path)


    def test_nonunique_path_issues_error(self):
        '''
        If the name already exists, issue error
        '''
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        # get all resources owned by the regular user
        all_user_resources = Resource.objects.filter(owner = self.regular_user)
        resource1 = all_user_resources[0]
        resource2 = all_user_resources[1]
        pk = resource1.pk
        # sort of a meta-test: for the test to work properly, both resources need to have
        # the same bucket
        self.assertEqual(os.path.dirname(resource1.path), os.path.dirname(resource2.path))

        # now that we know both resources have the same bucket, pretend the user
        # is renaming resource1 and it will exactly match resource2
        new_name = resource2.name
        self.assertTrue(len(new_name) > 1)

        # for google, length needs to be 1-1024 bytes when UTF-8 encoded
        url = reverse('resource-rename', args=[pk,])

        data = {'new_name': new_name}
        response = client.post(url, data, format='json')
        self.assertEqual(response.status_code, 400)

        # ensure nothing changed:
        r = Resource.objects.get(pk=pk)
        self.assertEqual(r.name, resource1.name)
        self.assertEqual(r.path, resource1.path)


    @mock.patch('base.views.storage')
    def test_successful_change(self, mock_storage):
        '''
        Tests that the database objects change appropriately
        ''' 
        mock_storage_client = mock.MagicMock()
        mock_bucket = mock.MagicMock()
        mock_bucket.get_blob.return_value = mock.MagicMock()
        mock_bucket.rename_blob.return_value = None
        mock_storage_client.get_bucket.return_value = mock_bucket
        mock_storage.Client.return_value = mock_storage_client

        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        # get all resources owned by the regular user
        all_user_resources = Resource.objects.filter(owner = self.regular_user)
        all_names = [x.name for x in all_user_resources]
        proposed_new_name = 'abcefgh.txt'
        self.assertTrue(all([proposed_new_name not in all_names])) # another "meta-test" --need to ensure we are, in fact, proposing a unique name

        pk = all_user_resources[0].pk
        original_name = all_user_resources[0].name 
        original_path = all_user_resources[0].path 

        url = reverse('resource-rename', args=[pk,])

        data = {'new_name': proposed_new_name}
        response = client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200)

        # check that rename happened:
        r = Resource.objects.get(pk=pk)
        new_name = r.name 
        new_path = r.path
        expected_new_name = proposed_new_name
        expected_new_path = os.path.join(os.path.dirname(original_path), expected_new_name)
        self.assertEqual(new_name, expected_new_name)
        self.assertEqual(new_path, expected_new_path)


    def test_bad_payload_issues_error(self):
        '''
        Tests the case where the payload is missing
        some data
        '''
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        # get all resources owned by the regular user
        all_user_resources = Resource.objects.filter(owner = self.regular_user)
        pk = all_user_resources[0].pk

        url = reverse('resource-rename', args=[pk,])

        # mess-up the payload:
        data = {'new_nameXYZ': 'a.txt'}
        response = client.post(url, data, format='json')
        self.assertEqual(response.status_code, 400)
