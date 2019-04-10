from rest_framework import serializers

from analysis.models import Workflow, \
    AnalysisProject, \
    AnalysisProjectResource, \
    OrganizationWorkflow, \
    PendingWorkflow, 
    WorkflowConstraint

class WorkflowSerializer(serializers.ModelSerializer):

    class Meta:
        model = Workflow
        fields = ('workflow_id', \
                  'version_id', \
                  'git_commit_hash', \
                  'git_url', \
                  'workflow_name', \
                  'workflow_title', \
                  'workflow_short_description', \
                  'workflow_long_description', \
                  'is_default', \
                  'is_active' \
        )


class PendingWorkflowSerializer(serializers.ModelSerializer):
    class Meta:
        model = PendingWorkflow
        fields = ( 'clone_url', \
                   'commit_hash', \
                   'status', \
                   'error', \
                   'complete', \
                   'staging_directory', \
                   'start_time', \
                   'finish_time', \
        )


class AnalysisProjectSerializer(serializers.ModelSerializer):
    workflow = WorkflowSerializer(many=False, read_only=True)
    class Meta:
        model = AnalysisProject
        fields = '__all__'
        read_only_fields = ('analysis_uuid', \
            'analysis_bucketname', \
            'started', \
            'completed', \
            'start_time', \
            'finish_time', \
            'success', \
            'error', \
        )

class AnalysisProjectResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisProjectResource
        fields = '__all__'
        read_only_fields = ('analysis_project','resource')


class OrganizationWorkflowSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationWorkflow
        fields = '__all__'


class WorkflowConstraintSerializer(serializers.ModelSerializer):

    class Meta:
        model = WorkflowConstraint
        fields = ('name', \
                  'description', \
                  'handler', \
                  'implementation_class', \
                  'value' \
        )
