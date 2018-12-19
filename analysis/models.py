from django.db import models
from django.contrib.auth import get_user_model


class Workflow(models.Model):
    '''
    This class captures the notion of a fully implemented
    workflow/pipeline.

    It is used to track the locations of the potentially many WDL-based
    workflows and subversions of those.
    '''

    # this keeps track of the analysis type, and we reference it in the URL
    workflow_id = models.PositiveSmallIntegerField()

    # this keeps track of potential sub-versions of a workflow
    version_id = models.PositiveSmallIntegerField()

    # this keeps track of the workflow name. 
    workflow_name = models.CharField(max_length=500)

    # this keeps track of whether a workflow is the most recent or the "default"
    is_default = models.BooleanField(default=False)

    # this tracks whether a particular workflow (workflow_id AND version_id)
    # is active and able to be accessed
    # False by default since we do not necessarily want all the ingested
    # workflows to be automatically live
    is_active = models.BooleanField(default=False)

    # this keeps track of the location of the folder holding the 
    # WDL and associated files.  Allows us to locate the proper WDL
    # when an analysis is requested.
    workflow_location = models.CharField(max_length=2000)

    class Meta:
        # ensure the the combination of a workflow and a version is unique
        unique_together = ('workflow_id', 'version_id')
