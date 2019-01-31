from django.db import models

from django.contrib.auth import get_user_model

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

    # if the file was uploaded from Dropbox, Drive, etc. what was the "source" used to locate it?
    source_path = models.CharField(max_length=1000, null=True, blank=True, default='')

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

    # if the file was uploaded by the client.
    originated_from_upload = models.BooleanField(null=False, default=False)

    # The date the resource was added:
    # auto_now_add sets the timestamp when an instance of created
    date_added = models.DateTimeField(null=False, auto_now_add=True)

    # when does this Resource expire?  When we expire a Resource, it will
    # be set to inactive.  Can be null, which would allow it to be permanent
    expiration_date = models.DateTimeField(null=True)

    objects = ResourceManager()
    
    def __str__(self):
        return '%s' % self.name

    def get_owner(self):
        return self.owner


class Organization(models.Model):
    '''
    This model allows us to selectively expose analyses to different groups of individuals
    Thus, access to different analyses can be controlled from an organization standpoint.
    '''
    org_name = models.CharField(max_length=200, default='DEFAULT', blank=True)
