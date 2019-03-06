from django.urls import re_path
from rest_framework.urlpatterns import format_suffix_patterns

from base import views

'''
For all the endpoints given here, consult the specific view for
details about the actual methods they support, and what sorts of 
info they provide back
'''
urlpatterns = [
    # endpoints related to querying Resources:
    re_path(r'^$', views.ResourceList.as_view(), name='resource-list'),
    re_path(r'^(?P<pk>[0-9]+)/$', views.ResourceDetail.as_view(), name='resource-detail'),
    re_path(r'^user/(?P<user_pk>[0-9]+)/$', views.UserResourceList.as_view(), name='user-resource-list'),
    re_path(r'^tree/$', views.get_tree_ready_resources, name='resource-list-tree'),
]
urlpatterns = format_suffix_patterns(urlpatterns)
