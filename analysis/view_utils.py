import os
import sys
import json
from importlib import import_module

from django.conf import settings

from .models import Workflow

def fill_context(request, workflow_obj, context_dict):
    '''
    This function orchestrates adding content to the context dict
    by going through the handlers defined in the GUI spec

    `workflow_obj` is an instance of a Workflow
    `context_dict` is a dictionary which will be used to fill-in
    the ui.
    '''

    # get the location of the workflow (which is relative to the root of the app)
    # and make it absolute by prepending BASE_DIR
    location = workflow_obj.workflow_location
    location = os.path.join(settings.BASE_DIR, location)

    # add the workflow location to the python path, so modules can be found there first
    # in case of name clashes
    sys.path.insert(0, location)

    # Load the GUI spec, which we parse to get the python modules used
    # to load custom dynamic content
    gui_spec_path = os.path.join(location, settings.USER_GUI_SPEC_NAME)
    if os.path.isfile(gui_spec_path):
        gui_spec = json.load(open(gui_spec_path))
        for input_element in gui_spec['input_elements']:
            display_element = input_element['display_element']
            if 'handler' in display_element:
                module_name = display_element['handler'][:-len(settings.PY_SUFFIX)]
                mod = import_module(module_name)
                mod.add_to_context(request, context_dict)
    else:
        raise Exception('The GUI specification was not found in the correct '
            'location.  Something (or someone) has corrupted the '
            'workflow directory at %s' % location
        )

    # remove the workflow dir so it doesn't clutter the python path
    sys.path.remove(location)




def get_workflow(workflow_id, version_id=None, admin_request=False):
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
        raise Exception('The workflow with workflow_id=%s was not found' % workflow_id) 
    
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
                    raise Exception('A non-admin cannot request an inactive workflow.')
        else:
            raise  Exception('There should only be a single workflow returned when querying for '
                'workflow_id=%s and version_id=%s.' % (workflow_id, version_id)
            )
    else:
        raise Exception('No workflow was found.')


def validate_workflow_dir(workflow_obj):
    '''
    `workflow_obj` is a Workflow object from the database.

    In this function, we check that all the required files, etc. are there.
    This is performed as part of the ingestion, but we need to double-check
    in case something was corrupted.

    returns True or False depending on whether it checks out correctly.
    '''
    location = workflow_obj.workflow_location
    if os.path.isdir(os.path.join(settings.BASE_DIR, location)):

        if not os.path.isfile(os.path.join(location, settings.USER_GUI_SPEC_NAME)):
            raise Exception('GUI spec file not found.')
        if not os.path.isfile(os.path.join(location, settings.WDL_INPUTS_TEMPLATE_NAME)):
            raise Exception('WDL inputs template file not found.')
        if not os.path.isfile(os.path.join(location, settings.HTML_TEMPLATE_NAME)):
            raise Exception('HTML template file not found.')
        
        wdl_files = [x for x in os.listdir(location) 
            if x.split('.')[-1].lower() == settings.WDL 
        ]
        if len(wdl_files) != 1:
            raise Exception('There were %d WDL files found in %s.  There '
                'needs to be exactly one.  Something (or SOMEONE!) has corrupted the '
                'workflow directory.' % (len(wdl_files), location)
            )

        return True
    else:
        return False
