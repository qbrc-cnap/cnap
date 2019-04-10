from django.contrib import admin

from .models import Workflow, \
    AnalysisProject, \
    SubmittedJob, \
    CompletedJob, \
    PendingWorkflow, \
    AnalysisProjectResource, \
    Warning, \
    JobClientError, \
    WorkflowConstraint

class WorkflowAdmin(admin.ModelAdmin):
    list_display = ('workflow_name', 'workflow_id', 'version_id', 'is_default', 'is_active', 'workflow_title', 'workflow_short_description', 'workflow_long_description')
    list_editable = ('is_default', 'is_active', 'workflow_title', 'workflow_short_description')
    list_display_links = ('workflow_name',)


class AnalysisProjectAdmin(admin.ModelAdmin):
    list_display = ('analysis_uuid', 'owner', 'started', 'completed')
    list_editable = ()
    list_display_links = ('analysis_uuid',)


class AnalysisProjectResourceAdmin(admin.ModelAdmin):
    list_display = ('analysis_project','resource')


class SubmittedJobAdmin(admin.ModelAdmin):
    list_display = ('job_id', 'job_status', 'job_staging_dir')
    list_editable = ()
    list_display_links = ('job_id',)


class WarningAdmin(admin.ModelAdmin):
    list_display = ('message',)


class CompletedJobAdmin(admin.ModelAdmin):
    list_display = ('job_id','job_status', 'project')
    list_display_links = ('project',)


class PendingWorkflowAdmin(admin.ModelAdmin):
    list_display = ('start_time','status','error','complete')


class JobClientErrorAdmin(admin.ModelAdmin):
    list_display = ('error_text',)


class WorkflowConstraintAdmin(admin.ModelAdmin):
    list_display = ('name', 'implementation_class')
    list_display_links = ('workflow',)

admin.site.register(Workflow, WorkflowAdmin)
admin.site.register(WorkflowConstraint, WorkflowConstraintAdmin)
admin.site.register(PendingWorkflow, PendingWorkflowAdmin)
admin.site.register(AnalysisProject, AnalysisProjectAdmin)
admin.site.register(AnalysisProjectResource, AnalysisProjectResourceAdmin)
admin.site.register(SubmittedJob, SubmittedJobAdmin)
admin.site.register(Warning, WarningAdmin)
admin.site.register(CompletedJob, CompletedJobAdmin)
admin.site.register(JobClientError, JobClientErrorAdmin)
