import inspect
from django.contrib import admin
from django.contrib.admin.sites import AlreadyRegistered

import analysis.models
from analysis.models import Workflow, \
    AnalysisProject, \
    SubmittedJob, \
    CompletedJob, \
    PendingWorkflow, \
    AnalysisProjectResource, \
    Warning, \
    JobClientError, \
    WorkflowConstraint, \
    ProjectConstraint, \
    ImplementedConstraint, \
    WorkflowContainer

class WorkflowAdmin(admin.ModelAdmin):
    list_display = ('workflow_name', 'workflow_id', 'version_id', 'is_default', 'is_active', 'workflow_title', 'workflow_short_description', 'workflow_long_description')
    list_editable = ('is_default', 'is_active', 'workflow_title', 'workflow_short_description')
    list_display_links = ('workflow_name',)


class AnalysisProjectAdmin(admin.ModelAdmin):
    list_display = ('analysis_uuid', 'workflow', 'owner', 'started', 'completed')
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
    list_display = ('workflow', 'name', 'implementation_class')
    list_display_links = ('workflow',)


class ProjectConstraintAdmin(admin.ModelAdmin):
    list_display = ('project', 'constraint')


class WorkflowContainerAdmin(admin.ModelAdmin):
    list_display = ('workflow', 'image_tag', 'hash_string')
    list_display_links = ('image_tag',)
    

# use an auto-register for the constraint fields that are children of the 
# ImplementedConstraint class.  This way we can see the constraints in the 
# admin interface, but do not have to continuously update this module
# when potentially new constraint classes are added

constraint_classnames = []
for name, obj in inspect.getmembers(analysis.models):
    if inspect.isclass(obj):
        if obj.__base__ == ImplementedConstraint:
            constraint_classnames.append(name)
for c in constraint_classnames:
    clazz = getattr(analysis.models, c)
    field_list = [f.name for f in clazz._meta.get_fields() if f.auto_created == False]
    new_admin = type('NewAdmin', (admin.ModelAdmin,), {'list_display': field_list})
    try:
        admin.site.register(clazz, new_admin)
    except AlreadyRegistered:
        pass


admin.site.register(Workflow, WorkflowAdmin)
admin.site.register(WorkflowContainer, WorkflowContainerAdmin)
admin.site.register(ProjectConstraint, ProjectConstraintAdmin)
#admin.site.register(ImplementedConstraint, ImplementedConstraintAdmin)
admin.site.register(WorkflowConstraint, WorkflowConstraintAdmin)
admin.site.register(PendingWorkflow, PendingWorkflowAdmin)
admin.site.register(AnalysisProject, AnalysisProjectAdmin)
admin.site.register(AnalysisProjectResource, AnalysisProjectResourceAdmin)
admin.site.register(SubmittedJob, SubmittedJobAdmin)
admin.site.register(Warning, WarningAdmin)
admin.site.register(CompletedJob, CompletedJobAdmin)
admin.site.register(JobClientError, JobClientErrorAdmin)
