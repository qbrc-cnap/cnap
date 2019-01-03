from django.db import models
from django.contrib.auth import get_user_model
import uuid

from base.models import Organization


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

    # a human-readable name for the 'title' of a workflow/analysis
    # Used for display-- users will see a list of these describing the 
    # workflows they can run.  Can be added to the WDL file in a meta section
    # under the keyword `workflow_title`
    workflow_title = models.CharField(max_length=200, default='Workflow')

    # a SHORT description of the workflow to help users.  Not too long (See max length)
    # Can be added to WDL under meta section with key `workflow_short_description`
    workflow_short_description = models.CharField(max_length=400, default='', blank=True)

    # a longer description of the workflow to help users.  Not too long (See max length)
    # Can be added to WDL under meta section with key `workflow_long_description`
    workflow_long_description = models.CharField(max_length=2000, default='', blank=True)

    class Meta:
        # ensure the the combination of a workflow and a version is unique
        unique_together = ('workflow_id', 'version_id')


class AnalysisProject(models.Model):
    '''
    This class captures information that is contained via the combination of a Workflow
    and an actor who instantiates the Workflow instance.  This ties a Workflow to a particular
    user.
    '''
    # field for tracking (perhaps with an external LIMS)
    tracking_id = models.CharField(max_length=200, blank=True, default='')

    # field for url referencing.  Serves the same purpose as primary key, but 
    # when users hit the URL for their analysis, we prefer it not be a simple integer
    analysis_uuid = models.UUIDField(unique=True, default = uuid.uuid4)

    # an analysis needs a location where the files are stored.
    analysis_bucketname = models.CharField(max_length=63, blank=False)

    # foreign key to the Workflow
    workflow = models.ForeignKey('Workflow', on_delete=models.CASCADE)

    # foreign key to the owner/user
    owner = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)

    # boolean for whether the analysis has been started/run
    started = models.BooleanField(default=False)

    # boolean for whether complete
    completed = models.BooleanField(default=False)

    # fields to track status
    start_time = models.DateTimeField(blank=True, null=True)
    finish_time = models.DateTimeField(blank=True, null=True)
    success = models.BooleanField(default=True)
    error = models.BooleanField(default=False)


class OrganizationWorkflow(models.Model):
    '''
    This model joins an Organization to the list of available Workflows
    '''
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE)
