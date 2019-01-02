from django.urls import re_path
from rest_framework.urlpatterns import format_suffix_patterns

from base import views

urlpatterns = [
    # endpoints related to querying Organizations:
    re_path(r'^$', views.OrganizationList.as_view(), name='organization-list'),
    re_path(r'^(?P<pk>[0-9]+)/$', views.OrganizationDetail.as_view(), name='organization-detail'),
]
urlpatterns = format_suffix_patterns(urlpatterns)
