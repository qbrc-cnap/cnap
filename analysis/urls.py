from django.urls import path, re_path

from . import views

urlpatterns = [

    # lists all AnalysisProject instances
    path('projects/', views.AnalysisProjectList.as_view(), name='analysis-project-list'),

    # API view that gives details about a particular AnalysisProject 
    # (NOT the endpoint for actually running an analysis!)
    path('projects/details/<uuid:analysis_uuid>/', views.AnalysisProjectDetail.as_view(), name='analysis-project-detail'),

    # a view where users can restart an AnalysisProject if they input bad data
    path('projects/<uuid:analysis_uuid>/restart/', views.AnalysisRestartView.as_view(), name='analysis-project-restart'),

    # a view where users can actually execute an AnalysisProject, which is different than 
    # the API view given above
    path('projects/<uuid:analysis_uuid>/', views.AnalysisView.as_view(), name='analysis-project-execute'),

    # a view to create AnalysisProject instances for admins
    path('projects/create/', views.AnalysisProjectCreateView.as_view(), name='analysis-project-create'),

    # endpoints for Workflows
    path('workflows/', views.WorkflowList.as_view(), name='workflow-list'),
    path('workflows/<int:pk>/', views.WorkflowDetail.as_view(), name='workflow-detail'),

    # endpoints for PEndingWorkflows
    path('pending-workflows/', views.PendingWorkflowList.as_view(), name='pending-workflow-list'),
    path('pending-workflows/<int:pk>/', views.PendingWorkflowDetail.as_view(), name='pending-workflow-detail'),

    # endpoint for querying constraints
    path('workflow-constraints/', views.WorkflowConstraintList.as_view(), name='workflow-constraints'),
    path('workflow-constraints/<int:pk>', views.WorkflowConstraintRetrieveUpdateDestroy, name='workflow-constraints-details'),
    path('workflow-constraint-options/', views.get_constraint_options, name='workflow-constraint-options'),

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
