from django.contrib import admin

from .models import Workflow

class WorkflowAdmin(admin.ModelAdmin):
    list_display = ('workflow_name', 'workflow_id', 'version_id', 'is_default', 'is_active', 'workflow_title', 'workflow_short_description', 'workflow_long_description')
    list_editable = ('is_default', 'is_active', 'workflow_title', 'workflow_short_description')
    list_display_links = ('workflow_name',)

admin.site.register(Workflow, WorkflowAdmin)
