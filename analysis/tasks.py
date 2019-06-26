import os
import io
import glob
import json
import shutil
import datetime
import time
import zipfile
import requests
from importlib import import_module
from jinja2 import Template

from django.conf import settings
from celery.decorators import task
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from googleapiclient.discovery import build as google_api_build
from google.cloud import storage

from helpers import utils
from helpers.utils import get_jinja_template
from helpers.email_utils import notify_admins, send_email
import analysis.models
from analysis.models import Workflow, \
    AnalysisProject, \
    AnalysisProjectResource, \
    SubmittedJob, \
    Warning, \
    CompletedJob, \
    JobClientError, \
    ProjectConstraint
from base.models import Resource, Issue, CurrentZone

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ZIPNAME = 'depenencies.zip'
WDL_INPUTS = 'inputs.json'
WORKFLOW_LOCATION = 'location'
WORKFLOW_PK = 'workflow_primary_key'
USER_PK = 'user_pk'
VERSIONING_FILE = 'workflow_version.%s.txt'

MAX_COPY_ATTEMPTS = 5
SLEEP_PERIOD = 60 # in seconds.  how long to sleep between copy attempts.


class InputMappingException(Exception):
    pass


class MissingMappingHandlerException(Exception):
    pass


class MissingDataException(Exception):
    pass


class JobOutputCopyException(Exception):
    pass


class JobOutputsException(Exception):
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

    # save this problem in the database:
    issue = Issue(message = message)
    issue.save()

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

                # The data referenced by data[target[settings.NAME]] could effectively be anything.  Its format
                # is dictated by some javascript code.  For example, a file chooser
                # could send data to the backend in a variety of formats, and that format
                # is determined solely by the author of the workflow.  We need to have custom
                # code which takes that payload and properly maps it to the WDL inputs

                # Get the handler code:
                handler_path = os.path.join(absolute_workflow_dir, target[settings.HANDLER])
                if os.path.isfile(handler_path):
                    # we have a proper file.  Call that to map our unmapped_data
                    # to the WDL inputs
                    print('Using handler code in %s to map GUI inputs to WDL inputs' % handler_path)
                    module_name = target[settings.HANDLER][:-len(settings.PY_SUFFIX)]
                    module_location = create_module_dot_path(absolute_workflow_dir)
                    module_name = module_location + '.' + module_name
                    mod = import_module(module_name)
                    print('Imported module %s' % module_name)
                    map_dict = mod.map_inputs(user, data, target[settings.NAME], target[settings.TARGET_IDS])
                    print('Result of input mapping: %s' % map_dict)
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


def check_constraints(project, absolute_workflow_dir, inputs_json):
    '''
    Loads the module containing the code to check constraints
    and calls it.  Returns a 3-ple.  The first item of the tuple indicates 
    if any of the constraints are violated; True is all pass, False if any fail.
    The second bool indicates if there was a problem with the handler module (i.e. which is outside
    the user's control).  Finally the third is a list of messages that can indicate how the client
    violated the constraints (e.g. "you submitted too many samples")
    If there was a problem with the handler module (i.e. missing file or some bug in the code)
    then inform the admin and let the client know that it is being worked on.
    '''

    # Using the project, we can get any constraints applied to this project:
    project_constraints = ProjectConstraint.objects.filter(project=project)
    if len(project_constraints) == 0:
        return (True, False,[]) # no constraints, of course it passes

    constraint_passes = []
    messages = []
    for project_constraint in project_constraints:
        # the constraint member is of type ImplementedConstraint, which has as one of its members
        # an attribute referencing the WorkflowConstraint
        implemented_constraint = project_constraint.constraint
        handler_filename = implemented_constraint.workflow_constraint.handler
        handler_path = os.path.join(absolute_workflow_dir, handler_filename)
        if os.path.isfile(handler_path):
            # the handler file exists.  Load the module and call the function
            module_name = handler_filename[:-len(settings.PY_SUFFIX)]
            module_location = create_module_dot_path(absolute_workflow_dir)
            module_name = module_location + '.' + module_name
            mod = import_module(module_name)
            try:
                constraint_satisifed, message = mod.check_constraints(implemented_constraint, inputs_json)
                constraint_passes.append(constraint_satisifed)
                messages.append(message)
            except Exception as ex:
                print(ex) # so we can see the exception in the logs
                handle_exception(ex, message = str(ex))
                return (False, True, messages)
        else:
            # the handler file is not there.  Something is wrong. Let an admin know
            handle_exception(None, message = 'Constraint handler module was not found at %s for project %s' % (handler_path, str(project.analysis_uuid)))
            return (False, True), messages
    return (all(constraint_passes), False, messages)


@task(name='prep_workflow')
def prep_workflow(data):
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
        workflow_obj = Workflow.objects.get(pk=data[WORKFLOW_PK])
        staging_dir = os.path.join(settings.JOB_STAGING_DIR, 
            'test_%s' % workflow_obj.workflow_name, 
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
    
    # check that any applied constraints are not violated:
    if data['analysis_uuid']:
        print('check constraints')
        constraints_satisfied, problem, constraint_violation_messages = check_constraints(analysis_project, data[WORKFLOW_LOCATION], wdl_input_path)
        print('done checking constraints')
        if problem:
            print('Was problem with constraints!')
            analysis_project.status = '''
                An unexpected error occurred on job submission.  An administrator has been automatically notified of this error.
                Thank you for your patience.
                '''
            analysis_project.error = True
            analysis_project.save()
            return
        elif not constraints_satisfied:
            print('constraints violated')
            analysis_project.status = 'The constraints imposed on this project were violated.'
            analysis_project.error = True
            analysis_project.completed = False
            analysis_project.success = False
            analysis_project.save()

            for m in constraint_violation_messages:
                jc = JobClientError(project=analysis_project, error_text=m)
                jc.save()
            return

    # Go start the workflow:
    if data['analysis_uuid']:
        print('had UUID')
        # we are going to start the workflow-- check if we should run a pre-check
        # to examine user input:
        run_precheck = False
        if os.path.exists(os.path.join(staging_dir, settings.PRECHECK_WDL)):
            print('should run precheck')
            run_precheck = True

        execute_wdl(analysis_project, staging_dir, run_precheck)
    else:
        print('View final staging dir at %s' % staging_dir)
        print('Would post the following:\n')
        print('Data: %s\n' % data)
        return wdl_input_dict


def execute_wdl(analysis_project, staging_dir, run_precheck=False):
    '''
    This function performs the actual work of submitting the job
    '''

    # read config to get the names/locations/parameters for job submission
    config_path = os.path.join(THIS_DIR, 'wdl_job_config.cfg')
    config_dict = utils.load_config(config_path)

    # the path of the input json file:
    wdl_input_path = os.path.join(staging_dir, WDL_INPUTS)

    # pull together the components of the POST request to the Cromwell server
    submission_endpoint = config_dict['submit_endpoint']
    submission_url = settings.CROMWELL_SERVER_URL + submission_endpoint
    payload = {}
    payload = {'workflowType': config_dict['workflow_type'], \
        'workflowTypeVersion': config_dict['workflow_type_version']
    }

    # load the options file so we can fill-in the zones:
    options_json = {}
    try:
        current_zone = CurrentZone.objects.all()[0]
    except IndexError:
        message = 'A current zone has not set.  Please check that a single zone has been selected in the database'
        handle_exception(None, message=message)

    options_json['default_runtime_attributes'] = {'zones': current_zone.zone.zone}
    options_json_str = json.dumps(options_json)
    options_io = io.BytesIO(options_json_str.encode('utf-8'))

    files = {
        'workflowOptions': options_io, 
        'workflowInputs': open(wdl_input_path,'rb')
    }
    
    if run_precheck:
        files['workflowSource'] = open(os.path.join(staging_dir, settings.PRECHECK_WDL), 'rb')
    else:
        files['workflowSource'] =  open(os.path.join(staging_dir, settings.MAIN_WDL), 'rb')

    zip_archive = os.path.join(staging_dir, ZIPNAME)
    if os.path.exists(zip_archive):
        files['workflowDependencies'] = open(zip_archive, 'rb')

    # start the job:
    try:
        response = requests.post(submission_url, data=payload, files=files)
    except Exception as ex:
        print('An exception was raised when requesting cromwell server:')
        print(ex)
        message = 'An exception occurred when trying to submit a job to Cromwell. \n'
        message += 'Project ID was: %s' % str(analysis_project.analysis_uuid)
        message += str(ex)

        analysis_project.status = '''
            Error on job submission.  An administrator has been automatically notified of this error.
            Thank you for your patience.
            '''
        analysis_project.error = True
        analysis_project.save()
        handle_exception(ex, message=message)
        raise ex
    response_json = json.loads(response.text)
    if response.status_code == 201:
        if response_json['status'] == 'Submitted':
            job_id = response_json['id']

            if run_precheck:
                job_status = 'Checking input data...'
            else:
                job_status = 'Job submitted...'

            job = SubmittedJob(project=analysis_project, 
                job_id=job_id, 
                job_status=job_status, 
                job_staging_dir=staging_dir,
                is_precheck = run_precheck
            )
            job.save()

            # update the project also:
            analysis_project.started = True # should already be set
            analysis_project.start_time = datetime.datetime.now()
            analysis_project.status = job_status
            analysis_project.save()
        else:
            # In case we get other types of responses, inform the admins:
            message = 'Job was submitted, but received an unexpected response from Cromwell:\n'
            message += response.text
            handle_exception(None, message=message)
    else:
        message = 'Did not submit job-- status code was %d, and response text was: %s' % (response.status_code, response.text)
        analysis_project.status = '''
            Error on job submission.  An administrator has been automatically notified of this error.
            Thank you for your patience.
            '''
        analysis_project.error = True
        analysis_project.save()
        handle_exception(None, message=message)


def parse_outputs(obj):
    '''
    depending on how the workflow was created, the outputs object can be relatively complex
    e.g. for a scattered job, it can have nested lists for each key.  Other times, a simple
    list, or even a string.

    `obj` is itself a dictionary OR a list.  Returns a list of strings
    '''
    all_outputs = []
    if type(obj) == dict:
        for key, val in obj.items():
            if type(val) == str: # if simple string output, just a single file:
                all_outputs.append(val)
            elif val is not None: # covers dict and list
                all_outputs.extend(parse_outputs(val))
            else:
                pass # val was None.  OK in cases with optional output
    elif type(obj) == list:
        for item in obj:
            if type(item) == str:
                all_outputs.append(item)
            elif item is not None:
                all_outputs.extend(parse_outputs(item))
            else:
                pass # item was None.  OK for cases of optional output
    else:
        raise Exception('Unexpected type')
    return all_outputs

def get_resource_size(path):
    '''
    This is used to query for the size of a file located at `path`.
    Depending on the environment, this is different

    TODO: abstract this for different cloud providers!!
    '''
    if settings.CONFIG_PARAMS['cloud_environment'] == settings.GOOGLE:
        client = google_api_build('storage', 'v1')
        bucket_prefix = settings.CONFIG_PARAMS['google_storage_gs_prefix']
        p = path[len(bucket_prefix):]
        bucketname = p.split('/')[0]
        objectname = '/'.join(p.split('/')[1:])
        response = client.objects().get(bucket=bucketname, object=objectname).execute()
        return int(response['size'])
    else:
        raise Exception('Have not implemented for this cloud provider yet')


def move_resource_to_user_bucket(storage_client, job, resource_path):
    '''
    Copies the final job output from the cromwell bucket to the user's bucket/folder
    '''
    # move the resource into the user's bucket:
    destination_bucket = settings.CONFIG_PARAMS[ \
        'storage_bucket_prefix' \
        ][len(settings.CONFIG_PARAMS['google_storage_gs_prefix']):]
    destination_object = os.path.join( str(job.project.owner.user_uuid), \
        str(job.project.analysis_uuid), \
        job.job_id, \
        os.path.basename(resource_path)
    )
    full_destination_with_prefix = '%s%s/%s' % (settings.CONFIG_PARAMS['google_storage_gs_prefix'], 
        destination_bucket, \
        destination_object \
    )
    full_source_location_without_prefix = resource_path[len(settings.CONFIG_PARAMS['google_storage_gs_prefix']):]
    source_bucketname = full_source_location_without_prefix.split('/')[0]
    source_objectname = '/'.join(full_source_location_without_prefix.split('/')[1:])

    copied = False
    attempts = 0
    while ((not copied) and (attempts < MAX_COPY_ATTEMPTS)):
        try:
            response = storage_client.objects().copy(sourceBucket=source_bucketname, \
                sourceObject=source_objectname, \
                destinationBucket=destination_bucket, \
                destinationObject=destination_object, body={}).execute()
            copied = True
        except Exception as ex:
            print('Copy failed.  Sleep and try again.')
            time.sleep(SLEEP_PERIOD)
            attempts += 1

    # if still not copied, raise an issue:
    if not copied:
        raise JobOutputCopyException('Still could not copy after %d attempts.' % MAX_COPY_ATTEMPTS)
    else:
        return full_destination_with_prefix


def register_outputs(job):
    '''
    This adds outputs from the workflow to the list of Resources owned by the client
    This way they are able to download files produced by the workflow
    '''
    config_path = os.path.join(THIS_DIR, 'wdl_job_config.cfg')
    config_dict = utils.load_config(config_path)

    # pull together the components of the request to the Cromwell server
    outputs_endpoint = config_dict['outputs_endpoint']
    outputs_url_template = Template(settings.CROMWELL_SERVER_URL + outputs_endpoint)
    outputs_url = outputs_url_template.render({'job_id': job.job_id})
    
    try:
        response = requests.get(outputs_url)
        response_json = json.loads(response.text)
        if (response.status_code == 404) or (response.status_code == 400) or (response.status_code == 500):
            job.project.status = 'Analysis completed.  Error encountered when collecting final outputs.'
            job.project.error = True
            job.project.save()
            handle_exception(None, 'Query for job failed with message: %s' % response_json['message'])
        else: # the request itself was OK
            outputs = response_json['outputs']
            output_filepath_list = parse_outputs(outputs)
            environment = settings.CONFIG_PARAMS['cloud_environment']
            storage_client = google_api_build('storage', 'v1')
            for p in output_filepath_list:
                size_in_bytes = get_resource_size(p)
                full_destination_with_prefix = move_resource_to_user_bucket(
                    storage_client, 
                    job,  
                    p
                )

                # add the Resource to the database:
                r = Resource(
                    source = environment,
                    path = full_destination_with_prefix,
                    name = os.path.basename(p),
                    owner = job.project.owner,
                    size = size_in_bytes
                )
                r.save()

                # add a ProjectResource to the database, so we can tie the Resource created above with the analysis project:
                apr = AnalysisProjectResource(analysis_project=job.project, resource=r)
                apr.save()

    except Exception as ex:
        print('An exception was raised when requesting job outputs from cromwell server')
        print(ex)
        message = 'An exception occurred when trying to query outputs from Cromwell. \n'
        message += 'Job ID was: %s' % job.job_id
        message += 'Project ID was: %s' % job.project.analysis_uuid
        message += str(ex)
        raise JobOutputsException(message)


def copy_pipeline_components(job):
    '''
    This copies the inputs.json to the output directory.  Together with the WDL files, that can be used
    to recreate everything  

    Also creates a file that indicates the repository and commit ID for the workflow version
    '''
    additional_files = []

    # where the submitted files were placed:
    staging_dir = job.job_staging_dir
    wdl_input_path = os.path.join(staging_dir, WDL_INPUTS)
    additional_files.append(wdl_input_path)

    # write the git versioning file to that staging dir:
    version_file = os.path.join(staging_dir, VERSIONING_FILE % job.job_id)
    git_url = job.project.workflow.git_url
    git_commit = job.project.workflow.git_commit_hash
    d = {
        'git_repository': git_url,
        'git_commit': git_commit
    }
    with open(version_file, 'w') as fout:
        fout.write(json.dumps(d))
    additional_files.append(version_file)

    environment = settings.CONFIG_PARAMS['cloud_environment']
    storage_client = storage.Client()

    for p in additional_files:
        stat_info = os.stat(p)
        size_in_bytes = stat_info.st_size

        destination_bucket = settings.CONFIG_PARAMS['storage_bucket_prefix']
        object_name = os.path.join( str(job.project.owner.user_uuid), \
            str(job.project.analysis_uuid), \
            job.job_id, \
            os.path.basename(p)
        )

        # perform the upload to the bucket:
        bucket_name = destination_bucket[len(settings.CONFIG_PARAMS['google_storage_gs_prefix']):]
        bucket = storage_client.get_bucket(bucket_name)
        blob = bucket.blob(object_name)
        blob.upload_from_filename(p)

        # add the Resource to the database:
        full_destination_with_prefix = '%s/%s' % ( 
            destination_bucket, \
            object_name \
        )
        r = Resource(
            source = environment,
            path = full_destination_with_prefix,
            name = os.path.basename(p),
            owner = job.project.owner,
            size = size_in_bytes
        )
        r.save()

        # add a ProjectResource to the database, so we can tie the Resource created above with the analysis project:
        apr = AnalysisProjectResource(analysis_project=job.project, resource=r)
        apr.save()



def handle_success(job):
    '''
    This is executed when a WDL job has completed and Cromwell has indicated success
    `job` is an instance of SubmittedJob
    '''

    try:
        # if everything goes well, we set the AnalysisProject to a completed state,
        # notify the client, and delete the SubmittedJob.  Since there is a 1:1
        # between AnalysisProject and a complete job, that's enough to track history
    
        register_outputs(job)

        copy_pipeline_components(job)

        # update the AnalysisProject instance to reflect the success:
        project = job.project
        project.completed = True
        project.success = True
        project.error = False
        project.status = 'Successful completion'
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

    except Exception as ex:
        # Set the project parameters so that clients will know what is going on:
        project.status = 'Analysis completed.  Error encountered when preparing final output.  An administrator has been notified'
        project.error = True
        project.success = False
        project.completed = False
        project.save()

        if type(ex) == JobOutputsException:
            message = str(ex)
        else:
            message = 'Some other exception was raised following wrap-up from a completed job.'

        handle_exception(ex, message=message)
    finally:
        # regardless of what happened, save a CompletedJob instance
        project = job.project
        cj = CompletedJob(project=project, 
            job_id = job.job_id, 
            job_status=job.job_status, 
            success = True,
            job_staging_dir=job.job_staging_dir)
        cj.save()
        job.delete()


def handle_failure(job):
    '''
    This is executed when a WDL job has completed and Cromwell has indicated a failure has occurred
    `job` is an instance of SubmittedJob
    '''
    project = job.project
    cj = CompletedJob(project=project, 
        job_id = job.job_id, 
        job_status=job.job_status, 
        success = False,
        job_staging_dir=job.job_staging_dir)
    cj.save()
    job.delete()

    # update the AnalysisProject instance to reflect the failure:
    project.completed = False
    project.success = False
    project.error = True
    project.status = 'The job submission has failed.  An administrator has been notified.'
    project.finish_time = datetime.datetime.now()
    project.restart_allowed = False # do not allow restarts for runtime failures
    project.save()

    # inform client (if desired):
    if not settings.SILENT_CLIENTSIDE_FAILURE:
        recipient = project.owner.email
        email_html = open('email_templates/analysis_fail.html').read()
        email_plaintext = open('email_templates/analysis_fail.txt').read()
        email_subject = open('email_templates/analysis_fail_subject.txt').readline().strip()
        send_email(email_plaintext, email_html, recipient, email_subject)

    # notify admins:
    message = 'Job (%s) experienced failure.' % cj.job_id
    subject = 'Cromwell job failure'
    notify_admins(message, subject)


def walk_response(key, val, target):
    '''
    Walks through a json object (`val`), returns all 
    primitives (e.g. strings) referenced by a `key` which
    equals `target`.  
    '''
    f = []
    if type(val) == list:
        for item in val:
            f.extend(walk_response('', item, target))
    elif type(val) == dict:
        for k, v in val.items():
            f.extend(walk_response(k, v, target))
    elif key == target:
        f.append(val)
    return f

def log_client_errors(job, stderr_file_list):
    '''
    This handles pulling the stderr files (which indicate what went wrong)
    from the cloud-based storage and extracting their contents
    '''

    # make a folder where we can dump these stderr files temporarily:
    foldername = 'tmp_stderr_%s' % datetime.datetime.now().strftime('%H%M%S_%m%d%Y')
    stderr_folder = os.path.join(job.job_staging_dir, foldername)
    os.mkdir(stderr_folder)

    storage_client = storage.Client()
    bucket_prefix = settings.CONFIG_PARAMS['google_storage_gs_prefix']
    local_file_list = []
    for i, stderr_path in enumerate(stderr_file_list):
        path_without_prefix = stderr_path[len(bucket_prefix):]
        bucket_name = path_without_prefix.split('/')[0]
        object_name = '/'.join(path_without_prefix.split('/')[1:])
        bucket = storage_client.get_bucket(bucket_name)
        blob = bucket.blob(object_name)
        file_location = os.path.join(stderr_folder, 'stderr_%d' % i)
        local_file_list.append(file_location)
        blob.download_to_filename(file_location)

    # now have all files-- read content and create database objects to track:
    errors = []
    for f in local_file_list:
        file_contents = open(f).read()
        if len(file_contents) > 0:
            stderr_sections = file_contents.split(settings.CROMWELL_STDERR_DELIM)
            for section in stderr_sections:
                jc = JobClientError(project=job.project, error_text=section)
                jc.save()
                errors.append(jc)
            
    shutil.rmtree(stderr_folder)
    return errors


def handle_precheck_failure(job):
    '''
    If a pre-check job failed, something was wrong with the inputs.  
    We query the cromwell metadata to get the error so the user can correct it
    '''
    config_path = os.path.join(THIS_DIR, 'wdl_job_config.cfg')
    config_dict = utils.load_config(config_path)

    # pull together the components of the request to the Cromwell server
    metadata_endpoint = config_dict['metadata_endpoint']
    metadata_url_template = Template(settings.CROMWELL_SERVER_URL + metadata_endpoint)
    metadata_url = metadata_url_template.render({'job_id': job.job_id})
    try:
        response = requests.get(metadata_url)
        response_json = response.json()
        stderr_file_list = walk_response('',response_json, 'stderr')
        error_obj_list = log_client_errors(job, stderr_file_list)

        # update the AnalysisProject instance:
        project = job.project
        project.completed = False
        project.success = False
        project.error = True
        project.status = 'Issue encountered with inputs.'
        project.message = ''
        project.finish_time = datetime.datetime.now()
        project.save() 

        # inform the client of this problem so they can fix it (if allowed):
        email_address = project.owner.email
        current_site = Site.objects.get_current()
        domain = current_site.domain
        project_url = reverse('analysis-project-execute', args=[project.analysis_uuid,])
        url = 'https://%s%s' % (domain, project_url)
        context = {'site': url, 'user_email': email_address}
        if project.restart_allowed:
            email_template_path = 'email_templates/analysis_fail_with_recovery.html'
            email_plaintxt_path = 'email_templates/analysis_fail_with_recovery.txt'
            email_subject = 'email_templates/analysis_fail_subject.txt'
        else:
            email_template_path = 'email_templates/analysis_fail.html'
            email_plaintxt_path = 'email_templates/analysis_fail.txt'
            email_subject = 'email_templates/analysis_fail_subject.txt'

        email_template = get_jinja_template(email_template_path)
        email_html = email_template.render(context)
        email_plaintxt_template = get_jinja_template(email_plaintxt_path)
        email_plaintxt = email_plaintxt_template.render(context)
        email_subject = open(email_subject).readline().strip()
        send_email(email_plaintxt, email_html, email_address, email_subject)

        if not project.restart_allowed:
            # a project that had a pre-check failed, but a restart was NOT allowed.
            # need to inform admins:
            message = 'Job (%s) experienced failure during pre-check.  No restart was allowed.  Staging dir was %s' % (job.job_id, job.job_staging_dir)
            subject = 'Cromwell job failure on pre-check'
            notify_admins(message, subject)

        # delete the failed job:
        job.delete()

    except Exception as ex:
        print('An exception was raised when requesting metadata '
            'from cromwell server following a pre-check failure')
        print(ex)
        message = 'An exception occurred when trying to query metadata. \n'
        message += 'Job ID was: %s' % job.job_id
        message += 'Project ID was: %s' % job.project.analysis_uuid
        message += str(ex)
        try:
            warnings_sent = Warning.objects.get(job=job)
            print('Error when querying cromwell for metadata.  Notification suppressed')
        except analysis.models.Warning.DoesNotExist:
            handle_exception(ex, message=message)

            # add a 'Warning' object in the database so that we don't
            # overwhelm the admin email boxes.
            warn = Warning(message=message, job=job)
            warn.save()
        raise ex  


def handle_precheck_success(job):
    '''
    This function is invoked if the pre-check passed, and we are OK to launch the full job
    '''
    project = job.project
    staging_dir = job.job_staging_dir

    # Remove the old job object
    job.delete()

    # execute the main wdl file:
    execute_wdl(project, staging_dir, False)


@task(name='check_job')
def check_job():
    '''
    Used for pinging the cromwell server to check job status
    '''
    terminal_actions = {
        'Succeeded': handle_success,
        'Failed': handle_failure
    }

    precheck_terminal_actions = {
        'Succeeded': handle_precheck_success,
        'Failed': handle_precheck_failure
    }

    other_states = ['Submitted','Running']

    config_path = os.path.join(THIS_DIR, 'wdl_job_config.cfg')
    config_dict = utils.load_config(config_path)

    # pull together the components of the request to the Cromwell server
    query_endpoint = config_dict['query_status_endpoint']
    query_url_template = Template(settings.CROMWELL_SERVER_URL + query_endpoint)

    # get the job IDs for active jobs:
    active_job_set = SubmittedJob.objects.all()
    print('%d active jobs found.' % len(active_job_set))
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
                    
                    if job.is_precheck:
                        precheck_terminal_actions[status](job) # call the function to execute the logic for this end-state

                    else:
                        terminal_actions[status](job) # call the function to execute the logic for this end-state
                elif status in other_states:
                    # any custom behavior for unfinished tasks
                    # can be handled here if desired

                    # update the job status in the database
                    job.job_status = status
                    job.save()

                    project = job.project
                    project.status = status
                    project.save()
                else:
                    # has some status we do not recognize
                    message = 'When querying for status of job ID: %s, ' % job.job_id
                    message += 'received an unrecognized response: %s' % response.text
                    job.job_status = 'Unknown'
                    job.save()

                    try:
                        warnings_sent = Warning.objects.get(job=job)
                        print('When querying cromwell for job status, received unrecognized status.  Notification suppressed')
                    except analysis.models.Warning.DoesNotExist:
                        handle_exception(None, message=message)

                        # add a 'Warning' object in the database so that we don't
                        # overwhelm the admin email boxes.
                        warn = Warning(message=message, job=job)
                        warn.save()
        except Exception as ex:
            print('An exception was raised when requesting job status from cromwell server')
            print(ex)
            message = 'An exception occurred when trying to query a job. \n'
            message += 'Job ID was: %s' % job.job_id
            message += 'Project ID was: %s' % job.project.analysis_uuid
            message += str(ex)
            try:
                warnings_sent = Warning.objects.get(job=job)
                print('Error when querying cromwell for job status.  Notification suppressed')
            except analysis.models.Warning.DoesNotExist:
                handle_exception(ex, message=message)

                # add a 'Warning' object in the database so that we don't
                # overwhelm the admin email boxes.
                warn = Warning(message=message, job=job)
                warn.save()
            raise ex
