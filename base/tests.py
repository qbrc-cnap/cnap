from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from django.urls import reverse
from django.contrib.auth import get_user_model
from django.conf import settings

from base.models import Resource

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
        owner=testcase_obj.admin_user,
    )

    r2 = Resource.objects.create(
        source='google_storage',
        path='in some user dropbox',
        size=500,
        owner=testcase_obj.admin_user,
    )

    # create a couple of resources owned by the regular user:
    r3 = Resource.objects.create(
        source='google_storage',
        path='gs://a/b/reg_owned1.txt',
        size=500,
        owner=testcase_obj.regular_user,
    )
    r4 = Resource.objects.create(
        source='google_storage',
        path='gs://a/b/reg_owned2.txt',
        size=500,
        owner=testcase_obj.regular_user,
    )

    r5 = Resource.objects.create(
        source='google_storage',
        path='in some user dropbox',
        size=500,
        owner=testcase_obj.regular_user,
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
                'is_active': True,
                'expiration_date': '2018-12-02T00:00:00'
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
                'is_active': True,
                'expiration_date': '2018-12-02T00:00:00'
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
                'is_active': True,
                'expiration_date': '2018-12-02T00:00:00'
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
                'is_active': True,
                'expiration_date': '2018-12-02T00:00:00'
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
