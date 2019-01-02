from django.urls import path, re_path

from . import views

urlpatterns = [

    # lists all AnalysisProject instances
    path('projects/', views.AnalysisProjectList.as_view(), name='analysis-project-list'),

    # API view that gives details about a particular AnalysisProject 
    # (NOT the endpoint for actually running an analysis!)
    path('projects/details/<uuid:analysis_uuid>/', views.AnalysisProjectDetail.as_view(), name='analysis-project-detail'),

    # a view where users can actually execute an AnalysisProject, which is different than 
    # the API view given above
    path('projects/<uuid:analysis_uuid>/', views.AnalysisView.as_view(), name='analysis-project-execute'),

    # endpoints for Workflows
    path('workflows/', views.WorkflowList.as_view(), name='workflow-list'),
    path('workflows/<int:pk>/', views.WorkflowDetail.as_view(), name='workflow-detail'),

    # endpoints for OrganizationWorkflows
    path('org-workflows/', views.OrganizationWorkflowList.as_view(), 
        name='org-workflow-list'
    ),
    path('org-workflows/<int:pk>/', views.OrganizationWorkflowDetail.as_view(), 
        name='org-workflow-detail'
    ),

    # for admin users to look at the workflow
    path('workflow-view/<int:workflow_id>/', 
        views.AnalysisView.as_view(), 
        name='latest_workflow_view'),

    # for admin users to look at the workflow (And dictate possible
    # subversion)
    path('workflow-view/<int:workflow_id>/<int:version_id>/', 
        views.AnalysisView.as_view(), 
        name='workflow_version_view'),
]
