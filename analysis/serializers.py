from rest_framework import serializers

from analysis.models import Workflow, AnalysisProject, OrganizationWorkflow

class WorkflowSerializer(serializers.ModelSerializer):

    class Meta:
        model = Workflow
        fields = ('workflow_id', \
                  'version_id', \
                  'workflow_name', \
                  'workflow_title', \
                  'workflow_short_description', \
                  'workflow_long_description', \
                  'is_default', \
                  'is_active' \
        )


class AnalysisProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisProject
        fields = '__all__'


class OrganizationWorkflowSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationWorkflow
        fields = '__all__'