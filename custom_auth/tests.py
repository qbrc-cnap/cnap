from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.conf import settings

def create_data(testcase_obj):

    # create two users-- one is admin, other is regular
    testcase_obj.regular_user = get_user_model().objects.create_user(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')
    testcase_obj.admin_user = get_user_model().objects.create_user(email=settings.ADMIN_TEST_EMAIL, password='abcd123!', is_staff=True)
    testcase_obj.other_user = get_user_model().objects.create_user(email=settings.OTHER_TEST_EMAIL, password='abcd123!')


'''
Tests for listing Users:
  - admin users can list all users
  - admin users can list info about specific user
  - non-admin users do not have access to anything (returns 403)
'''
class UserListTestCase(TestCase):
    def setUp(self):
        create_data(self)

    def test_list_all_users_by_admin(self):
        # establish the admin client:
        client = APIClient()
        client.login(email=settings.ADMIN_TEST_EMAIL, password='abcd123!')        

        url = reverse('user-list')
        response = client.get(url)
        data = response.data
        self.assertEqual(response.status_code,200) 
        self.assertEqual(len(data), 3)

    def test_list_specific_user_by_admin(self):
        # establish the admin client:
        client = APIClient()
        client.login(email=settings.ADMIN_TEST_EMAIL, password='abcd123!')        

        # get the regular user's pk:
        u = get_user_model().objects.filter(email=settings.REGULAR_TEST_EMAIL)[0]
        reguser_pk = u.pk

        url = reverse('user-detail', args=[reguser_pk])
        response = client.get(url)
        data = response.data
        self.assertEqual(response.status_code,200) 
        self.assertEqual(data['email'], settings.REGULAR_TEST_EMAIL)

    def test_regular_user_cannot_list_users(self):
        # establish a "regular" client:
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')        

        # check that querying all users is blocked:
        url = reverse('user-list')
        response = client.get(url)
        data = response.data
        self.assertEqual(response.status_code,403)

        # Now check that they cannot check even their own data:
        # get the regular user's pk:
        u = get_user_model().objects.filter(email=settings.REGULAR_TEST_EMAIL)[0]
        reguser_pk = u.pk

        url = reverse('user-detail', args=[reguser_pk])
        response = client.get(url)
        data = response.data
        self.assertEqual(response.status_code,403) 


'''
Tests for creating Users:
  - admin user can create a user with a specific username/email/pwd
  - non-admin users do not have access to anything (returns 403)
'''
class UserCreateTestCase(TestCase):
    def setUp(self):
        create_data(self)

    def test_admin_can_create_user(self):
        # establish the admin client:
        client = APIClient()
        client.login(email=settings.ADMIN_TEST_EMAIL, password='abcd123!')

        # get the admin user's pk:
        u = get_user_model().objects.filter(email=settings.ADMIN_TEST_EMAIL)[0]
        adminuser_pk = u.pk

        url = reverse('user-list')
        data = {'email':settings.YET_ANOTHER_TEST_EMAIL, \
                'password': 'abcd123!', \
        }
        response = client.post(url, data, format='json')
        self.assertEqual(response.status_code, 201)  

        u = get_user_model().objects.filter(email=settings.YET_ANOTHER_TEST_EMAIL)
        self.assertEqual(len(u), 1)

    def test_no_duplicate_user(self):
        # establish the admin client:
        client = APIClient()
        client.login(email=settings.ADMIN_TEST_EMAIL, password='abcd123!')

        # get the admin user's pk:
        u = get_user_model().objects.filter(email=settings.ADMIN_TEST_EMAIL)[0]
        adminuser_pk = u.pk

        url = reverse('user-list')
        data = {'email':settings.OTHER_TEST_EMAIL, \
                'password': 'abcd123!', \
        }
        response = client.post(url, data, format='json')
        self.assertEqual(response.status_code, 400)  


    def test_regular_user_cannot_create_user(self):
        # establish the admin client:
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        # get the admin user's pk:
        u = get_user_model().objects.filter(email=settings.ADMIN_TEST_EMAIL)[0]
        adminuser_pk = u.pk

        url = reverse('user-list')
        data = {'email':settings.YET_ANOTHER_TEST_EMAIL, \
                'password': 'abcd123!', \
        }
        response = client.post(url, data, format='json')
        self.assertEqual(response.status_code, 403)  


'''
Tests for User deletion:
  - deletion of User causes deletion of all associated entities
  - non-admin cannot delete users
'''
class UserDeleteTestCase(TestCase):
    def setUp(self):
        create_data(self)

    def test_admin_can_delete_user(self):
        # establish the admin client:
        client = APIClient()
        client.login(email=settings.ADMIN_TEST_EMAIL, password='abcd123!')

        u = get_user_model().objects.filter(email=settings.REGULAR_TEST_EMAIL)
        self.assertEqual(len(u), 1)

        # get the reg user's pk:
        u = get_user_model().objects.filter(email=settings.REGULAR_TEST_EMAIL)[0]
        reguser_pk = u.pk

        url = reverse('user-detail', args=[reguser_pk,])
        response = client.delete(url)  
        u = get_user_model().objects.filter(email=settings.REGULAR_TEST_EMAIL)
        self.assertEqual(len(u), 0)

    def test_reguser_cannot_delete_user(self):
        # establish the admin client:
        client = APIClient()
        client.login(email=settings.REGULAR_TEST_EMAIL, password='abcd123!')

        u = get_user_model().objects.filter(email=settings.OTHER_TEST_EMAIL)
        self.assertEqual(len(u), 1)
        otheruser_pk = u[0].pk

        url = reverse('user-detail', args=[otheruser_pk,])
        response = client.delete(url)  
        self.assertEqual(response.status_code, 403)

