from django.contrib.auth import views as original_auth_views 
from django.urls import re_path
from django.conf import settings

from rest_framework.urlpatterns import format_suffix_patterns

from custom_auth import views as custom_auth_views

urlpatterns = [
    # endpoints related to querying User info:
    re_path(r'^$', custom_auth_views.UserList.as_view(), name='user-list'),
    re_path(r'^(?P<pk>[0-9]+)/$', custom_auth_views.UserDetail.as_view(), name='user-detail'),
]
urlpatterns = format_suffix_patterns(urlpatterns)


