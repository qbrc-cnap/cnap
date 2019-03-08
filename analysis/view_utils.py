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
CONTEXT_ARGS = settings.CONTEXT_ARGS


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
                if CONTEXT_ARGS in display_element:
                    context_args = display_element[CONTEXT_ARGS]
                else:
                    context_args = {}
                mod.add_to_context(request, workflow_obj, context_dict, context_args)
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
    if version_id is not None:
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

def start_job_on_gcp(request, data, workflow_obj):
    '''
    Starts the process of instantiating the workflow  

    `data` is a dictionary of the payload POST'd from the frontend
    '''
    workflow_dir = workflow_obj.workflow_location
    location = os.path.join(settings.BASE_DIR, workflow_dir)
    data[analysis_tasks.WORKFLOW_LOCATION] = location
    data[analysis_tasks.USER_PK] = request.user.pk
    analysis_tasks.start_workflow.delay(data)

