from django.urls import path, re_path

from . import views

urlpatterns = [
    re_path('^$', views.home, name='home'),

    # if no particular version of a workflow is requested, use the default
    path('<int:workflow_id>/', 
        views.AnalysisView.as_view(), 
        name='latest_workflow_view'),

    # if we wish to expose particular versions of a workflow
    path('<int:workflow_id>/<int:version_id>/', 
        views.AnalysisView.as_view(), 
        name='workflow_version_view'),
]
