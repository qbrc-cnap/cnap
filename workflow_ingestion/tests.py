import os
import shutil
import json
import tempfile

#from unittest import TestCase
from django.test import TestCase
import unittest.mock as mock

THIS_DIR = os.path.realpath(os.path.abspath(os.path.dirname(__file__)))
TEST_UTILS_DIR = os.path.join(THIS_DIR, 'test_utils')

from .ingest_workflow import locate_handler, \
    copy_handler_if_necessary, inspect_handler_module, \
    get_files, query_for_tag, parse_docker_runtime_declaration, \
    check_runtime, register_constraints, \
    MissingHandlerException, HandlerConfigException, WdlImportException, \
    RuntimeDockerException, \
    ConstraintFileFormatException, \
    ConstraintFileClassnameException, \
    ConstraintFileKeyException, \
    WDL, PYFILE, ZIP, JSON, CONSTRAINTS_JSON

from .gui_utils import check_input_mapping, fill_html_and_js_template, \
    check_known_input_element, TARGET, TARGET_IDS, DISPLAY_ELEMENT, GUI_ELEMENTS, \
    InvalidGuiMappingException, \
    ConfigurationException, UnknownGuiElementException


def mock_listdir(d):
    return ['main.wdl', 'sub.wdl', 'bar.py', 'gui.json']

def mock_abspath(d):
    return d

def mock_realpath(d):
    return d

class TestWorkflowIngestion(TestCase):
    '''
    This test class covers some common issues that we can test when ingesting
    the workflow
    '''

    @mock.patch('workflow_ingestion.ingest_workflow.os')
    def test_missing_main_wdl_file_raises_ex(self, mock_os):
        mock_os.listdir.return_value = ['foo.wdl', 'bar.py', 'gui.json']
        with self.assertRaises(WdlImportException):
           get_files('/www/mydir')


    @mock.patch('workflow_ingestion.ingest_workflow.os.listdir', new=mock_listdir)
    @mock.patch('workflow_ingestion.ingest_workflow.os.path.abspath', new=mock_abspath)
    @mock.patch('workflow_ingestion.ingest_workflow.os.path.realpath', new=mock_realpath)
    def test_multiple_wdl_file_correctly_configured_returns_expected(self):
        file_dict = get_files('/www/mydir')
        expected_dict = {
            PYFILE: ['/www/mydir/bar.py'],
            ZIP: [],
            JSON: ['/www/mydir/gui.json'],
            WDL: ['/www/mydir/main.wdl', '/www/mydir/sub.wdl'],
        }
        self.assertEqual(file_dict, expected_dict)

    def test_missing_handler_module_returns_none(self):
        '''
        This tests that the function responsible for finding the 
        handler returns None if it is not found
        '''
        with mock.patch('workflow_ingestion.ingest_workflow.os.path.isfile', side_effect=[False, False]):
            locations = ['/foo/bar', 'foo/baz']
            returnval = locate_handler('modname', locations)
            self.assertEqual(None, returnval)

    def test_handler_module_returns_proper_path(self):
        '''
        This tests that the function responsible for finding the 
        handler returns the proper path if it is found
        '''
        with mock.patch('workflow_ingestion.ingest_workflow.os.path.isfile', side_effect=[False, True]):
            locations = ['/foo/bar', '/foo/baz']
            returnval = locate_handler('modname', locations)
            self.assertEqual('/foo/baz/modname', returnval)

    @mock.patch('workflow_ingestion.ingest_workflow.shutil.copy2')
    @mock.patch('workflow_ingestion.ingest_workflow.locate_handler')
    def test_handler_in_staging_dir_and_no_copy_called(self, mock_locator, mock_copy2):
        '''
        This tests the case where a gui element (e.g. a file chooser)
        which requires a handler module does NOT call any copy method
        if the module is already in the staging dir
        '''
        element={
            "target_ids": ["TestWorkflow.inputs"],
            "name": "input_files",
            "handler": "input_mapping.py"
		}
        staging_dir = '/some/staging_dir'
        module_path = os.path.join(staging_dir, 'input_mapping.py')
        mock_locator.return_value = module_path
        r = copy_handler_if_necessary(element, staging_dir, [])
        self.assertEqual(r, 'input_mapping.py')
        mock_copy2.assert_not_called()


    @mock.patch('workflow_ingestion.ingest_workflow.shutil.copy2')
    @mock.patch('workflow_ingestion.ingest_workflow.locate_handler')
    def test_copy_default_handler_called(self, mock_locator, mock_copy2):
        '''
        This tests the case where a gui element (e.g. a file chooser)
        that requires a handler module correctly copies
        '''
        element={
            "target_ids": ["TestWorkflow.inputs"],
            "name": "input_files",
            "handler": "input_mapping.py"
		}
        staging_dir = '/some/staging_dir'
        module_path = os.path.join('/some/other/dir', 'input_mapping.py')
        mock_locator.return_value = module_path
        r = copy_handler_if_necessary(element, staging_dir, [])
        self.assertEqual(r, 'input_mapping.py')
        mock_copy2.assert_called_once_with(module_path, staging_dir)


    def test_unknown_input_target_raises_exception_case1(self):
        '''
        This tests that the check_input_mapping function correctly raises
        an error if the gui spec gives an input "target" that is not in the WDL
        inputs.  Here we check if the gui spec was a dict (which is used when 
        the mapping of the GUI element to the WDL input is relatively complex)
        '''
        input_element = {}
        input_element[TARGET] = {
            TARGET_IDS: ['target1',],
            'name': 'dummy_name',
            'handler': 'something.py'
        }
        input_element[DISPLAY_ELEMENT]={}
        workflow_input_list = ['actual_target']
        with self.assertRaises(InvalidGuiMappingException):
            check_input_mapping(input_element, workflow_input_list)

    def test_unknown_input_target_raises_exception_case2(self):
        '''
        This tests that the check_input_mapping function correctly raises
        an error if the gui spec gives an input "target" that is not in the WDL
        inputs.  Here we check if the gui spec was a string, so it should directly
        map to the WDL input
        '''
        input_element = {}
        input_element[TARGET] = 'bad_target'
        input_element[DISPLAY_ELEMENT]={}
        workflow_input_list = ['actual_target']
        with self.assertRaises(InvalidGuiMappingException):
            check_input_mapping(input_element, workflow_input_list)

    def test_gui_spec_missing_name_attribute_raises_exception(self):
        '''
        The gui spec was more complex than a string, so it is a dict.
        The dict needs to have a `name` attribute so we know which WDL
        input to map it to.  Here, we test that an exception is raised
        if the GUI spec does NOT have a name attribute
        '''
        input_element = {}
        input_element[TARGET] = {
            TARGET_IDS: ['target1',],
            # this is missing --> 'name': 'dummy_name',
            'handler': 'something.py'
        }
        input_element[DISPLAY_ELEMENT] = {
            "type": "file_chooser", \
            "filter": ".*", \
            "label": "Input files:", \
            "choose_multiple": True, \
            "description": "Choose files to concatenate" \
		}	
        gui_schema = json.load(open(os.path.join(THIS_DIR, 'gui_schema.json')))
        element_schema = gui_schema['gui_elements']['file_chooser']
        with self.assertRaises(ConfigurationException):
            fill_html_and_js_template(input_element, element_schema, 'file_chooser', 0)

    @mock.patch('workflow_ingestion.ingest_workflow.locate_handler')
    def test_missing_handler_raises_exception_case1(self, mock_locator):
        '''
        If the GUI spec gives a handler that does not exist,
        ensure we raise an exception
        '''
        element={
            "target_ids": ["TestWorkflow.inputs"],
            "name": "input_files",
            "handler": "input_mapping.py"
		}
        staging_dir = '/some/staging_dir'
        module_path = os.path.join('/some/other/dir', 'input_mapping.py')
        mock_locator.return_value = None
        with self.assertRaises(MissingHandlerException):
            copy_handler_if_necessary(element, staging_dir, [])


    def test_unknown_gui_element_raises_exception(self):
        '''
        This tests the case that an exception is raised if the GUI spec given by the 
        developer does not match any of those in our GUI schema.
        '''
        display_element = {
            "type": "UNKNOWN", \
            "filter": ".*", \
            "label": "Input files:", \
            "choose_multiple": True, \
            "description": "Choose files to concatenate" \
		}	
        gui_schema = json.load(open(os.path.join(THIS_DIR, 'gui_schema.json')))
        gui_schema_element_names = gui_schema[GUI_ELEMENTS].keys()
        with self.assertRaises(UnknownGuiElementException):
            check_known_input_element(display_element, gui_schema_element_names)

    @mock.patch('workflow_ingestion.ingest_workflow.os.listdir', new=mock_listdir)
    @mock.patch('workflow_ingestion.ingest_workflow.import_module')
    def test_input_mapping_handler_missing_entry_method_raises_ex(self, mock_import_mod):
        '''
        The input mapping python code requires a function named
        `map_inputs` 

        Raise an exception if the method is missing
        '''
        mock_mod = mock.MagicMock()
        del mock_mod.myfunc
        mock_import_mod.return_value = mock_mod
        with self.assertRaises(HandlerConfigException):
            inspect_handler_module('/some/path/bar.py', 'myfunc', 1)


    @mock.patch('workflow_ingestion.ingest_workflow.os.listdir', new=mock_listdir)
    @mock.patch('workflow_ingestion.ingest_workflow.import_module')
    @mock.patch('workflow_ingestion.ingest_workflow.signature')
    def test_input_mapping_handler_incorrect_signature_raises_ex(self, \
        mock_signature,
        mock_import_mod
    ):
        '''
        The input mapping python code requires a function named
        `map_inputs` with 4 args:
        request.user, ALL unmapped_data, the 'reference' of the data from the input element, target[TARGET_IDS]

        Raise an exception if the method has the wrong signature.
        We obviously cannot do type checking, but at least we can 
        '''
        # mock that the found function takes two parameters
        mock_obj = mock.MagicMock(parameters=['a','b'])
        mock_signature.return_value = mock_obj

        mock_mod = mock.MagicMock()
        mock_import_mod.return_value = mock_mod

        # ensure we throw an exception if the number of expected args is
        # different (i.e. any number other than 2 below)
        with self.assertRaises(HandlerConfigException):
            inspect_handler_module('/some/path/bar.py', 'myfunc', 1)


    @mock.patch('workflow_ingestion.ingest_workflow.os.listdir', new=mock_listdir)
    @mock.patch('workflow_ingestion.ingest_workflow.import_module', side_effect=SyntaxError)
    def test_handler_syntax_error_raises_exception(self, mock_import_mod):
        '''
        The gui spec was more complex than a string, so it is a dict.
        The GUI spec needs to define a "handler" which is some python
        code that maps the front-end payload to the format necessary
        for the WDL input.  Here we test that we raise an exception
        if the code for the handler has a syntax error (import fails)     
        '''
        with self.assertRaises(SyntaxError):
            inspect_handler_module('/some/path/bar.py', 'myfunc', 1)


    @mock.patch('workflow_ingestion.ingest_workflow.utils')
    def test_docker_tag_correctly_found(self, mock_utils):
        '''
        This tests that an exception is raised if there is no docker
        image with the tag
        '''
        mock_perform_query = mock.MagicMock()
        mock_utils.perform_get_query = mock_perform_query
        mock_perform_query.return_value = {
            'count':3,
            'next': None,
            'results':[
                {'name': 'v1.0'},
                {'name': 'v1.1'},
                {'name': 'v1.2'}
            ]
        }
        self.assertTrue(query_for_tag('url', 'v1.1'))

    @mock.patch('workflow_ingestion.ingest_workflow.utils')
    def test_docker_tag_correctly_found_case2(self, mock_utils):
        '''
        This tests that an exception is raised if there is no docker
        image with the tag
        '''
        mock_perform_query = mock.MagicMock()
        mock_utils.perform_get_query = mock_perform_query
        mock_perform_query.return_value = {
            'count':1,
            'next': None,
            'results':[
                {'name': 'v1.2'}
            ]
        }
        self.assertTrue(query_for_tag('url', 'v1.2'))

    @mock.patch('workflow_ingestion.ingest_workflow.utils')
    def test_reject_ingestion_if_no_docker_tag_case1(self, mock_utils):
        '''
        This tests that an exception is raised if there is no docker
        image with the tag
        '''
        mock_perform_query = mock.MagicMock()
        mock_utils.perform_get_query = mock_perform_query
        mock_perform_query.return_value = {
            'count':3,
            'next': None,
            'results':[
                {'name': 'v1.0'},
                {'name': 'v1.1'},
                {'name': 'v1.2'}
            ]
        }
        self.assertFalse(query_for_tag('url', 'v1.3'))


    def test_docker_image_without_tag_raises_exception(self):
        '''
        If the WDL runtime section has a declaration like:
          docker: "docker.io/someUser/someImage"
          then it does not have a tag ("latest" if inferred)
        reject that since we wish to keep all the docker containers
        specifically versioned.
        '''
        with self.assertRaises(RuntimeDockerException):
            parse_docker_runtime_declaration('docker: "docker.io/someUser/foo"')


    def test_docker_image_with_latest_tag_raises_exception(self):
        '''
        If the WDL runtime section has a declaration like:
          docker: "docker.io/someUser/someImage"
          then it does not have a tag ("latest" if inferred)
        reject that since we wish to keep all the docker containers
        specifically versioned.
        '''
        with self.assertRaises(RuntimeDockerException):
            parse_docker_runtime_declaration('docker: "docker.io/someUser/foo:latest"')


    def test_missing_runtime_section_raises_exception(self):
        '''
        If one writes a task that does not have a runtime section an exception
        should be raised
        '''

        # Some mock WDL text.  Note that taskA is missing the runtime section
        wdl_text = '''
        workflow {
            File x
            call taskA {
                input:
                y=x
            }
            call task B {
                input:
                z=x
            }
        }
        task taskA{
            File y
            command {
                echo ${y}
            }
        }

        task taskB{
            File z
            command {
                echo ${z}
            }
            runtime {
                docker: "docker.io/userA/imgA:v1.0"
            }
        }
        '''
        with self.assertRaises(RuntimeDockerException):
            check_runtime(wdl_text)

    def test_missing_docker_spec_raises_exception(self):
        '''
        If the runtime section does not have a docker declaration, raise
        an exception
        '''

        # Some mock WDL text.  Note that taskA has a runtime, but is missing
        # the docker key-value:
        wdl_text = '''
        workflow {
            File x
            call taskA {
                input:
                y=x
            }
        }
        task taskA{
            File y
            command {
                echo ${y}
            }
            runtime {
               cpu: 8
               memory: "16G" 
            }
        }

        '''
        with self.assertRaises(RuntimeDockerException):
            check_runtime(wdl_text)


    def test_wdl_without_task_returns_empty_set(self):
        '''
        If the WDL file does not define any tasks (e.g. only workflow)
        then the check_runtime function should return an empty set
        '''

        # Some mock WDL text.  Note that taskA has a runtime, but is missing
        # the docker key-value:
        wdl_text = '''
        import "foo.wdl" as foo
        workflow {
            File x
            call foo.taskA {
                input:
                y=x
            }
        }
        '''
        result = check_runtime(wdl_text)
        self.assertTrue(len(result) == 0)


class TestWorkflowConstraints(TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        from analysis.models import Workflow
        self.test_workflow = Workflow.objects.create(
            git_url = 'https://github.com',
            git_commit_hash = 'abcd',
            workflow_name = 'some name',
            workflow_id = 1,
            version_id = 1
        )

    def tearDown(self):
        # Remove the directory after the test
        shutil.rmtree(self.test_dir)

    @mock.patch('workflow_ingestion.ingest_workflow.os')
    def test_missing_constraint_file_is_ok(self, mock_os):
        '''
        If there is no constraint file, that's fine.  No reason to require
        that a constraint be applied to a Worfklow

        Should just pass silently (e.g. no exceptions raised)
        '''
        mock_os.path.exists.return_value = False
        register_constraints(self.test_workflow, '/path/to/some_dir')

    def test_malformed_constraint_file(self):
        '''
        The constraint file (in json format) needs to be parsed as a dict
        by the native json module.  If it is anything else, then we know it's
        invalid
        '''
        # This *almost* has the correct format, but is list-based, so invalid
        some_list_json = [
            {'constraintA': {'type':'NumericConstraint', 'handler':'foo.py', 'description':'foo'}},
            {'constraintB': {'type':'NumericConstraint', 'handler':'foo.py', 'description':'foo'}}
        ]

        outfile_path = os.path.join(self.test_dir, CONSTRAINTS_JSON)
        with open(outfile_path, 'w') as fout:
            fout.write(json.dumps(some_list_json))

        with self.assertRaises(ConstraintFileFormatException):
            register_constraints(self.test_workflow, self.test_dir)

    def test_malformed_constraint_file_case2(self):
        '''
        The constraint file has a constraint "item" that is missing
        a required key ('handler' in this case)
        '''
        constraint_json = {
            'constraintA': {'type':'NumericConstraint', 'handler':'foo.py', 'description':'foo1'},
            'constraintB': {'type':'NumericConstraint', 'description':'foo2'},
        }

        outfile_path = os.path.join(self.test_dir, CONSTRAINTS_JSON)
        with open(outfile_path, 'w') as fout:
            fout.write(json.dumps(constraint_json))

        with self.assertRaises(ConstraintFileKeyException):
            register_constraints(self.test_workflow, self.test_dir)


    @mock.patch('workflow_ingestion.ingest_workflow.get_constraint_classnames')
    def test_malformed_constraint_file_case3(self, mock_constraint_class_func):
        '''
        The constraint file has a constraint "item" that specifies a constraint
        class that does not exist
        '''
        constraint_json = {
            'constraintA': {'type':'classA', 'handler':'foo.py', 'description':'foo1'},
            'constraintB': {'type':'UnknownClass', 'handler': 'foo.py', 'description':'foo2'},
        }

        outfile_path = os.path.join(self.test_dir, CONSTRAINTS_JSON)
        with open(outfile_path, 'w') as fout:
            fout.write(json.dumps(constraint_json))

        mock_constraint_class_func.return_value = ['classA', 'classB']

        with self.assertRaises(ConstraintFileClassnameException):
            register_constraints(self.test_workflow, self.test_dir)

    @mock.patch('workflow_ingestion.ingest_workflow.get_constraint_classnames')
    def test_constraint_handler_missing_file_raises_ex(self, mock_constraint_class_func):
        '''
        The constraint file has a constraint "item" that specifies a constraint
        class that does not exist
        '''
        constraint_json = {
            'constraintA': {'type':'classA', 'handler':'foo1.py', 'description':'foo1'},
            'constraintB': {'type':'classB', 'handler': 'foo2.py', 'description':'foo2'},
        }

        outfile_path = os.path.join(self.test_dir, CONSTRAINTS_JSON)
        with open(outfile_path, 'w') as fout:
            fout.write(json.dumps(constraint_json))

        mock_constraint_class_func.return_value = ['classA', 'classB']

        with self.assertRaises(HandlerConfigException):
            register_constraints(self.test_workflow, self.test_dir)

    @mock.patch('workflow_ingestion.ingest_workflow.get_constraint_classnames')
    def test_constraint_handler_no_func_raises_ex(self, mock_constraint_class_func):
        '''
        The constraint file references a python handler module that does not have
        a function with the correct name
        '''
        constraint_json = {
            'constraintA': {'type':'classA', 'handler':'foo1.py', 'description':'foo1'},
            'constraintB': {'type':'classB', 'handler': 'foo2.py', 'description':'foo2'},
        }

        outfile_path = os.path.join(self.test_dir, CONSTRAINTS_JSON)
        with open(outfile_path, 'w') as fout:
            fout.write(json.dumps(constraint_json))

        mock_constraint_class_func.return_value = ['classA', 'classB']

        # write a constraint file that does not have correct function name:
        file_contents = '''
        def some_func(x,y):
            pass
        '''
        with open(os.path.join(self.test_dir, 'foo1.py'), 'w') as fout:
            fout.write(file_contents)

        with self.assertRaises(HandlerConfigException):
            register_constraints(self.test_workflow, self.test_dir)

    @mock.patch('workflow_ingestion.ingest_workflow.get_constraint_classnames')
    def test_constraint_handler_bad_signature_raises_ex(self, mock_constraint_class_func):
        '''
        The constraint file references a python handler module that has the correct function
        name, but not the correct signature (2 args)
        '''
        constraint_json = {
            'constraintA': {'type':'classA', 'handler':'foo1.py', 'description':'foo1'},
            'constraintB': {'type':'classB', 'handler': 'foo2.py', 'description':'foo2'},
        }

        outfile_path = os.path.join(self.test_dir, CONSTRAINTS_JSON)
        with open(outfile_path, 'w') as fout:
            fout.write(json.dumps(constraint_json))

        mock_constraint_class_func.return_value = ['classA', 'classB']

        # write a constraint file that does not have correct function name:
        file_contents = '''
        def check_constraints(x):
            pass
        '''
        with open(os.path.join(self.test_dir, 'foo1.py'), 'w') as fout:
            fout.write(file_contents)

        with self.assertRaises(HandlerConfigException):
            register_constraints(self.test_workflow, self.test_dir)

    @mock.patch('workflow_ingestion.ingest_workflow.get_constraint_classnames')
    @mock.patch('workflow_ingestion.ingest_workflow.inspect_handler_module')
    def test_constraint_added_correctly(self, mock_inspect,  mock_constraint_class_func):
        '''
        Tests that a WorkflowConstraint object is properly added to the database
        '''
        constraint_json = {
            'constraintA': {'type':'classA', 'handler':'foo1.py', 'description':'foo1'}
        }

        outfile_path = os.path.join(self.test_dir, CONSTRAINTS_JSON)
        with open(outfile_path, 'w') as fout:
            fout.write(json.dumps(constraint_json))

        mock_constraint_class_func.return_value = ['classA', 'classB']
        mock_inspect.return_value = None

        # write a constraint file that does not have correct function name:
        file_contents = '''
        def check_constraints(x, y):
            pass
        '''
        with open(os.path.join(self.test_dir, 'foo1.py'), 'w') as fout:
            fout.write(file_contents)

        # prior to calling function, check that there are no database entries
        from analysis.models import WorkflowConstraint
        w = WorkflowConstraint.objects.all()
        self.assertEqual(len(w), 0)

        register_constraints(self.test_workflow, self.test_dir)

        w = WorkflowConstraint.objects.all()
        self.assertEqual(len(w), 1)
        w = w[0]
        self.assertTrue(w.implementation_class == 'classA')



        




