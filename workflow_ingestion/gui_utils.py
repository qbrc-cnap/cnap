import os
import sys
import json

from jinja2 import Environment, FileSystemLoader

# for easy reference, determine the directory we are currently in
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_ROOT_DIR = os.path.dirname(THIS_DIR)

# add the app root dir to the syspath
sys.path.append(APP_ROOT_DIR)

# need all this to get the django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cnap_v2.settings')
import django
from django.conf import settings
django.setup()

# Some constants (only referenced here):
GUI_SCHEMA_PATH = 'gui_schema.json'
GUI_ELEMENTS = 'gui_elements'
MASTER_HTML_TEMPLATE = 'master_html_template'
MASTER_JS_TEMPLATE = 'master_javascript_template'
MASTER_CSS_TEMPLATE = 'master_css_template'
JS_HANDLER = 'js_handler'

# Other constants that are used in various locations
# have been stored in the settings module
INPUT_ELEMENTS = settings.INPUT_ELEMENTS
TARGET = settings.TARGET
TARGET_IDS = settings.TARGET_IDS
DISPLAY_ELEMENT = settings.DISPLAY_ELEMENT


class UnknownGuiElementException(Exception):
    '''
    This is raised when the user-specified GUI declares an input 
    that we do not have a schema for.
    '''
    pass


class InvalidGuiMappingException(Exception):
    '''
    This is raised if the user-specified GUI attempts to map
    to a Workflow input that does not exist.
    '''
    pass


class ConfigurationException(Exception):
    '''
    This is kind of a general, catch-all
    exception that is raised if a KeyError is
    thrown, which indicates the key was missing due to
    an incorrect specification
    '''
    pass

class MissingRequiredParameterException(Exception):
    '''
    This is raised when a GUI element that requires a value is omitted
    in the creator-defined GUI spec.
    '''


def check_input_mapping(input_element, workflow_input_list):
    '''
    input_element is a dictionary with keys of TARGET and 
    DISPLAY_ELEMENT.  TARGET defines which WDL input(s) the GUI
    element maps to

    workflow_input_list is a list of strings, which are the IDs
    of the required inputs for the workflow.

    If the mapping is made correctly, do nothing.  Otherwise raise
    an exception
    '''
    if TARGET in input_element:
        target_spec = input_element[TARGET]

        # as described in the docs, the target can either be a string
        # OR a JSON-object (a dict in python)
        if type(target_spec) == str:
            # put in a list so we handle in a consistent manner
            all_input_targets = [target_spec,]
        elif type(target_spec) == dict:
            all_input_targets = list(set(target_spec[TARGET_IDS]))
        else:
            raise InvalidGuiMappingException('The specification of'
                ' your target was not correct.  It was of type %s and'
                ' we expect only "str" or "dict" types.' % type(target_spec)
            )

        # now that we have a list of the intended targets, check that they are in fact
        # correctly spelled and can be mapped to the required inputs to the WDL:
        for t in all_input_targets:
            if not t in workflow_input_list:
                raise InvalidGuiMappingException('The target %s is not in the list of '
                    'required inputs to the WDL.' % t
                )
        return all_input_targets

    else:
        raise InvalidGuiMappingException('Could not find a mapping'
            ' from your GUI element to the workflow for input element: %s'
            % input_element
        )


def check_known_input_element(display_element, gui_schema_element_names):
    '''
    Checks that the GUI input element specified was valid.
    If OK, does nothing (simply returns).  Otherwise raise
    an exception
    '''
    if display_element['type'] in gui_schema_element_names:
        return display_element['type']
    else:
        raise UnknownGuiElementException('The GUI element type '
            'was given as %s, and the set of known types is %s.' %
            (display_element['type'], gui_schema_element_names)
        ) 


def check_element_parameters(display_element, element_schema):
    '''
    The display_element input is a dict that specifies how the user
    would like to configure/display the UI element.

    The element_schema input is a dictionary giving the configuration
    options for the particular element type given in display_element.

    In this function we check that all the required parameters were present
    If not, raise an exception. 
    '''

    for parameter_spec in element_schema['parameters']:
        parameter_name = parameter_spec['name']
        if parameter_spec['required']:
            if not parameter_name in display_element:
                raise MissingRequiredParameterException(
                    'Your input element was given as: %s\n\n'
                    'However, for this element type you need to '
                    'specify the required parameter %s' %
                    (display_element, parameter_name)
                )
      

def get_jinja_template(template_path):

    # load the environment/template for the jinja template engine: 
    template_dir = os.path.realpath(
        os.path.abspath(
            os.path.dirname(
                os.path.join(THIS_DIR, template_path)
            )
        )
    )
    env = Environment(loader=FileSystemLoader(template_dir))
    return env.get_template(
        os.path.basename(template_path)
    )


def fill_html_template(input_element, 
    element_schema, 
    display_element_type, idx):
    '''
    Using the parameters specified, construct the "context" for
    filling out the HTML template.  Return the template
    as a string

    idx is used for creating unique id's in the case of multiple
    elements having the same type
    '''
    html_template_path = element_schema['html_source']
    html_template = get_jinja_template(html_template_path)

    # we use the 'name' field for each form element in the UI
    # this way we can map the input elements to the CWL inputs
    if TARGET in input_element:
        target_spec = input_element[TARGET]

        # if the target is a string, then we know it directly
        # maps to a WDL input.  Just use that as the name
        if type(target_spec) == str:
            name = target_spec

        # if the target key points at a dict, the GUI element's data
        # can subsequently map to potentially multiple WDL inputs
        # thus, we need a 'name' parameter to track this
        elif type(target_spec) == dict:
            try:
                name = target_spec['name']
            except KeyError:
                raise ConfigurationException('If your GUI target has'
                    ' type "dict", then a "name" parameter needs to be'
                    ' declared so we can map to the workflow inputs.'
                )

        else:
            raise InvalidGuiMappingException('The type of the target'
                ' specification was not recognized.  Generally, this'
                ' exception should be caught before, so something is awry.'
            )

    # now construct the dictionary which defines how the template is filled
    context = {'id': idx, 'name': name}
    display_element = input_element[DISPLAY_ELEMENT]
    for param_dict in element_schema['parameters']:
        param_name = param_dict['name']
        if param_name in display_element:
            context[param_name] = display_element[param_name]
        else:
            # add the default to the display_element object
            display_element[param_name] = param_dict['default']
            context[param_name] = param_dict['default']
    return html_template.render(context)


def fill_final_template(master_template_path, 
    final_template_path, form_elements):
        
    # fill-in the overall template:
    ui_template = get_jinja_template(master_template_path)
    context = {'form_elements': form_elements}
    ui = ui_template.render(context)

    # write to the final file:
    with open(final_template_path, 'w') as fout:
        # note that we have to wrap the template with django
        # tags here, rather than in the original template.  
        # Otherwise jinja does not recognize the tags and fails.
        #fout.write("{% extends 'base.html' %}\n")
        #fout.write('{% block content %}\n')
        fout.write(ui)
        #fout.write('{% endblock%}\n')


def fill_css_template(css_template_path, final_css_path):
    '''
    Fills in any customized CSS, adding it to the master CSS and writing to the final path
    '''
    #TODO implement custom CSS
    with open(final_css_path, 'w') as fout:
        css_template = get_jinja_template(css_template_path)
        context = {}
        css_str = css_template.render(context)
        fout.write(css_str)


def fill_javascript_template(gui_schema, javascript_template_path,
    final_javascript_path, 
    element_type_list):
    '''
    `gui_schema` is the schema (a dict) of all the potential UI elements
    and the params
    `javascript_template_path` gives the path to the template we have to fill-in
    `final_javascript_path` gives the path of the file to which we write the completed
    template
    `element_type_list` is a list of the "types" of the input elements that are 
    featured in the UI we are creating.
    '''
    js_handlers = []
    for element_type in set(element_type_list):
        element_spec = gui_schema[GUI_ELEMENTS][element_type]
        js_handler = element_spec[JS_HANDLER]
        if js_handler:
            js_handler = os.path.join(THIS_DIR, js_handler)
            if os.path.isfile(js_handler):
                js_handlers.append(open(js_handler).read())
            else:
                raise Exception('Problem! Could not locate the javascript handler at %s' % js_handler)
    # fill-in the overall template:
    js_template = get_jinja_template(javascript_template_path)
    context = {'js_handlers': js_handlers}
    full_js_str = js_template.render(context)

    # write to the final file:
    with open(final_javascript_path, 'w') as fout:
        # note that we have to wrap the template with django
        # tags here, rather than in the original template.  
        # Otherwise jinja does not recognize the tags and fails.
        fout.write(full_js_str)
    

def construct_gui(staging_dir):
    '''
    This is the main entrypoint to constructing a HTML GUI
    based on the specifications provided in the JSON-format
    file (at workflow_gui_spec_filepath).

    staging_dir is the path to a directory containing all the relevant files

    Comments below (and in functions) explain the various steps
    in the ingestion process
    '''

    # load the schema which allows basic checks
    gui_schema = json.load(open(os.path.join(THIS_DIR, GUI_SCHEMA_PATH)))

    # load the GUI spec file into a dict
    workflow_gui_spec_filename = settings.USER_GUI_SPEC_NAME
    workflow_gui_spec_path = os.path.join(staging_dir, workflow_gui_spec_filename)
    workflow_gui_spec = json.load(open(workflow_gui_spec_path))

    # load the input template which gives the required inputs to the workflow
    workflow_inputs_filename = settings.WDL_INPUTS_TEMPLATE_NAME
    workflow_inputs_path = os.path.join(staging_dir, workflow_inputs_filename)
    workflow_inputs = json.load(open(workflow_inputs_path))

    # get a set of the known GUI elements that are available:
    gui_schema_element_names = gui_schema[GUI_ELEMENTS].keys()

    # iterate through the input elements, and add the completed
    # html strings to a list
    form_elements = []

    # this list tracks the different types of input elements
    # These are the keys in the `gui_elements` object of the GUI
    # schema (e.g. 'file_chooser', 'text')
    element_type_list = []
    mapped_input_list = []
    for i, input_element in enumerate(workflow_gui_spec[INPUT_ELEMENTS]):

        # ensure that we are mapping the inputs to a known WDL input:
        mapped_inputs_for_element = check_input_mapping(input_element, workflow_inputs.keys())
        mapped_input_list.extend(mapped_inputs_for_element)

        # ensure that the input element specifies a known GUI element
        display_element = input_element[DISPLAY_ELEMENT]
        display_element_type = check_known_input_element(
            display_element, 
            gui_schema_element_names
        )
        element_type_list.append(display_element_type)

        # Now that we know we are properly mapping to a WDL input and
        # that the UI element is at least known, we need to check that the
        # required parameters for that element were specified.
        check_element_parameters(display_element, 
            gui_schema[GUI_ELEMENTS][display_element_type])

        # Now fill-in the portions of the GUI html template that do not require 
        # dynamic, database-given input.
        element_html_str = fill_html_template(input_element, 
            gui_schema[GUI_ELEMENTS][display_element_type], display_element_type, i)
        form_elements.append(element_html_str)

    # write an updated GUI spec (which includes the default params)
    with open(workflow_gui_spec_path, 'w') as fout:
        json.dump(workflow_gui_spec, fout)

    # using the list of the element types, collect the necessary javascript
    javascript_template_path = gui_schema[MASTER_JS_TEMPLATE]
    final_javascript_path = os.path.join(staging_dir, 
        settings.FORM_JAVASCRIPT_NAME)
    fill_javascript_template(gui_schema, javascript_template_path,
        final_javascript_path, 
        element_type_list)

    # collect the CSS for the form:
    css_template_path = gui_schema[MASTER_CSS_TEMPLATE]
    final_css_path = os.path.join(staging_dir, settings.FORM_CSS_NAME)
    fill_css_template(css_template_path, final_css_path)

    # It's possible that some of the WDL inputs are created at runtime and do not 
    # have direct GUI elements that pass data to them.  We simply warn about those.
    set_diff = set(workflow_inputs.keys()).difference(set(mapped_input_list)) 
    if len(set_diff) > 0:
        for s in set_diff:
            print('Warning: You have a required input (%s) that was not mapped to a GUI element.' 
                'This is not necessarily an error, however.' % s
            )

    master_template_path = gui_schema[MASTER_HTML_TEMPLATE]
    final_template_path = os.path.join(staging_dir, settings.HTML_TEMPLATE_NAME)
    fill_final_template(master_template_path, final_template_path, form_elements)
    return final_template_path, final_javascript_path, final_css_path



        


