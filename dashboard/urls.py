from django.urls import re_path, path

from dashboard import views as dashboard_views
'''
For all the endpoints given here, consult the specific view for
details about the actual methods they support, and what sorts of 
info they provide back
'''
urlpatterns = [
    re_path(r'^$', dashboard_views.dashboard_index, name='dashboard-home'),
    path(r'add-new-workflow', dashboard_views.add_new_workflow, name='dashboard-add-workflow'),
]
