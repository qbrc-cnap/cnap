from celery.decorators import task

@task(name='start_workflow')
def start_workflow(job_staging_dir):
    '''
    job_staging_dir is the path to a directory containing the necessary
    files to launch a job
    '''
    pass
