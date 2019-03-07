import datetime
from celery.decorators import task

from analysis.models import PendingWorkflow
from workflow_ingestion.ingest_workflow import ingest_main

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
        pending_workflow.status = 'Something is wrong. %s' % ex
    
    pending_workflow.complete = True
    pending_workflow.finish_time = datetime.datetime.now()
    pending_workflow.save()
