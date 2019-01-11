import os
import glob
import shutil
import sys
import json
import datetime
from importlib import import_module

from jinja2 import Environment, FileSystemLoader

from django.conf import settings
from django.http import HttpResponseBadRequest
from django.contrib.auth import get_user_model

from analysis.models import Workflow, AnalysisProject
import analysis.tasks as analysis_tasks

INPUT_ELEMENTS = settings.INPUT_ELEMENTS
DISPLAY_ELEMENT = settings.DISPLAY_ELEMENT
HANDLER = settings.HANDLER
TARGET = settings.TARGET
TARGET_IDS = settings.TARGET_IDS
NAME = settings.NAME
WORKFLOW_ID = settings.WORKFLOW_ID
VERSION_ID = settings.VERSION_ID
WORKFLOW_LOCATION = 'location'
USER_PK = 'user_pk'


class MissingGuiSpecException(Exception):
    pass

class WdlCountException(Exception):
    pass

class MissingHtmlTemplateException(Exception):
    pass

class NonexistentWorkflowException(Exception):
    pass

class InactiveWorkflowException(Exception):
    pass

class MissingDataException(Exception):
    pass

class MissingMappingHandlerException(Exception):
    pass

class InputMappingException(Exception):
    pass


def create_module_dot_path(filepath):
    location_relative_to_basedir = os.path.relpath(filepath, start=settings.BASE_DIR)
    return location_relative_to_basedir.replace('/', '.')


def fill_context(request, workflow_obj, context_dict):
    '''
    This function orchestrates adding content to the context dict
    by going through the handlers defined in the GUI spec

    `workflow_obj` is an instance of a Workflow
    `context_dict` is a dictionary which will be used to fill-in
    the ui.  Dictionaries are passed by reference, so the additions
    to this dict persist to the caller.
    '''

    # get the location of the workflow (which is relative to the root of the app)
    # and make it absolute by prepending BASE_DIR
    location = workflow_obj.workflow_location
    location = os.path.join(settings.BASE_DIR, location)
    module_location = create_module_dot_path(location)

    # Load the GUI spec, which we parse to get the python modules used
    # to load custom dynamic content (the `handler` key)
    gui_spec_path = os.path.join(location, settings.USER_GUI_SPEC_NAME)
    if os.path.isfile(gui_spec_path):
        gui_spec = json.load(open(gui_spec_path))
        for input_element in gui_spec[INPUT_ELEMENTS]:
            display_element = input_element[DISPLAY_ELEMENT]
            if HANDLER in display_element:
                module_name = display_element[HANDLER][:-len(settings.PY_SUFFIX)]
                module_name = module_location + '.' + module_name
                mod = import_module(module_name)
                mod.add_to_context(request, context_dict)
    else:
        raise Exception('The GUI specification was not found in the correct '
            'location.  Something (or someone) has corrupted the '
            'workflow directory at %s' % location
        )



def query_workflow(workflow_id, version_id=None, admin_request=False):
    '''
    This function will return a Workflow object from the database, which
    allows the frontend view to display the proper content.

    `workflow_id` is an integer which was parsed from the URL
    `version_id` is an optional integer which specifies a particular
        version of a workflow
    `admin_request` is a boolean which allows admin users to see 'inactive'
        workflows.  Otherwise, requests inactive workflows are rejected. 
    ''' 
    # first query for the workflow ID.  
    # If nothing was found immediately raise an exception
    workflow_obj_queryset = Workflow.objects.filter(workflow_id=workflow_id)
    if not workflow_obj_queryset.exists():
        raise NonexistentWorkflowException('The workflow with workflow_id=%s was not found' % workflow_id) 
    
    # If a version was specified, get that. Otherwise, get the default
    if version_id:
        workflow_obj = workflow_obj_queryset.filter(version_id=version_id)
    else:
        workflow_obj = workflow_obj_queryset.filter(is_default=True)

    # Obviously we need to have a result at this point, or we throw an exception
    if workflow_obj.exists():

        # there should only be one result returned.  Otherwise, we have a problem.
        if len(workflow_obj) == 1:

            # regardless of which workflow we received, need to check that it is active
            workflow_obj = workflow_obj[0]
            if workflow_obj.is_active:
                return workflow_obj
            else:
                # admins can request inactive workflows (mainly for live-testing purpose)
                if admin_request:
                    return workflow_obj
                else:
                    raise InactiveWorkflowException('A non-admin cannot request an inactive workflow.')
        else:
            raise  Exception('There should only be a single workflow returned when querying for '
                'workflow_id=%s and version_id=%s.' % (workflow_id, version_id)
            )
    else:
        raise NonexistentWorkflowException('No workflow was found.')


def validate_workflow_dir(workflow_obj):
    '''
    `workflow_obj` is a Workflow object from the database.

    In this function, we check that all the required files, etc. are there.
    This is performed as part of the ingestion, but we need to double-check
    in case something was corrupted.

    returns True or False depending on whether it checks out correctly.

    Does not do any checking of the contents of the files themselves.  Some of that
    was handled during the ingestion of the workflow
    '''
    location = workflow_obj.workflow_location
    if os.path.isdir(os.path.join(settings.BASE_DIR, location)):

        if not os.path.isfile(os.path.join(location, settings.USER_GUI_SPEC_NAME)):
            raise MissingGuiSpecException('GUI spec file not found.')
        if not os.path.isfile(os.path.join(location, settings.WDL_INPUTS_TEMPLATE_NAME)):
            raise Exception('WDL inputs template file not found.')
        if not os.path.isfile(os.path.join(location, settings.HTML_TEMPLATE_NAME)):
            raise MissingHtmlTemplateException('HTML template file not found.')
        
        wdl_files = [x for x in os.listdir(location) 
            if x.split('.')[-1].lower() == settings.WDL 
        ]
        if len(wdl_files) != 1:
            raise WdlCountException('There were %d WDL files found in %s.  There '
                'needs to be exactly one.  Something (or SOMEONE!) has corrupted the '
                'workflow directory.' % (len(wdl_files), location)
            )

        return True
    else:
        return False


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
    for element in gui_spec_json[INPUT_ELEMENTS]:
        target = element[TARGET]
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
            if target[NAME] in data:
                unmapped_data = data[target[NAME]]

                # unmapped_data could effectively be anything.  Its format
                # is dictated by some javascript code.  For example, a file chooser
                # could send data to the backend in a variety of formats, and that format
                # is determined solely by the author of the workflow.  We need to have custom
                # code which takes that payload and properly maps it to the WDL inputs

                # Get the handler code:
                handler_path = os.path.join(absolute_workflow_dir, target[HANDLER])
                if os.path.isfile(handler_path):
                    # we have a proper file.  Call that to map our unmapped_data
                    # to the WDL inputs
                    module_name = target[HANDLER][:-len(settings.PY_SUFFIX)]
                    module_location = create_module_dot_path(absolute_workflow_dir)
                    module_name = module_location + '.' + module_name
                    mod = import_module(module_name)
                    map_dict = mod.map_inputs(user, unmapped_data, target[TARGET_IDS])
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


def start_job_on_gcp(request, data, workflow_obj):
    '''
    Starts the process of instantiating the workflow  

    `data` is a dictionary of the payload POST'd from the frontend
    '''
    workflow_dir = workflow_obj.workflow_location
    location = os.path.join(settings.BASE_DIR, workflow_dir)
    data[WORKFLOW_LOCATION] = location
    data[USER_PK] = request.user.pk
    analysis_tasks.start_workflow(data)
    print('task started...')


