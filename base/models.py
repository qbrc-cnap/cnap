import datetime

from jinja2.filters import do_filesizeformat

from django.db import models
from django.conf import settings
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
    expiration_date = models.DateField(null=True, blank=True)

    # track the number of times this Resource has been downloaded.  The total
    # number of downloads can be set in the config file:
    total_downloads = models.PositiveSmallIntegerField(null=False, default=0)

    objects = ResourceManager()

    def save(self, *args, **kwargs):
        if self._state.adding: # if creating, NOT updating
            if self.expiration_date is None:
                today = datetime.date.today()
                expiration_date = today + settings.EXPIRATION_PERIOD
                self.expiration_date = expiration_date
        super().save(*args, **kwargs)

    def __str__(self):
        return '%s' % self.name

    def get_owner(self):
        return self.owner

    def gui_representation(self):
        '''
        This returns a dictionary giving the representation in the UI.
        The structure is dictated by the UI-- e.g. the `text` key is used
        as the display shown.  `pk` is not shown, but is carried around with the
        node such that it can be returned to the backend.
        '''
        d = {}
        d['text'] = '%s (%s)'  % (self.name, do_filesizeformat(self.size, binary=True))
        d['pk'] = self.pk
        d['href'] = '/resources/%d' % self.pk
        return d


class Organization(models.Model):
    '''
    This model allows us to selectively expose analyses to different groups of individuals
    Thus, access to different analyses can be controlled from an organization standpoint.
    '''
    org_name = models.CharField(max_length=200, default='DEFAULT', blank=True)


class Issue(models.Model):
    '''
    This class is used when analyses have errors, etc.  Anytime an email is sent to an admin, a
    row will be added to log that entry.  This way, we can see all the errors in one place.
    '''
    message = models.CharField(max_length=5000)
    time = models.DateTimeField(auto_now=True)
