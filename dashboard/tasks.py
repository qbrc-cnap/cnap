import traceback
import datetime
import os
import time
from celery.decorators import task
from django.db.utils import IntegrityError
from django.contrib.auth import get_user_model
from django.conf import settings

import google
from google.cloud import storage

from analysis.models import PendingWorkflow
from base.models import Resource, CurrentZone
from workflow_ingestion.ingest_workflow import ingest_main

from helpers.email_utils import send_email
from helpers.utils import get_jinja_template


MAX_COPY_ATTEMPTS = 5
SLEEP_PERIOD = 5 # seconds

class BucketImportException(Exception):
    pass

@task(name='kickoff_ingestion')
def kickoff_ingestion(pending_workflow_pk):
    '''
    This function does the asynchronous work when ingesting a new workflow.
    The repository containing the workflow code has already been cloned locally
    All the info about that is contained in a PendingWorkflow instance referenced
    by the input argument pending_workflow_pk.  Since this is a celery task, we can 
    only pass simple objects (e.g. don't pass database instances around)
    '''

    pending_workflow = PendingWorkflow.objects.get(pk=pending_workflow_pk)
    pending_workflow.status = 'Started ingestion'
    pending_workflow.save()
    dir = pending_workflow.staging_directory
    try:
        ingest_main(dir, pending_workflow.clone_url, pending_workflow.commit_hash)
        pending_workflow.status = 'Completed ingestion'
    except Exception as ex:
        pending_workflow.error = True
        reason = ''.join(traceback.format_exception(etype=type(ex), value=ex, tb=ex.__traceback__))
        print(reason)
        pending_workflow.status = reason[:1000] if len(reason)>1000 else reason
    
    pending_workflow.complete = True
    pending_workflow.finish_time = datetime.datetime.now()
    pending_workflow.save()


def get_zone_as_string():
    '''
    Returns the current zone as a string
    '''
    try:
        current_zone = CurrentZone.objects.all()[0]
        return current_zone.zone.zone
    except IndexError:
        message = 'A current zone has not set.  Please check that a single zone has been selected in the database'
        handle_exception(None, message=message)
        return None


def do_google_copy(source_blob, destination_bucket, new_blob_name):
    '''
    Handles the "re-try" on the copy process for a bucket-to-bucket transfer
    within google

    source_blob is a google.cloud.storage.blob.Blob instance
    destination_bucket is a google.cloud.storage.bucket.Bucket instance
    new_blob_name is a string 
    '''
    copied = False
    attempts = 0
    while ((not copied) and (attempts < MAX_COPY_ATTEMPTS)):
        try:
            print('Copy %s to %s/%s' % (source_blob, destination_bucket.name, new_blob_name))
            destination_bucket.copy_blob(source_blob, \
                destination_bucket, \
                new_name=new_blob_name \
            )
            copied = True
        except Exception as ex:
            print('Copy failed.  Sleep and try again.')
            time.sleep(SLEEP_PERIOD)
            attempts += 1

    # if still not copied, raise an issue:
    if not copied:
        print('Problem with copy (%s/%s --> %s/%s).  Failed after %d attempts' % (
            source_blob.bucket.name,
            source_blob.name,
            destination_bucket.name,
            new_blob_name,
            MAX_COPY_ATTEMPTS)
        )
        raise BucketImportException('Still could not copy after %d attempts.' % MAX_COPY_ATTEMPTS)
    else:
        return os.path.join(destination_bucket.name, new_blob_name)

@task(name='transfer_google_bucket')
def transfer_google_bucket(admin_pk, bucket_user_pk, client_bucket_name):
    '''
    Copies files from the provided bucket into the user's bucket.
    Then adds the copied files to the CNAP database

    Used in situations where a user has files already in a Google bucket.  This 
    gets copied to our own storage and auto-added to the user's Resources.

    Note that this function assumes the bucket can already be accessed.
    '''
    storage_client = storage.Client()

    # get the user object.  This is the person who will eventually
    # 'own' the files. It was previously verified to be a valid PK
    user = get_user_model().objects.get(pk=bucket_user_pk)

    # get the destination bucket (to where we are moving the files)
    destination_bucket_prefix = settings.CONFIG_PARAMS[ \
        'storage_bucket_prefix' \
        ][len(settings.CONFIG_PARAMS['google_storage_gs_prefix']):]
    destination_bucket_name = '%s-%s' % (destination_bucket_prefix, str(user.user_uuid)) # <prefix>-<uuid>

    # typically this bucket would already exist due to a previous upload, but 
    # we create the bucket if it does not exist 
    try:
        destination_bucket = storage_client.get_bucket(destination_bucket_name)
        print('Destination bucket at %s existed.' % destination_bucket_name)
    except google.api_core.exceptions.NotFound:
        b = storage.Bucket(destination_bucket_name)
        b.name = destination_bucket_name
        zone_str = get_zone_as_string() # if the zone is (somehow) not set, this will be None
        # if zone_str was None, b.location=None, which is the default (and the created bucket is multi-regional)
        if zone_str:
            b.location = '-'.join(zone_str.split('-')[:-1]) # e.g. makes 'us-east4-c' into 'us-east4'
        destination_bucket = storage_client.create_bucket(b)

    # get a list of the names of the files within the destination bucket.
    # This is how we will check against overwriting.
    destination_bucket_objects = [x.name for x in list(destination_bucket.list_blobs())]

    # Now iterate through the files we are transferring:
    blobs = storage_client.list_blobs(client_bucket_name)
    failed_filepaths = []
    for source_blob in blobs:
        basename = os.path.basename(source_blob.name)
        new_blob_name = os.path.join(settings.CONFIG_PARAMS['uploads_folder_name'], basename)
        target_path = settings.CONFIG_PARAMS['google_storage_gs_prefix'] + os.path.join(destination_bucket.name, new_blob_name)

        # we do NOT want to overwrite.  We check the destination bucket to see if the file is there.
        # If we find it, we consider that a "failure" and will report it to the admins
        if new_blob_name in destination_bucket_objects:
            failed_filepaths.append(target_path)
        else:
            p = do_google_copy(source_blob, destination_bucket, new_blob_name)
    
        # now register the resources to this user:
        try:
            Resource.objects.create(
                source = 'google_bucket',
                path=target_path,
                size=source_blob.size,
                name = basename,
                owner=user,
            )
        except IntegrityError as ex:
            # OK to pass, because regardless of whether the file was in the bucket
            # previously, we acknowledge it now and need it to be in the db.
            pass


    # done.  Inform the admin user:
    admin_user = get_user_model().objects.get(pk=admin_pk)
    email_address = admin_user.email
    context = {'original_bucket': client_bucket_name, 'failed_paths': failed_filepaths}
    email_template = get_jinja_template('email_templates/bucket_transfer_success.html')
    email_html = email_template.render(context)
    email_plaintxt_template = get_jinja_template('email_templates/bucket_transfer_success.txt')
    email_plaintxt = email_plaintxt_template.render(context)
    email_subject = open('email_templates/bucket_transfer_success_subject.txt').readline().strip()
    send_email(email_plaintxt, email_html, email_address, email_subject)


