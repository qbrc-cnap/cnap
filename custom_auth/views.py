
from django.contrib.auth.views import PasswordResetView
from django.contrib.auth import get_user_model

from rest_framework import generics, permissions

from custom_auth.forms import CustomPasswordResetForm
from custom_auth.serializers import UserSerializer


class CustomPasswordResetView(PasswordResetView): 
    form_class = CustomPasswordResetForm
    html_email_template_name = 'registration/password_reset_email.html'


class UserList(generics.ListCreateAPIView):
    '''
    This allows:
        GET: listing of all Users
        POST: create new User

    This view is limited to users with elevated/admin privileges
    '''
    queryset = get_user_model().objects.all()
    serializer_class = UserSerializer
    permission_classes = (permissions.IsAdminUser,)


class UserDetail(generics.RetrieveUpdateDestroyAPIView):
    '''
    This allows:
        GET: details of specific User
        PUT: edit details of the User
        DELETE: remove User

    This view is limited to users with elevated/admin privileges
    '''
    queryset = get_user_model().objects.all()
    serializer_class = UserSerializer
    permission_classes = (permissions.IsAdminUser,)
