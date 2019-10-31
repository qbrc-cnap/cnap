from django.db import models
from django.contrib.auth import get_user_model

from base.models import Resource 

class TransferCoordinatorObjectManager(models.Manager):
     '''
     This class provides a way to filter TransferCoordinator objects for a particular user
     Could perhaps be optimized.
     '''
     def user_transfer_coordinators(self, user):
         all_tc = super(TransferCoordinatorObjectManager, self).get_queryset()
         all_user_transfers = Transfer.objects.user_transfers(user)
         user_tc_pk = list(set([t.coordinator.pk for t in all_user_transfers]))
         q = all_tc.filter(pk__in = user_tc_pk)
         return q



class TransferCoordinator(models.Model):
    '''
    This model serves as a way to track a "batch" of Transfer instances (which can be of size >= 1), which allows
    for messaging once actions are completed.  Note that the Transfer model references this class, which 
    gives us the link between the two entities.
    '''

    # If all the Transfers have completed
    completed = models.BooleanField(null=False, default=False)

    # When the batch of Transfers was started- auto_now_add sets this when we create
    # the object
    start_time = models.DateTimeField(null=False, auto_now_add=True)

    # when all the Transfers completed. This does NOT imply success.
    finish_time = models.DateTimeField(null=True)

    objects = TransferCoordinatorObjectManager()


class TransferObjectManager(models.Manager):
     '''
     This class provides a nice way to filter Transfer objects for a particular user
     '''
     def user_transfers(self, user):
         return super(TransferObjectManager, self).get_queryset().filter(originator=user)

     #def get_coordinator(self, tc):
     #    return super(TransferObjectManager, self).get_queryset().filter(coordinator__pk=tc.pk)


class Transfer(models.Model):
    '''
    This class gives info about the transfer of a Resource from one location to another
    '''

    # True if transferring AWAY from our system (e.g. out of our bucket into a Dropbox)
    # False is an upload, which means someone is placing a file in our filesystem
    # No default value, and require a value with null=False
    download = models.BooleanField(null=False)

    # the Resource instance we are moving, as a foreign key
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE)

    # where the Resource is going (e.g. a URL)
    destination = models.TextField(null=False, max_length=1000)

    # has the Transfer completed?  This does NOT indicate success.  
    # A Transfer can be marked complete if it has tried and we have 
    # stopped trying to transfer it
    completed = models.BooleanField(null=False, default=False)

    # has the Transfer started?
    started = models.BooleanField(null=False, default=False)

    # This marks whether the transfer was successful
    success = models.BooleanField(null=False, default=False)

    # When the transfer was started- auto_now_add sets this when we create
    # the Transfer
    start_time = models.DateTimeField(null=False, auto_now_add=True)

    # when the Transfer completed.  As above, a complete transfer
    # does NOT imply success.
    finish_time = models.DateTimeField(null=True)

    # how long the transfer took:
    duration = models.DurationField(null=True)

    # each Transfer is "managed" by a TransferCoordinator, which monitors >=1 Transfers
    coordinator = models.ForeignKey(TransferCoordinator, on_delete=models.CASCADE)

    # other users (such as admins) can request transfers on behalf of regular users
    # this allows us to track who started the transfer, while the resource may only be
    # owned by that regular user
    originator = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)

    objects = TransferObjectManager()

    def __str__(self):
        return 'Transfer of %s, %s' % (self.resource, 'download' if self.download else 'upload')

    def get_owner(self):
        return self.resource.owner

    def save(self, *args, **kwargs):
        if self.finish_time:
            self.duration = self.finish_time - self.start_time
        super().save(*args, **kwargs)


class FailedTransfer(models.Model):
    '''
    This tracks failed transfers for auditing/performance purposes
    '''
    # if a download or upload
    was_download = models.BooleanField(null=False)

    # where was it supposed to go?  if upload, this would be the bucket path
    # is a download, just says which storage service it was supposed to go to.
    intended_path = models.TextField(null=False, max_length=1000)

    # When the transfer was started-
    start_time = models.DateTimeField(null=False)

    # when the Transfer failed.
    finish_time = models.DateTimeField(null=False, auto_now_add=True)

    # the name of the file that failed to transfer
    resource_name = models.CharField(max_length=100, null=False)

    # the coordinator that was handling this failure
    coordinator = models.ForeignKey(TransferCoordinator, on_delete=models.CASCADE)
