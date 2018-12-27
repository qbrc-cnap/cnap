from rest_framework import serializers

from analysis.models import Workflow

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
