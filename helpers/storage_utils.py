import google
from google.cloud import storage

from base.models import CurrentZone
from helpers.email_utils import notify_admins


def create_regional_bucket(bucketname):
    '''
    Creates a storage bucket in the current region.
    '''
    client = storage.Client()
    b = storage.Bucket(bucketname)
    b.name = bucketname
    current_zone = CurrentZone.objects.all()[0] # something like "us-east1-c"
    current_region = '-'.join(current_zone.split('-')[:2])
    b.location = current_region
    try:
        final_bucket = client.create_bucket(b)
        return
    except google.api_core.exceptions.Conflict as ex:
        message = '''
            An attempt was made to create a bucket at %s.  However, the storage API indicated
            that this was an existing bucket.  Exception reported: %s  
        ''' % (bucketname, ex)
    except google.api_core.exceptions.BadRequest as ex:
        message = '''
            An attempt was made to create a bucket at %s.  However, the storage API indicated
            that there was an error during creation.  Exception reported: %s  
        ''' % (bucketname, ex)
    except Exception as ex:
        message = '''
            An attempt was made to create a bucket at %s.  However, there was an unexpected exception
            raised.  Exception reported: %s  
        ''' % (bucketname, ex)
    subject = 'Error with bucket creation'
    notify_admins(message, subject)