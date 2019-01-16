import os
import glob
import json
import shutil
import datetime
import zipfile
import requests
from importlib import import_module
from jinja2 import Template

from django.conf import settings
from celery.decorators import task
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site

from helpers import utils
from helpers.utils import get_jinja_template
from helpers.email_utils import notify_admins, send_email
from analysis.models import Workflow, AnalysisProject, SubmittedJob

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ZIPNAME = 'depenencies.zip'
WDL_INPUTS = 'inputs.json'
WORKFLOW_LOCATION = 'location'
USER_PK = 'user_pk'


class InputMappingException(Exception):
    pass


class MissingMappingHandlerException(Exception):
    pass


class MissingDataException(Exception):
    pass


class MockAnalysisProject(object):
    '''
    A mock class for use when testing.
    '''
    pass


def handle_exception(ex, message = ''):
    '''
    This function handles situations where there an error when submitting
    to the cromwell server (submission or execution)
    '''
    subject = 'Error encountered with asynchronous task.'
    notify_admins(message, subject)

def create_module_dot_path(filepath):
    location_relative_to_basedir = os.path.relpath(filepath, start=settings.BASE_DIR)
    return location_relative_to_basedir.replace('/', '.')

def fill_wdl_input(data):
    '''
    Constructs the inputs to the WDL.  Returns a dict
    '''
    absolute_workflow_dir = data[WORKFLOW_LOCATION]
    user_pk = data[USER_PK]
    user = get_user_model().objects.get(pk=user_pk)

    # load the wdl input into a dict
    wdl_input_path = os.path.join(absolute_workflow_dir,
        settings.WDL_INPUTS_TEMPLATE_NAME)
    wdl_input_dict = json.load(open(wdl_input_path))
    required_inputs = list(wdl_input_dict.keys())

    # load the gui spec and create a dictionary:
    gui_spec_path = os.path.join(absolute_workflow_dir,
        settings.USER_GUI_SPEC_NAME)
    gui_spec_json = json.load(open(gui_spec_path))

    # for tracking which inputs were found.  We can then see that all the required
    # inputs were indeed specified
    found_inputs = [] 

    # iterate through the input elements that were specified for the GUI
    for element in gui_spec_json[settings.INPUT_ELEMENTS]:
        target = element[settings.TARGET]
        if type(target)==str and target in wdl_input_dict:
            # if the GUI specified a string input, it is supposed to directly
            # map to a WDL input.  If not, something has been corrupted.
            try:
                value = data[target] # get the value of the input from the frontend
                wdl_input_dict[target] = value # set the value in the dict of WDL inputs
                found_inputs.append(target)
            except KeyError:
                # if either of those key lookups failed, this exception will be raised
                raise MissingDataException('The key "%s" was not in either the data payload (%s) '
                    'or the WDL input (%s)' % (target, data, wdl_input_dict))
        elif type(target)==dict:
            # if the "type" of target is a dict, it needs to have a name attribute that is 
            # present in the data payload. Otherwise, we cannot know where to map it
            if target[settings.NAME] in data:
                unmapped_data = data[target[settings.NAME]]

                # unmapped_data could effectively be anything.  Its format
                # is dictated by some javascript code.  For example, a file chooser
                # could send data to the backend in a variety of formats, and that format
                # is determined solely by the author of the workflow.  We need to have custom
                # code which takes that payload and properly maps it to the WDL inputs

                # Get the handler code:
                handler_path = os.path.join(absolute_workflow_dir, target[settings.HANDLER])
                if os.path.isfile(handler_path):
                    # we have a proper file.  Call that to map our unmapped_data
                    # to the WDL inputs
                    module_name = target[settings.HANDLER][:-len(settings.PY_SUFFIX)]
                    module_location = create_module_dot_path(absolute_workflow_dir)
                    module_name = module_location + '.' + module_name
                    mod = import_module(module_name)
                    map_dict = mod.map_inputs(user, unmapped_data, target[settings.TARGET_IDS])
                    for key, val in map_dict.items():
                        if key in wdl_input_dict:
                            wdl_input_dict[key] = val
                            found_inputs.append(key)
                        else:
                           raise InputMappingException('Problem!  After mapping the front-'
                                'end to WDL inputs using the map \n%s\n'
                               'the key "%s" was not one of the WDL inputs' \
                               % (map_dict, key)
                           )
                else:
                    raise MissingMappingHandlerException('Could not find handler for mapping at %s' % handler_path)
            else:
                raise MissingDataException('If the type of the WDL target is a dictionary, then it MUST '
                    'specify a "name" attribute.  The value of that attribute must be in the '
                    'payload sent by the frontend.')
        else:
            raise Exception('Unexpected object encountered when trying to map front-end '
                'to WDL inputs.')

    if len(set(required_inputs).difference(set(found_inputs))) > 0:
        raise Exception('The set of required inputs was %s, and the set of found '
            'inputs was %s' % (required_inputs, found_inputs)
        )
    else:
        return wdl_input_dict

@task(name='start_workflow')
def start_workflow(data):
    '''
    
    '''
    # if the 'analysis_uuid' key evaluates to something, then
    # we have a "real" request to run analysis.  If it evaluates
    # to None, then we are simply testing that the correct files/variables
    # are created

    print('Workflow submitted with data: %s' % data)
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
    payload = {}
    payload = {'workflowType': config_dict['workflow_type'], \
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
        try:
            response = requests.post(submission_url, data=payload, files=files)
        except Exception as ex:
            print('An exception was raised when requesting cromwell server:')
            print(ex)
            message = 'An exception occurred when trying to submit a job to Cromwell. \n'
            message += 'Project ID was: %s' % data['analysis_uuid']
            message += str(ex)
            handle_exception(ex, message=message)
            raise ex
        response_json = json.loads(response.text)
        if response.status_code == 201:
            if response_json['status'] == 'Submitted':
                job_id = response_json['id']
                job = SubmittedJob(project=analysis_project, 
                    job_id=job_id, 
                    job_status='Submitted', 
                    job_staging_dir=staging_dir
                )
                job.save()

                # update the project also:
                analysis_project.started = True
                analysis_project.start_time = datetime.datetime.now()
                analysis_project.save()
            else:
                # In case we get other types of responses, inform the admins:
                message = 'Job was submitted, but received an unexpected response from Cromwell:\n'
                message += response.text
                handle_exception(None, message=message)
        else:
            message = 'Did not submit job-- status code was %d, and response text was: %s' % (response.status_code, response.text)
            handle_exception(None, message=message)
    else:
        print('View final staging dir at %s' % staging_dir)
        print('Would post the following:\n')
        print('Data: %s\n' % data)
        print('Files as appropriate.  Keys are: %s' % files.keys())


def handle_success(job):
    '''
    This is executed when a WDL job has completed and Cromwell has indicated success
    `job` is an instance of SubmittedJob
    '''
    # update the AnalysisProject instance to reflect the success:
    project = job.project
    project.completed = True
    project.success = True
    project.error = False
    project.finish_time = datetime.datetime.now()
    project.save()

    # inform client:
    email_address = project.owner.email
    current_site = Site.objects.get_current()
    domain = current_site.domain
    url = 'https://%s' % domain
    context = {'site': url, 'user_email': email_address}
    email_template = get_jinja_template('email_templates/analysis_success.html')
    email_html = email_template.render(context)
    email_plaintxt_template = get_jinja_template('email_templates/analysis_success.txt')
    email_plaintxt = email_plaintxt_template.render(context)
    email_subject = open('email_templates/analysis_success_subject.txt').readline().strip()
    send_email(email_plaintxt, email_html, email_address, email_subject)

    # delete the staging dir where the files were:
    staging_dir = job.job_staging_dir
    shutil.rmtree(staging_dir)

def handle_failure(job):
    '''
    This is executed when a WDL job has completed and Cromwell has indicated a failure has occurred
    `job` is an instance of SubmittedJob
    '''
    # update the AnalysisProject instance to reflect the failure:
    project = job.project
    project.completed = True
    project.success = False
    project.error = True
    project.finish_time = datetime.datetime.now()
    project.save()

    # inform client (if desired):
    if not settings.SILENT_CLIENTSIDE_FAILURE:
        send_email(plaintext_msg, message_html, recipient, subject)

    # notify admins:
    message = 'Job (%s) experienced failure.' % job.job_id
    subject = 'Cromwell job failure'
    notify_admins(message, subject)


@task(name='check_job')
def check_job():
    '''
    Used for pinging the cromwell server to check job status
    '''
    terminal_actions = {
        'Succeeded': handle_success,
        'Failed': handle_failure
    }
    other_states = ['Submitted','Running']

    config_path = os.path.join(THIS_DIR, 'wdl_job_config.cfg')
    config_dict = utils.load_config(config_path)

    # pull together the components of the request to the Cromwell server
    query_endpoint = config_dict['query_status_endpoint']
    query_url_template = Template(settings.CROMWELL_SERVER_URL + query_endpoint)

    # get the job IDs for active jobs:
    active_job_set = SubmittedJob.objects.all()
    for job in active_job_set:
        query_url = query_url_template.render({'job_id': job.job_id})
        try:
            response = requests.get(query_url)
            response_json = json.loads(response.text)
            if (response.status_code == 404) or (response.status_code == 400) or (response.status_code == 500):
                handle_exception(None, 'Query for job failed with message: %s' % response_json['message'])
            else: # the request itself was OK
                status = response_json['status']

                # if the job was in one of the finished states, execute some specific logic
                if status in terminal_actions.keys():
                    terminal_actions[status](job) # call the function to execute the logic for this end-state

                    # remove job since complete:
                    job.delete()

                elif status in other_states:
                    # any custom behavior for unfinished tasks
                    # can be handled here if desired

                    # update the job status in the database
                    job.job_status = status
                    job.save()
                else:
                    # has some status we do not recognize
                    message = 'When querying for status of job ID: %s, ' % job.job_id
                    message += 'received an unrecognized response: %s' % response.text
                    handle_exception(None, message=message)
                    job.job_status = 'Unknown'
                    job.save()
        except Exception as ex:
            print('An exception was raised when requesting job status from cromwell server')
            print(ex)
            message = 'An exception occurred when trying to query a job. \n'
            message += 'Job ID was: %s' % job.job_id
            message += 'Project ID was: %s' % job.project.analysis_uuid
            message += str(ex)
            handle_exception(ex, message=message)
            raise ex
        
