import os
import glob
import json
import shutil
import datetime
import zipfile
import requests

from django.conf import settings
from celery.decorators import task

from helpers import utils
from analysis.models import Workflow, AnalysisProject
from analysis.view_utils import fill_wdl_input, WORKFLOW_LOCATION, USER_PK

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ZIPNAME = 'depenencies.zip'
WDL_INPUTS = 'inputs.json'

class MockAnalysisProject(object):
    '''
    A mock class for use when testing.
    '''
    pass


@task(name='start_workflow')
def start_workflow(data):
    '''
    
    '''
    # if the 'analysis_uuid' key evaluates to something, then
    # we have a "real" request to run analysis.  If it evaluates
    # to None, then we are simply testing that the correct files/variables
    # are created

    date_str = datetime.datetime.now().strftime('%H%M%S_%m%d%Y')
    if data['analysis_uuid']:
        staging_dir = os.path.join(settings.JOB_STAGING_DIR, 
            str(data['analysis_uuid']), 
            date_str
        )
        analysis_project = AnalysisProject.objects.get(
            analysis_uuid = data['analysis_uuid']
        )

    else:
        staging_dir = os.path.join(settings.JOB_STAGING_DIR, 
            'test', 
            'test_workflow_name', 
            date_str
        )
        analysis_project = MockAnalysisProject()
        analysis_project.analysis_bucketname = 'some-mock-bucket'

    # make the temporary staging dir:
    try:
        os.makedirs(staging_dir)
    except OSError as ex:
        if ex.errno == 17: # existed already
            raise Exception('Staging directory already existed.  This should not happen.')
        else:
            raise Exception('Something else went wrong when attempting to create a staging'
            ' directory at %s' % staging_dir)

    # copy WDL files over to staging:
    wdl_files = glob.glob(os.path.join(data[WORKFLOW_LOCATION], '*.' + settings.WDL))
    for w in wdl_files:
        shutil.copy(w, staging_dir)
    # if there are WDL files in addition to the main one, they need to be zipped
    # and submitted as 'dependencies'
    additional_wdl_files = [x for x in glob.glob(os.path.join(staging_dir, '*.' + settings.WDL)) 
        if os.path.basename(x) != settings.MAIN_WDL]
    zip_archive = None
    if len(additional_wdl_files) > 0:
        zip_archive = os.path.join(staging_dir, ZIPNAME)
        with zipfile.ZipFile(zip_archive, 'w') as zipout:
            for f in additional_wdl_files:
                zipout.write(f, os.path.basename(f))

    # create/write the input JSON to a file in the staging location
    wdl_input_dict = fill_wdl_input(data)
    wdl_input_path = os.path.join(staging_dir, WDL_INPUTS)
    with open(wdl_input_path, 'w') as fout:
        json.dump(wdl_input_dict, fout)

    # read config to get the names/locations/parameters for job submission
    config_path = os.path.join(THIS_DIR, 'wdl_job_config.cfg')
    config_dict = utils.load_config(config_path)

    # pull together the components of the POST request to the Cromwell server
    submission_endpoint = config_dict['submit_endpoint']
    submission_url = settings.CROMWELL_SERVER_URL + submission_endpoint
    data = {}
    data = {'workflowType': config_dict['workflow_type'], \
        'workflowTypeVersion': config_dict['workflow_type_version']
    }
    files = {
        'workflowSource': open(os.path.join(staging_dir, settings.MAIN_WDL), 'rb'), 
        'workflowInputs': open(wdl_input_path,'rb')
    }
    if zip_archive:
        files['workflowDependencies'] = open(zip_archive, 'rb')

    # start the job:
    if data['analysis_uuid']:
        response = requests.post(submission_url, data=data, files=files)
        print(response.text)
    else:
        print('View final staging dir at %s' % staging_dir)
        print('Would post the following:\n')
        print('Data: %s\n' % data)
        print('Files as appropriate.  Keys are: %s' % files.keys())