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
    workflow_location = models.FilePathField()

    class Meta:
        # ensure the the combination of a workflow and a version is unique
        unique_together = ('workflow_id', 'version_id')


class ResourceManager(models.Manager):
     '''
     This class provides a nice way to filter Resource objects for a particular user
     '''
     def user_resources(self, user):
         return super(ResourceManager, self).get_queryset().filter(owner=user)


class Resource(models.Model):
    '''
    This model respresents a general resource/file.  See individual fields for interpretation
    '''
    # the location (e.g. string like 'google') where the Resource is 
    source = models.CharField(max_length=100, null=False)

    # the location (e.g. URL) where the Resource lives, relative to source
    # e.g. gs://bucket/dir/object.txt for google buckets
    path = models.CharField(max_length=1000, null=False)
    
    # a human-readable name for the UI
    name = models.CharField(max_length=1000, null=False)

    # the file size in bytes.  For display, this will be converted
    # to human-readable form  
    size = models.BigIntegerField(default=0)

    # each Resource can only be associated with a single User instance
    owner = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)

    # this boolean controls whether a Resource is active and able to be transferred
    is_active = models.BooleanField(null=False, default=True)

    # The date the resource was added:
    # auto_now_add sets the timestamp when an instance of created
    date_added = models.DateTimeField(null=False, auto_now_add=True)

    # when does this Resource expire?  When we expire a Resource, it will
    # be set to inactive.  Can be null, which would allow it to be permanent
    expiration_date = models.DateTimeField(null=True)

    objects = ResourceManager()
    
    def __str__(self):
        return '%s' % self.source

    def get_owner(self):
        return self.owner