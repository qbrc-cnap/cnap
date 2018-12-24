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
import subprocess as sp
from importlib import import_module
from inspect import signature

import gui_utils

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
ACCEPTED_FILE_EXTENSIONS = [WDL, PYFILE, ZIP, JSON]

# Other constants:
NEW_WDL_DIR = 'wdl_dir' # a string used for common reference.  Value arbitrary.
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
        help='Path to a directory containing CWL '
             'files, GUI specs, and other files to be incorporated.'
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

    # expect only a single WDL file:
    if len(file_dict[WDL]) != 1:
        raise WdlImportException('There needs to be a single WDL '
            'file in the %s directory' % wdl_directory)

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


def create_input_template(file_dict, staging_dir, inputs_template_filename):
    '''
    The input arg is a path to a directory containing staged files
    There is a single WDL file giving the definition

    Note that to run the WOM tool, we might need to unzip the archive
    of task (or subworkflow) WDL files if such an archive exists.

    This function calls out to the WOMtool which creates the input template
    required to run the WDL
    '''
    main_wdl_file = file_dict[WDL][0]
    try:
        zip_file = file_dict[ZIP][0]
        unzip_cmd = 'unzip %s -d %s' % (
            os.path.join(staging_dir, zip_file), 
            staging_dir
        )
        call_external(unzip_cmd) 
    except IndexError:
        # there was no zip file (so the key was pointing at an empty list).
        # Nothing to do and not an error, so simply pass 
        pass

    # try to run the WOMtool:
    inputs_template_path = os.path.join(staging_dir, inputs_template_filename)
    cmd = 'java -jar %s inputs %s > %s' % (WOMTOOL_JAR, 
            main_wdl_file, 
            inputs_template_path
        )
    call_external(cmd)

    return inputs_template_path


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

    # we are looking in the meta section, so grab that
    meta_pattern = r'meta\s+\{.*?\}'
    f = open(wdl_path).read()
    m=re.search(meta_pattern, f, flags=re.DOTALL)
    if m:
        print('META section FOUND')
        meta_section_text = m.group(0)

        # find 'workflow_title' if it exists
        title_regex = 'workflow_title\s*=\s*([a-zA-Z][a-zA-Z0-9_]+)'
        m1 = re.search(title_regex, meta_section_text)
        if m1:
            print('found title')
            title = m1.group(1)
            print('title was %s' % title)
        else:
            title = get_workflow_name(wdl_path)

        # find 'workflow_description if it exists
        description_regex = 'workflow_description\s*=\s*(.*)'
        m2 = re.search(description_regex, meta_section_text)
        if m2:
            print('found desc')
            description = m2.group(1)
        else:
            description = ''
    else: # no meta section:
        title = get_workflow_name(wdl_path)
        description = ''

    return title, description


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
            inspect_handler_module(module_path, 'add_to_context', 2)    
            
            handler_module_list.append(module_name)

            # again, update the GUI dict for the same reason as above
            display_element[HANDLER] = module_name
    
    # rewrite the GUI spec since we changed the module names to be relative.
    with open(workflow_gui_spec_path, 'w') as fout:
        json.dump(workflow_gui_spec, fout)
    return handler_module_list

def add_workflow_to_db(workflow_name, destination_dir):
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

    # get the WDL file:
    wildcard_path = os.path.join(destination_dir, '*' + WDL)
    matches = glob.glob(wildcard_path)
    if len(matches) > 0:
        wdl_path = matches[0]
        workflow_title, workflow_description = get_workflow_title_and_description(wdl_path)
    else:
        raise Exception('Zero WDL files found.  This should not happen.')

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
        workflow_description = workflow_description
    )
    wf.save()

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


if __name__ == '__main__':
    '''
    This script is always called from the commandline
    '''

    if os.getcwd() != APP_ROOT_DIR:
        print('Please execute this script from %s.  Exiting.' % APP_ROOT_DIR)
        sys.exit(1)

    # First parse any commandline args and configuration params:
    arg_dict = parse_commandline()

    # Get the files we need to ingest: 
    file_dict = get_files(arg_dict[NEW_WDL_DIR])

    # Get the file specifying the GUI
    gui_spec_path = get_gui_spec(arg_dict[NEW_WDL_DIR])

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

    # Need to create an input template based on the WDL workflow:
    inputs_template_path = create_input_template(file_dict, staging_dir, 
        settings.WDL_INPUTS_TEMPLATE_NAME)
    file_dict[JSON].append(inputs_template_path)

    # At this point, we have a staging directory with all the required files
    # To create the GUI template, we need the GUI spec, the staging dir, and the inputs
    # template to check against.
    # This function also updates the workflow GUI file, fillling in all the 
    # optional parameters with defaults
    final_html_template_path, final_javascript_path = gui_utils.construct_gui(
        staging_dir)
    file_dict[HTML] = [final_html_template_path] # put in a list for consistency
    file_dict[JS] = [final_javascript_path]

    # Now that the gui spec has been updated to include default params, we need to
    # ensure that the correct python files are there.  This function copies all
    # the necessary handler python files into the staging dir.  It returns a list
    # of paths to those 
    handler_name_list = check_handlers(staging_dir)

    # above, it was just names of files, not paths.  Create paths, and add them
    # to the dictionary of files that will be copied to the final workflow dir
    handler_path_list = [os.path.join(staging_dir, x) for x in handler_name_list]
    file_dict[PYFILE] = list(set(file_dict[PYFILE]).union(handler_path_list))

    # create a location to copy the files to:
    # This dir will be at <workflow_name>/<stamp> relative to the workflows_dir.
    # <stamp> is a string used to identify unique subversions of the workflow
    # with a name of <workflow_name>
    wdl_path = file_dict[WDL][0]
    workflow_name = get_workflow_name(wdl_path)
    destination_dir = create_workflow_destination(workflow_name)

    # copy the files over.  Rather than copying everything, only copy over the
    # accepted file types 
    for filetype, filepaths in file_dict.items():
        for fp in filepaths:
            shutil.copy2(fp, destination_dir)

    # add the workflow to the database
    add_workflow_to_db(workflow_name, destination_dir)

    # link the html template so Django can find it
    link_django_template(WORKFLOWS_DIR, destination_dir, settings.HTML_TEMPLATE_NAME)
    link_form_javascript(WORKFLOWS_DIR, destination_dir, settings.FORM_JAVASCRIPT_NAME)
 
    # cleanup the staging dir:
    shutil.rmtree(staging_dir)
