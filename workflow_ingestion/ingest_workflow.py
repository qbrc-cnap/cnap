'''
This script is used for incorporating new analysis workflows into the
the framework.

Users will start with a directory containing a WORKING docker-based
WDL workflow

We require that there is only one WDL file (ending with ".wdl").  
If additional WDL files are used to define the sub-tasks (or sub-workflows)
then they need to be zipped.  Zipping is required to submit to the Cromwell
engine regardless.
'''

import shutil
import argparse
import os
import datetime
import glob
import re
import json
import sys
import time
import inspect
import subprocess as sp
from importlib import import_module
from inspect import signature
import requests

import workflow_ingestion.gui_utils as gui_utils

# for easy reference, determine the directory we are currently in, and
# also the base directory for the entire project (one level up)
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_ROOT_DIR = os.path.dirname(THIS_DIR)

# add the app root dir to the syspath
sys.path.append(APP_ROOT_DIR)

# need all this to "talk to" Django's database
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cnap_v2.settings')
import django
from django.conf import settings
django.setup()

# Now import a custom config parser:
from helpers import utils

# A config file that lives in this directory
CONFIG_FILE = os.path.join(THIS_DIR, 'config.cfg')

# File extensions for expected files.
# The check will be case-insensitive
WDL = 'wdl'
PYFILE = 'py'
ZIP = 'zip'
JSON = 'json'
JS = 'javascript'
CSS = 'css'
ACCEPTED_FILE_EXTENSIONS = [WDL, PYFILE, ZIP, JSON]

# Other constants:
MAIN_WDL = settings.MAIN_WDL
PRECHECK_WDL = settings.PRECHECK_WDL
CONSTRAINTS_JSON = settings.CONSTRAINTS_JSON
NEW_WDL_DIR = 'wdl_dir' # a string used for common reference.  Value arbitrary.
COMMIT_HASH = 'commit_hash' # a string used for common reference.  Value arbitrary.
CLONE_URL = 'clone_url' # a string used for common reference.  Value arbitrary
WOMTOOL_JAR = settings.WOMTOOL_JAR
HTML = 'html'
DISPLAY_ELEMENT = settings.DISPLAY_ELEMENT
WORKFLOWS_DIR = settings.WORKFLOWS_DIR
HANDLER = settings.HANDLER
TARGET = settings.TARGET
################


class WdlImportException(Exception):
    '''
    TODO add desc.
    '''
    pass


class GuiSpecFileException(Exception):
    '''
    We expect only one file that specifies the GUI
    If the number of matching files is != 1, then raise this
    '''
    pass

class MissingHandlerException(Exception):
    '''
    This is raised if we cannot locate a handler or find a default
    '''
    pass

class HandlerConfigException(Exception):
    '''
    This is raised if the handler module does not contain
    the proper function 
    '''
    pass

class MissingWdlInputTemplateException(Exception):
    '''
    This is raised if the inputs template for the WDL
    is missing.
    '''
    pass

class RuntimeDockerException(Exception):
    '''
    This is raised if there is a discrepancy between the number of tasks
    in a WDL file and the number of runtime sections defined in the WDL file
    '''
    pass


class DockerRegistryQueryException(Exception):
    '''
    This is raised if there was a problem when querying the docker registry
    for the appropriate tag
    '''
    pass


class ConstraintFileFormatException(Exception):
    '''
    This is raised if there are any problems with the file format dictating
    constraints that may be placed upon a workflow that we are ingesting.
    '''
    pass


class ConstraintFileKeyException(Exception):
    '''
    This is raised if a key is missing in the constraint objects contained
    in the constraint json file
    '''
    pass


class ConstraintFileClassnameException(Exception):
    '''
    This is raised if the class name given in the constraint file is not 
    found
    '''
    pass

def parse_commandline():
    '''
    Commandline arguments/options are specified here.
    
    Returns a dictionary.
    '''
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-d',
        '--dir',
        required=True,
        dest=NEW_WDL_DIR,
        help='Path to a directory containing WDL '
             'files, GUI specs, and other files to be incorporated.'
    )

    parser.add_argument(
        '-u',
        '--url',
         required=True,
         dest=CLONE_URL,
         help='The URL used for cloning the git repository.'
    )

    parser.add_argument(
        '-c',
        '--commit',
         required=True,
         dest=COMMIT_HASH,
         help='The git commit hash for this workflow.'
    )
    args = parser.parse_args()
    return vars(args)


def get_files(wdl_directory):
    '''
    Given a directory, returns a dict where the keys are file "types"
    and they point at a list of strings
    '''
    file_dict = {}

    for ext in ACCEPTED_FILE_EXTENSIONS:
        matched_files = [ os.path.abspath(os.path.realpath(os.path.join(wdl_directory, x))) for x 
            in os.listdir(wdl_directory) 
            if x.split('.')[-1].lower() == ext ]
        if len(matched_files) > 0:
            file_dict[ext] = matched_files
        else:
            file_dict[ext] = []

    # expect at least a single WDL file:
    if len(file_dict[WDL]) < 1:
        raise WdlImportException('There needs to be one or more WDL '
            'files in the %s directory' % wdl_directory)
    else:
        # need a single file named MAIN_WDL
        main_matches = [x for x in file_dict[WDL] if os.path.basename(x) == MAIN_WDL]
        if len(main_matches) != 1:
            raise WdlImportException('There needs to be exactly one WDL file '
                'named %s for us to identify which is the main WDL file.' % MAIN_WDL
            )

    # expect zero or one zip files.
    if len(file_dict[ZIP]) > 1:
        raise WdlImportException('There can be zero or one zip archives '
            ' in the %s directory' % wdl_directory)

    return file_dict


def get_gui_spec(wdl_directory):
    '''
    Find the proper file which defines the user-interface
    for the new Workflow.
    '''
    matched_files = [x for x in os.listdir(wdl_directory)
        if x == settings.USER_GUI_SPEC_NAME
    ]
    if len(matched_files) == 1:
        return os.path.join(wdl_directory, matched_files[0])
    else:
        raise GuiSpecFileException('There were %d files named %s' % (
            len(matched_files), settings.USER_GUI_SPEC_NAME
        ))


def create_workflow_destination(workflow_name):
    '''
    This function creates and returns the path to a "valid" destination dir
    for the newly ingested workflow

    That is, we check if a workflow by the same name has been ingested
    before, and creates date-stamped subdirectories underneath that.
    '''

    # construct path to the analyses dir:
    workflow_dir = os.path.join(
        APP_ROOT_DIR,
        WORKFLOWS_DIR
    )

    # see if a directory for this workflow exists.  If not 
    # create one.  Since this will not be the destination of the copy
    # we are supposed to create a directory here.
    workflow_dir = os.path.join(workflow_dir, workflow_name)
    try:
        os.makedirs(workflow_dir)
    except FileExistsError as ex:
        if ex.errno != 17:
            print('Unexpected exception when '
            'attempting to create directory at %s' % workflow_dir)
        else:
            print('Directory for this workflow already existed. '
                'Will create a new subversion directory.'
            )
    
    # create a stamp based on the date:
    now = datetime.datetime.now()
    datestamp_prefix = now.strftime('%Y%m%d') # e.g. 20181009

    # query to see if there are already subdirectories with that stamp
    directory_prefix = os.path.join(workflow_dir, datestamp_prefix)
    existing_dirs = glob.glob(directory_prefix + '*')

    # based on the number of existing dirs, create some new 
    # ones indexed by the count 
    n = len(existing_dirs)
    datestamp_with_index = '%s_%s' % (datestamp_prefix, n)
    newdir = os.path.join(workflow_dir, datestamp_with_index)

    # finally, make this dir:
    try:
        os.mkdir(newdir)
    except OSError:
        print('There was a problem when creating a directory at %s' % newdir)
        sys.exit(1)

    return newdir


def call_external(cmd):
    '''
    This is essentially a wrapper around subprocess.Popen
    but we tack on some additional printouts, etc.

    If the subprocess fails, we simply exit.
    '''
    p = sp.Popen(cmd, shell=True, stdout=sp.PIPE, stderr=sp.STDOUT)
    stdout, stderr = p.communicate()
    if p.returncode != 0:
        print('There was a problem with running the following: %s' % cmd)
        print('stdout: %s' % stdout)
        print('stderr: %s' % stderr)
        sys.exit(1)


def copy_to_staging_directory(*files):
    '''
    Creates a staging dir and copies files there
    Takes an arbitrary number of args
    '''
    # construct path to the staging dir:
    staging_dir = os.path.join(
        THIS_DIR,
        settings.STAGING_DIR
    )

    # create a datestamp
    now = datetime.datetime.now()
    datestamp_prefix = now.strftime('%Y%m%d') # e.g. 20181009

    # see if a directory for this exists with this prefix
    # Add suffix indices to make unique
    staging_dir = os.path.join(staging_dir, datestamp_prefix)
    n = len(glob.glob(staging_dir + '*'))
    if n != 0:
        staging_dir = staging_dir + '_%d' % (n-1)
    try:
        os.makedirs(staging_dir)
    except OSError as ex:
        print('Something went wrong when attempting to create staging '
            'directory at %s' % staging_dir)
        raise ex

    # now copy the files over:
    for f in files:
        shutil.copy2(f, staging_dir)
    return staging_dir


def get_workflow_name(wdl_path):
    '''
    We use regex to parse out the name of the workflow, which will be used
    to label the workflow directories.

    Regex closely follows the WDL spec, but some edge-cases could fail if users
    decide to name their workflows with ridiculous names or use 
    bizarre whitespace chars that don't work with python's regex: "\s" (don't do that!)
    '''
    pattern = r'workflow\s+([a-zA-Z][a-zA-Z0-9_]+)\s*\{.*\}'
    f = open(wdl_path).read()
    m=re.search(pattern, f, flags=re.DOTALL)
    if m:
        return m.group(1)


def get_workflow_title_and_description(wdl_path):
    '''
    We use regex to parse out the human-readable title and description of the workflow, which will be saved
    in the database and used for display purposes

    Regex closely follows the WDL spec, but some edge-cases could fail if users
    decide to name their workflows with ridiculous names or use 
    bizarre whitespace chars that don't work with python's regex: "\s" (don't do that!)

    If no `meta` section, return the workflow name and an empty description
    If there is a meta section but either of the keys are missing, return
    suitable defaults (workflow name and empty string for title and description, respectively)
    '''
    print('Using %s for get_workflow_title_and_description' % wdl_path)
    # we are looking in the meta section, so grab that
    meta_pattern = r'meta\s+\{.*?\}'
    f = open(wdl_path).read()
    m=re.search(meta_pattern, f, flags=re.DOTALL)
    if m:
        meta_section_text = m.group(0)

        # find 'workflow_title' if it exists
        title_regex = 'workflow_title\s*:\s*"(.*)"'
        m1 = re.search(title_regex, meta_section_text)
        if m1:
            title = m1.group(1)
        else:
            title = get_workflow_name(wdl_path)

        # find 'workflow_short_description' if it exists
        description_regex = 'workflow_short_description\s*:\s*"(.*)"'
        m2 = re.search(description_regex, meta_section_text)
        if m2:
            short_description = m2.group(1)
        else:
            short_description = ''

        # find 'workflow_long_description' if it exists
        description_regex = 'workflow_long_description\s*:\s*"(.*)"'
        m3 = re.search(description_regex, meta_section_text)
        if m3:
            long_description = m3.group(1)
        else:
            long_description = ''
    else: # no meta section:
        title = get_workflow_name(wdl_path)
        short_description = ''
        long_description = ''

    return title, short_description, long_description


def locate_handler(module_name, search_dir_list):
    '''
    This function searches for a module (python file)
    with name `module_name` in the search directories.

    The search directory list is ordered such that non-default (i.e. custom)
    implementations are found first

    Returns None is not found.
    '''
    potential_file_locations = [os.path.join(x,module_name) for x 
        in search_dir_list]
    for f in potential_file_locations:
        if os.path.isfile(f):
            return f
    return None
    

def copy_handler_if_necessary(element, staging_dir, search_dir_list):
    '''
    This function copies any "handler" scripts that are not already in the 
    staging directory.  This happens if the developer has not created a custom handler
    and is using the default implementation specified in the GUI schema.  This way
    all the code is together in one directory.

    returns the basename of the module that was copied into the staging dir

    If there is an error and no modules match, raise an error.
    '''
    handler_module = element[HANDLER]
    handler_module_path = locate_handler(handler_module, search_dir_list)
    if handler_module_path: # module was indeed found

        # if the module was NOT found in the staging dir, copy it there
        # so everything is together
        if os.path.dirname(handler_module_path) != staging_dir:
            shutil.copy2(handler_module_path, staging_dir)
        return os.path.basename(handler_module_path)
    else:
        raise MissingHandlerException('Could not locate the handler code specified'
            ' for the input element: %s' % json.dumps(element)
        )


def inspect_handler_module(module_path, fn_name, arg_num):
    '''
    This function checks that a handler module is syntatically
    correct AND has the proper method.
    '''
     # need to check that the handler contains the proper entry function
    # and has correct syntax:
    module_path_relative_to_base = os.path.relpath(
        module_path, 
        start=settings.BASE_DIR
    )

    # if we do not sleep and/or list the directory, the import_module sometimes fails to find
    # the file that is there.  Adding the sleep and directory listing seems to fix that...
    time.sleep(1)
    dir_listing = os.listdir(os.path.dirname(module_path_relative_to_base))
    if not os.path.basename(module_path_relative_to_base) in dir_listing:
        print('The module was not in the correct location.  Generally this should not happen.')
    module_dot_path = module_path_relative_to_base.replace('/', '.')[:-(len(PYFILE) + 1)]
    mod = import_module(module_dot_path)
    if not hasattr(mod, fn_name):
        raise HandlerConfigException('The module at %s needs '
            'contain a function named "%s".' % (module_path, fn_name))
    else:
        # has the correct method.  Check the number of arguments as a rough
        # check
        sig = signature(getattr(mod, fn_name))
        if len(sig.parameters) != arg_num:
            raise HandlerConfigException('The function %s (in file %s) '
                ' should take %d arguments.' % (fn_name, module_path, arg_num)
            )

def check_handlers(staging_dir):
    '''
    This function ensures that the various "handler" modules are correctly
    copied to the staging directory.  This way, all the code necessary to run 
    a workflow is together.
    '''
    # load the GUI spec file into a dict
    workflow_gui_spec_filename = settings.USER_GUI_SPEC_NAME
    workflow_gui_spec_path = os.path.join(staging_dir, workflow_gui_spec_filename)
    workflow_gui_spec = json.load(open(workflow_gui_spec_path))

    # a list of directories to look in.  These are searched in order, so that custom
    # implementations take precedence over the default.
    # Note that in the gui schema, any paths to default implementations are RELATIVE
    # to the directory holding the gui schema (i.e. this directory)
    search_dirs = [staging_dir, THIS_DIR]

    handler_module_list = []
    for input_element in workflow_gui_spec[settings.INPUT_ELEMENTS]:

        # if the target was of type dict, it is possible that
        # the developer has specified some custom code that can map
        # the inputs received by the GUI element to the proper inputs
        # for the workflow.  See if that key exists, and if it does,
        # check for the file
        if type(input_element[TARGET]) == dict:
            if HANDLER in input_element[TARGET]:
                module_name = copy_handler_if_necessary(input_element[TARGET], 
                    staging_dir, search_dirs)
                
                # need to check that the handler contains the proper entry function
                # and has correct syntax:
                module_path = os.path.join(staging_dir, module_name)
                inspect_handler_module(module_path, 'map_inputs', 3)

                handler_module_list.append(module_name)

                # we also update the dict specifying the GUI.  Since all the files
                # will be residing in the same directory as the final GUI spec, we only
                # need the basename
                input_element[TARGET][HANDLER] = module_name

        display_element = input_element[DISPLAY_ELEMENT]
        if HANDLER in display_element:
            module_name = copy_handler_if_necessary(display_element, 
                staging_dir, search_dirs)

            # need to check that the handler contains the proper entry function
            # and has correct syntax:
            module_path = os.path.join(staging_dir, module_name)
            inspect_handler_module(module_path, 'add_to_context', 4)    
            
            handler_module_list.append(module_name)

            # again, update the GUI dict for the same reason as above
            display_element[HANDLER] = module_name
    
    # rewrite the GUI spec since we changed the module names to be relative.
    with open(workflow_gui_spec_path, 'w') as fout:
        json.dump(workflow_gui_spec, fout)
    return handler_module_list

def parse_docker_runtime_declaration(docker_str):
    '''
    This function parses the docker string that is parsed out of 
    the WDL file.  Returns a tuple of strings giving the image name and tag,
    e.g. ('docker.io/user/img', 'v1.0') 
    Raises an exception if there is no tag
    '''
    # now if we split on ':', we get something like: (note the quotes)
    # ['docker', ' "docker.io/foo/bar', 'tag"']
    # if a tag is not specified, this list will have length 2.  We enforce that images are tagged, so raise excpetion
    contents = [x.strip() for x in docker_str.split(':')] # now looks like ['docker', '"docker.io/foo/bar', 'tag"']
    if len(contents) != 3:
        raise RuntimeDockerException('The docker spec (%s) did not match our expectations. '
            'Perhaps a tag was missing?  See WDL file.' % docker_str)
    image_name = contents[1][1:] # strip off the leading double-quote, leaving 'docker.io/foo/bar'
    tag = contents[-1][:-1] # strip off the trailing double-quote, leaving 'tag'

    if tag == 'latest':
        raise RuntimeDockerException('We do not allow the use of the "latest" tag for the Docker images. '
            'Please specify another tag.  Check WDL file.')

    return (image_name, tag)


def check_runtime(wdl_text):
    '''
    This function does the actual checking in the WDL file

    Returns a SET of the docker images (strings) for each task in the WDL file
    e.g. {'docker.io/user/imageA:tag', 'docker.io/user/imageB:tag'}
    '''
    # For parsing the WDL files:
    task_pattern = 'task\s+\w+\s?\{' # only finds the task definition line- does not extract the entire block of the task
    runtime_pattern = 'runtime\s?\{.*?\}' # extracts the entire runtime section, including the braces
    docker_pattern = 'docker\s?:\s?".*?"' # extracts the docker specification, e.g. docker: `"repo/user/image:tag"`

    # prepare a list to return:
    docker_runtimes = []

    # get the total number of tasks in this WDL file:
    task_match = re.findall(task_pattern, wdl_text, re.DOTALL)
    num_tasks = len(task_match)

    # we now know there are num_tasks tasks defined in the WDL file.  Therefore, there should be num_tasks runtime sections
    # Find all of those and parse each:
    runtime_sections = re.findall(runtime_pattern, wdl_text, re.DOTALL)
    if len(runtime_sections) != num_tasks:
        raise RuntimeDockerException('There were %d tasks defined, '
            'but only %d runtime sections found.  Check your WDL file.' % (num_tasks, len(runtime_sections)))
    elif num_tasks > 0: # tasks are defined and the number of runtime sections are consistent with tasks
        for runtime_section in runtime_sections:
            docker_match = re.search(docker_pattern, runtime_section, re.DOTALL)
            if docker_match:
                # the docker line was found.  Now parse it.
                docker_str = docker_match.group()  # something like 'docker: "docker.io/foo/bar:tag"'
                image_name, tag = parse_docker_runtime_declaration(docker_str)
                # "add" them back together, so we end up with 'docker.io/foo/bar:tag'
                docker_runtimes.append('%s:%s' % (image_name, tag))
            else: # docker spec not found in this runtime.  That's a problem
                raise RuntimeDockerException('Could not parse a docker image specification from your '
                    'runtime section: %s.  Check file' % runtime_section)
    # if we make it here, no exceptions were raised.  Return the docker images found:
    return set(docker_runtimes)


def perform_query(query_url):
    '''
    This performs the actual request and handles retries
    If it fails MAX_TRIES times, it gives up.

    If query is successful, returns a dictionary
    '''
    # how many times do we try to contact the registry before giving up:
    MAX_TRIES = 5

    success = False
    tries = 0
    while (not success) and (tries < MAX_TRIES):
        response = requests.get(query_url)
        if response.status_code == 200:
            success = True
            return response.json()
        else:
            tries += 1
    # exited the loop.  if success is still False, exit
    if not success:
        raise DockerRegistryQueryException('After %d tries, could not get '
        'a successful response from url: %s' % (MAX_TRIES, query_url))


def query_for_tag(query_url, tag):
    '''
    This function parses the JSON response received from the registry server (e.g. dockerhub)
    If something is amiss, raise an exception.  Otherwise, return True or False, depending on whether the
    tag was found.  
    response_json is a dict, tag is a string
    '''

    # make the initial request to the registry:
    response_json = perform_query(query_url)

    total_tags = response_json['count']
    running_index = 0
    tag_found = False
    while (running_index < total_tags) and (not tag_found):
        for item in response_json['results']:
            tagname = item['name']
            if tagname == tag:
                return True
            running_index += 1
        # are there more pages of results?
        next_url = response_json['next']
        if next_url:
            response_json = perform_query(next_url)
    return False


def check_runtime_docker_containers(staging_dir):
    '''
    staging_dir is a directory where we are keeping the files while we check that
    everything is OK.  

    This function looks in the WDL files and finds the docker container they use
    in the runtime section.  It then queries the docker registry (e.g. dockerhub)
    to see that the image exists.  Further, we enforce that each docker image
    has a tag, rather than using the default 'latest' tag.  This ensures that each
    WDL-based workflow has a specific Docker image version, rather than continually
    pulling the latest version.  We raise an exception if there are any deviations
    from this expectation.
    '''
    # The registry and the API url to query:
    docker_registries = {'docker.io': 'https://hub.docker.com/v2/repositories/%s/tags'}

    # get all the WDL files in this dir:
    image_set = set()
    wdl_files = [x for x in os.listdir(staging_dir) if os.path.basename(x).split('.')[-1].lower().endswith(WDL)]
    for w in wdl_files:
        w = os.path.join(staging_dir, w)
        # read in the entire WDL file:
        wdl_text = open(w).read()
        image_set = image_set.union(check_runtime(wdl_text))

    # now we have a set of the images we will be using, such as {'docker.io/user/imageA:tag1', 'docker.io/user/imageB:tag2'}
    # Check that they exist
    for image_str in image_set:
        image, tag = image_str.split(':') # image='docker.io/user/imageA', tag='tag1'
        image_contents = image.split('/') # ['docker.io', 'user', 'imageA']
        registry = image_contents[0] #'docker.io'
        repository_name = '/'.join(image_contents[1:]) #'user/imageA'
        query_url = docker_registries[registry] % repository_name
        tag_found = query_for_tag(query_url, tag)
        if not tag_found:
            raise RuntimeDockerException('Could not locate the repository at %s.' % image_str)


def add_workflow_to_db(workflow_name, destination_dir, clone_url, commit_hash):
    '''
    Once everything is in the correct location, we need to add the new workflow
    to the database.  

    Note that by default the workflow is marked inactive so that workflows
    in development are not immediately "exposed".
    '''


    from analysis.models import Workflow

    # query for existing workflows with this name:
    existing_wf = Workflow.objects.filter(workflow_name=workflow_name)
    if len(existing_wf) == 0:
        # no workflows had this name previously.  Need to create a new (unique!)
        # workflow_id.  query for all existing workflows 
        all_workflows = Workflow.objects.all()
        
        if len(all_workflows) == 0:
            workflow_id = 0
        else:
            max_id = max([x.workflow_id for x in all_workflows])
            workflow_id = max_id + 1
        # since this is the first time we 
        # add this workflow, the default version is zero
        version_id = 0 
    else:
        # get the id for this workflow:
        workflow_id = existing_wf[0].workflow_id
        max_version_id = max([x.version_id for x in existing_wf])
        version_id = max_version_id + 1

    # get the main WDL file:
    main_wdl = os.path.join(destination_dir, MAIN_WDL)
    if os.path.isfile(main_wdl):
        workflow_title, workflow_short_description, workflow_long_description = get_workflow_title_and_description(main_wdl)
    else:
        raise Exception('Zero main WDL files found.  This should not happen.  The main WDL must have been lost somehow??')

    # is there a pre-check WDL file, which determines if the workflow can be restarted:
    precheck_wdl = os.path.join(destination_dir, PRECHECK_WDL)
    if os.path.isfile(precheck_wdl):
        has_precheck = True
    else:
        has_precheck = False

    # now have a valid workflow and version ID.  Create the object
    workflow_location = os.path.relpath(destination_dir, APP_ROOT_DIR)
    wf = Workflow(
        workflow_id=workflow_id, 
        version_id=version_id, 
        is_default=False, 
        is_active=False, 
        workflow_name = workflow_name,
        workflow_location=workflow_location,
        workflow_title = workflow_title, 
        workflow_short_description = workflow_short_description,
        workflow_long_description = workflow_long_description,
        git_url = clone_url,
        git_commit_hash = commit_hash,
        restartable = has_precheck
    )
    wf.save()
    return wf

def link_django_template(workflow_libdir_name, workflow_dir, final_html_template_name):
    '''
    The templated HTML file is sitting in the destination_dir, but Django cannot find the template
    unless we locate it in one of the known template directories.  Here we choose the central location
    which is at 'templates' relative to the root of the django application.  We create a symlink from there
    back to the actual file located under the workflow library directory.

    '''
    # the abs path to the workflow library dir
    workflow_libdir = os.path.join(APP_ROOT_DIR, workflow_libdir_name)

    # now we can get the path of the html template relative to that workflow library dir:
    final_html_template_path = os.path.join(workflow_dir, final_html_template_name)
    relative_path = os.path.relpath(final_html_template_path, workflow_libdir)

    # the relative path lets us create the proper directory structure for linking
    linkpath = os.path.join(APP_ROOT_DIR, 'templates', workflow_libdir_name, relative_path)

    # need to make intermediate paths if necessary:
    linkdir = os.path.dirname(linkpath)
    if not os.path.isdir(linkdir):
        os.makedirs(linkdir)

    # finally, link them:
    os.symlink(final_html_template_path, linkpath)


def link_form_javascript(workflow_libdir_name, workflow_dir, javascript_filename):
    '''
    The templated HTML file is sitting in the destination_dir, but Django cannot treat it as 
    a static file unless we locate it in under the STATIC_ROOT dir.
    We create a symlink from there
    back to the actual file located under the workflow library directory.

    '''
    # the abs path to the workflow library dir
    workflow_libdir = os.path.join(APP_ROOT_DIR, workflow_libdir_name)

    # now we can get the path of the javascript relative to that workflow library dir:
    javascript_template_path = os.path.join(workflow_dir, javascript_filename)
    relative_path = os.path.relpath(javascript_template_path, workflow_libdir)

    # the relative path lets us create the proper directory structure for linking
    from django.conf import settings
    linkpath = os.path.join(settings.STATIC_ROOT, workflow_libdir_name, relative_path)

    # need to make intermediate paths if necessary:
    linkdir = os.path.dirname(linkpath)
    if not os.path.isdir(linkdir):
        os.makedirs(linkdir)

    # finally, link them:
    os.symlink(javascript_template_path, linkpath)

def link_form_css(workflow_libdir_name, workflow_dir, css_filename):
    '''
    The CSS file is sitting in the destination_dir, but Django cannot treat it as 
    a static file unless we locate it in under the STATIC_ROOT dir.
    We create a symlink from there
    back to the actual file located under the workflow library directory.

    '''
    # the abs path to the workflow library dir
    workflow_libdir = os.path.join(APP_ROOT_DIR, workflow_libdir_name)

    # now we can get the path of the CSS relative to that workflow library dir:
    css_path = os.path.join(workflow_dir, css_filename)
    relative_path = os.path.relpath(css_path, workflow_libdir)

    # the relative path lets us create the proper directory structure for linking
    from django.conf import settings
    linkpath = os.path.join(settings.STATIC_ROOT, workflow_libdir_name, relative_path)

    # need to make intermediate paths if necessary:
    linkdir = os.path.dirname(linkpath)
    if not os.path.isdir(linkdir):
        os.makedirs(linkdir)

    # finally, link them:
    os.symlink(css_path, linkpath)


def get_constraint_classnames():
    '''
    Returns a list of strings which give the class names of the available
    constraints (i.e. classes that derive from the base constraint type)
    '''
    import analysis.models
    from analysis.models import ImplementedConstraint
    # get a list of class names if the class derives from that base class above
    available_constraint_classnames = []
    for name, obj in inspect.getmembers(analysis.models):
        if inspect.isclass(obj):
            if obj.__base__ == ImplementedConstraint:
                available_constraint_classnames.append(name)
    return available_constraint_classnames


def register_constraints(workflow, staging_dir):
    '''
    Here we parse (if present) a file that defines various constraints that may be placed
    on this workflow when an analysis project is initiated.
    '''
    from analysis.models import WorkflowConstraint

    # get a list of class names if the class derives from that base class above
    available_constraint_classnames = get_constraint_classnames()

    required_keys = set(['type','handler','description'])
    constraint_filepath = os.path.join(staging_dir, CONSTRAINTS_JSON)
    if os.path.exists(constraint_filepath):
        j = json.load(open(constraint_filepath))
        if not type(j) == dict:
            raise ConstraintFileFormatException('Please check your formatting of the constraint file located at %s.  '
                'It should be parsed as a native dictionary when parsed by json.load' % constraint_filepath
            )
        for constraint_name, constraint_obj in j.items():
            # iterate through the elements of the constraints file, check that they meet the minimum 
            # requirements to be valid.
            keyset = required_keys.difference(constraint_obj.keys())
            if len(keyset) > 0: # this means some keys were missing in the constraint file
                raise ConstraintFileKeyException('The set of required keys is %s.  The following keys '
                    'were NOT given in the "constraint object": %s' % (required_keys, keyset)
                )
            else:
                # Had the correct keys, at least.  Now check them each.

                # check that the specified class type is something we know of (child of WorkflowConstraint)
                constraint_classname = constraint_obj['type']
                if not constraint_classname in available_constraint_classnames:
                    raise ConstraintFileClassnameException('The class (%s) is not a subclass of analysis.models.WorkflowConstraint' % constraint_classname)
                # we now have an apparently valid type for the constraint.  Check that the handler file is present:
                handler_filename = constraint_obj['handler']
                module_path = os.path.join(staging_dir, handler_filename)
                if not os.path.exists(module_path):
                    raise HandlerConfigException('The handler file (%s) was not found in the staging directory.  '
                        'Ensure that the file is included with your distribution.' % handler_filename
                    )
                # handler is there.  Check that it has a function with the correct signature
                inspect_handler_module(module_path, 'check_constraints', 2)

                # now we have a proper handler and class.  The description is not strictly necessary, but we enforce it for clarity:
                description = constraint_obj['description']

                # Now make an object of the appropriate type and save.  Note that the 
                # value of the constraint is null
                c = WorkflowConstraint(
                    workflow=workflow,
                    name=constraint_name,
                    description=description,
                    handler=handler_filename,
                    implementation_class=constraint_classname
                )
                c.save()



def ingest_main(clone_dir, clone_url, commit_hash):
    '''
    clone_dir is the path to a local directory which has the workflow content
    clone_url is the path used to clone the repository
    commit_hash is the hash of the git commit so we can track the versioning
    in git.
    '''

    # Get the files we need to ingest: 
    file_dict = get_files(clone_dir)

    # Get the file specifying the GUI
    gui_spec_path = get_gui_spec(clone_dir)

    # We expect that the WDL files are correct and have been tested, as we are
    # not in the business of double-checking and writing additional parsers.
    # We first create a "staging" dir, where we attempt to create the GUI
    # If something goes wrong, those files will remain there and ideally one can
    # determine the error.  If everything works, the contents of the staging dir
    # will be copied to a final directory and the staging directory deleted.
    file_list = []
    for filepaths in file_dict.values():
        file_list.extend(filepaths)
    staging_dir = copy_to_staging_directory(*file_list, gui_spec_path)

    # Now that the files have been copied, we need to update the dict of paths so they 
    # correctly point at the staging directory:
    for filetype, filepaths in file_dict.items():
        file_dict[filetype] = [os.path.join(staging_dir, os.path.basename(x)) for x in filepaths] 

    # Need to check that there is an input template based on the WDL workflow:
    inputs_template_path = os.path.join(staging_dir, settings.WDL_INPUTS_TEMPLATE_NAME)
    if not os.path.isfile(inputs_template_path):
        raise MissingWdlInputTemplateException('Need a file %s to be included in '
        'the original workflow directory' % settings.WDL_INPUTS_TEMPLATE_NAME)

    # At this point, we have a staging directory with all the required files
    # To create the GUI template, we need the GUI spec, the staging dir, and the inputs
    # template to check against.
    # This function also updates the workflow GUI file, fillling in all the 
    # optional parameters with defaults
    final_html_template_path, final_javascript_path, final_css_path = gui_utils.construct_gui(
        staging_dir)
    file_dict[HTML] = [final_html_template_path] # put in a list for consistency
    file_dict[JS] = [final_javascript_path]
    file_dict[CSS] = [final_css_path]

    # Now that the gui spec has been updated to include default params, we need to
    # ensure that the correct python files are there.  This function copies all
    # the necessary handler python files into the staging dir.  It returns a list
    # of paths to those 
    handler_name_list = check_handlers(staging_dir)

    # As a safeguard, check that the docker images used in the workflow are properly 
    # versioned and already exist in the docker registry
    check_runtime_docker_containers(staging_dir)

    # above, it was just names of files, not paths.  Create paths, and add them
    # to the dictionary of files that will be copied to the final workflow dir
    handler_path_list = [os.path.join(staging_dir, x) for x in handler_name_list]
    file_dict[PYFILE] = list(set(file_dict[PYFILE]).union(handler_path_list))

    # create a location to copy the files to:
    # This dir will be at <workflow_name>/<stamp> relative to the workflows_dir.
    # <stamp> is a string used to identify unique subversions of the workflow
    # with a name of <workflow_name>
    main_wdl_paths = [x for x in file_dict[WDL] if os.path.basename(x) == MAIN_WDL]
    if len(main_wdl_paths) != 1:
        raise WdlImportException('Could not locate %s, or there were > 1.  Result was: %s ' % (MAIN_WDL,main_wdl_paths))
    workflow_name = get_workflow_name(main_wdl_paths[0])
    destination_dir = create_workflow_destination(workflow_name)

    # copy the files over.  Rather than copying everything, only copy over the
    # accepted file types 
    for filetype, filepaths in file_dict.items():
        for fp in filepaths:
            shutil.copy2(fp, destination_dir)

    # add the workflow to the database
    workflow = add_workflow_to_db(workflow_name, destination_dir, clone_url, commit_hash)

    # link the html template so Django can find it
    link_django_template(WORKFLOWS_DIR, destination_dir, settings.HTML_TEMPLATE_NAME)
    link_form_javascript(WORKFLOWS_DIR, destination_dir, settings.FORM_JAVASCRIPT_NAME)
    link_form_css(WORKFLOWS_DIR, destination_dir, settings.FORM_CSS_NAME)

    # look for and register any constraints that can be applied to this new workflow
    register_constraints(workflow, staging_dir)

    # cleanup the staging dir:
    shutil.rmtree(staging_dir)

    # destination_dir is the absolute path to the directory we want to copy
    # first get the relative path:
    rel_path = os.path.relpath(destination_dir, APP_ROOT_DIR)
    host_location = os.path.join('/host_mount', settings.STATIC_LOC, rel_path)

    # for workflows that are completely new, the intermediate directories may not be there
    if not os.path.exists(host_location):
        os.makedirs(host_location)

    # The files in the container inside the static folder are symlinked back to the workflow dir
    # The -L flag copies the actual file, since we cannot symlink out of the container
    cp_command = 'cp -rL %s %s' % (destination_dir, host_location)
    call_external(cp_command)

    # let the user know where the final files are:
    print('Success!  Your new workflow has been added to the database and the files are located at %s' % destination_dir)


if __name__ == '__main__':
    '''
    If this script is called from the commandline
    '''

    if os.getcwd() != APP_ROOT_DIR:
        print('Please execute this script from %s.  Exiting.' % APP_ROOT_DIR)
        sys.exit(1)

    # First parse any commandline args and configuration params:
    arg_dict = parse_commandline()

    # call the main worker function
    ingest_main(arg_dict[NEW_WDL_DIR], arg_dict[CLONE_URL], arg_dict[COMMIT_HASH])
