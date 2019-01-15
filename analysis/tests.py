import os
import sys
import shutil
from importlib import invalidate_caches


from django.test import TestCase
import unittest.mock as mock

from django.contrib.auth import get_user_model

from analysis.models import Workflow
from base.models import Resource

THIS_DIR = os.path.realpath(os.path.abspath(os.path.dirname(__file__)))
TEST_UTILS_DIR = os.path.join(THIS_DIR, 'test_utils')

from .view_utils import query_workflow, \
    validate_workflow_dir, \
    fill_context, \
    WORKFLOW_ID, \
    VERSION_ID, \
    MissingGuiSpecException, \
    WdlCountException, \
    MissingHtmlTemplateException, \
    NonexistentWorkflowException, \
    InactiveWorkflowException

from .tasks import fill_wdl_input, \
    MissingDataException, \
    InputMappingException, \
    WORKFLOW_LOCATION, \
    USER_PK


class ViewUtilsTest(TestCase):
    '''
    This test class covers the "background" parts 
    of the view.  It is assumed that the Workflow has
    already been imported and is live (e.g. users can access)
    the workflow url
    '''

    def setUp(self):

        self.admin_user = get_user_model().objects.create_user(email='admin@admin.com', password='abcd123!', is_staff=True)
        self.regular_user = get_user_model().objects.create_user(email='reguser@gmail.com', password='abcd123!')

        # create a couple of resources owned by the regular user:
        self.r1 = Resource.objects.create(
            source='google_storage',
            path='gs://a/b/reg_owned1.txt',
            size=2e9,
            owner=self.regular_user,
        )
        self.r2 = Resource.objects.create(
            source='google_storage',
            path='gs://a/b/reg_owned2.txt',
            size=2.1e9,
            owner=self.regular_user,
        )

        # create a valid workflow
        w1_dir = os.path.join(TEST_UTILS_DIR, 'valid_workflow')
        w1 = Workflow.objects.create(
            workflow_id = 1,
            version_id = 1,
            workflow_name = 'validWorkflow',
            is_default=True,
            is_active=True,
            workflow_location=w1_dir
        )

        # create a workflow where the dir is missing the gui spec
        w2_dir = os.path.join(TEST_UTILS_DIR, 'invalid_workflow1')
        w2 = Workflow.objects.create(
            workflow_id = 2,
            version_id = 1,
            workflow_name = 'invalidWorkflow1',
            is_default=True,
            is_active=True,
            workflow_location=w2_dir
        )

        # create a workflow where the dir is missing the html template
        w3_dir = os.path.join(TEST_UTILS_DIR, 'invalid_workflow2')
        w3 = Workflow.objects.create(
            workflow_id = 3,
            version_id = 1,
            workflow_name = 'invalidWorkflow2',
            is_default=True,
            is_active=True,
            workflow_location=w3_dir
        )

        # create a workflow where the dir is missing the WDL file
        w5_dir = os.path.join(TEST_UTILS_DIR, 'invalid_workflow4')
        w5 = Workflow.objects.create(
            workflow_id = 5,
            version_id = 1,
            workflow_name = 'invalidWorkflow4',
            is_default=True,
            is_active=True,
            workflow_location=w5_dir
        )

        # create a workflow where the dir has multiple WDL files
        w6_dir = os.path.join(TEST_UTILS_DIR, 'invalid_workflow5')
        w6 = Workflow.objects.create(
            workflow_id = 6,
            version_id = 1,
            workflow_name = 'invalidWorkflow5',
            is_default=True,
            is_active=True,
            workflow_location=w6_dir
        )

        # create a workflow where the gui specifies a handler module
        # that technically works, but does NOT return the correct 
        # dictionary, and thus there are EXTRA parameters that the WDL
        # input does NOT require
        w10_dir = os.path.join(TEST_UTILS_DIR, 'invalid_workflow8')
        w10 = Workflow.objects.create(
            workflow_id = 10,
            version_id = 1,
            workflow_name = 'invalidWorkflow8',
            is_default=True,
            is_active=True,
            workflow_location=w10_dir
        )

        # create a workflow where the inpput mapping function generates
        # some exception
        w14_dir = os.path.join(TEST_UTILS_DIR, 'invalid_workflow10')
        w14 = Workflow.objects.create(
            workflow_id = 14,
            version_id = 1,
            workflow_name = 'invalidWorkflow',
            is_default=True,
            is_active=True,
            workflow_location=w14_dir
        )

        # create a workflow where the gui specifies a handler module
        # that technically works, but does NOT return the correct 
        # dictionary, and thus there are missing parameters that the WDL
        # input requires
        w11_dir = os.path.join(TEST_UTILS_DIR, 'invalid_workflow9')
        w11 = Workflow.objects.create(
            workflow_id = 11,
            version_id = 1,
            workflow_name = 'invalidWorkflow9',
            is_default=True,
            is_active=True,
            workflow_location=w11_dir
        )

       # create a workflow that is valid but inactive
        w8_dir = os.path.join(TEST_UTILS_DIR, 'inactive_workflow')
        w8 = Workflow.objects.create(
            workflow_id = 8,
            version_id = 1,
            workflow_name = 'inactiveWorkflow',
            is_default=True,
            is_active=False,
            workflow_location=w8_dir
        )

        # The next two workflows are two different versions of valid workflows
        # however, neither of them have had their 'is_default' field set to True.
        w12 = Workflow.objects.create(
            workflow_id = 12,
            version_id = 1,
            workflow_name = 'validWorkflow',
            is_default=False,
            is_active=True,
            workflow_location=w1_dir
        )

        w13 = Workflow.objects.create(
            workflow_id = 12,
            version_id = 2,
            workflow_name = 'validWorkflow',
            is_default=False,
            is_active=True,
            workflow_location=w1_dir
        )

    def tearDown(self):
        pass

        
    def test_fill_wdl_template_case7(self):
        '''
        The gui spec was more complex than a string, so it is a dict.
        Here, the handler code will return a dictionary which is supposed
        to directly map to the WDL inputs.  Here we test that an exception
        is raised if one of those inputs is NOT in fact a WDL input

        Note that this is not an error that would be difficult to pickup
        with the tests in the workflow ingestion module.  Here, we do make
        the call to the actual 'handler' method, but it is a 'mock' in the sense
        that it adds an additional garbage parameter.
        '''
        mock_request = mock.MagicMock(user=self.regular_user)

        # create a correct dict and assert that's ok:
        r1_pk = self.r1.pk
        r2_pk = self.r2.pk
        workflow = Workflow.objects.get(workflow_id=10, version_id=1)
        payload = {}
        payload[WORKFLOW_LOCATION] = workflow.workflow_location
        payload[USER_PK] = self.regular_user.pk
        payload['input_files'] = [r1_pk, r2_pk]
        payload['TestWorkflow.outputFilename'] = 'output.txt'
        expected_dict = {}
        expected_dict['TestWorkflow.outputFilename'] = 'output.txt'
        expected_dict['TestWorkflow.inputs'] = [self.r1.path, self.r2.path]
        with self.assertRaises(InputMappingException):
            fill_wdl_input(payload)


    def test_gui_element_handler_module_missing_proper_method_raises_ex(self):
        '''
        If a handler is defined in the GUI specification for this workflow
        it needs to have a `add_to_context` method.  If it does not, have it
        raise an exception.

        The existence of this method should also be checked in the ingestion 
        of the workflow, so this is a double-check
        '''
        workflow_obj = Workflow.objects.get(workflow_id=2, version_id=1)
        with self.assertRaises(MissingGuiSpecException):
            validate_workflow_dir(workflow_obj)

    def test_nonexistent_workflow_id_raises_exception(self):
        '''
        If a non-existent workflow id is sent to the `query_workflow` method
        it raises an exception
        '''
        all_workflows = Workflow.objects.all()
        max_id  = max([x.workflow_id for x in all_workflows])
        bad_id = max_id + 1
        with self.assertRaises(NonexistentWorkflowException):
            query_workflow(bad_id)


    def test_no_default_workflow_raises_exception(self):
        '''
        If we query a workflow id (which is valid), but there are no workflows with their
        is_default field set, raise exception
        '''
        with self.assertRaises(NonexistentWorkflowException):
            query_workflow(13)
    

    def test_inactive_workflow_request_from_regular_user_raises_exception(self):
        '''
        If the workflow is valid, but inactive, we do not let a 'regular' user
        instantiate a workflow.  
        '''
        with self.assertRaises(InactiveWorkflowException):
            query_workflow(8, admin_request=False)

    def test_inactive_workflow_request_from_admin_user_succeeds(self):
        '''
        If the workflow is valid, but inactive, we let an admin user
        instantiate a workflow. 
        '''
        workflow = query_workflow(8, admin_request=True)
        self.assertTrue(workflow.workflow_id==8)


    def test_corrupted_workflow_raises_exception_case1(self):
        '''
        Here, we test that an exception is raised if the GUI spec file
        (the one describing the UI for this workflow) is missing
        '''
        workflow_obj = Workflow.objects.get(workflow_id=2, version_id=1)
        with self.assertRaises(MissingGuiSpecException):
            validate_workflow_dir(workflow_obj)

    def test_corrupted_workflow_raises_exception_case2(self):
        '''
        Here, we test that an exception is raised if the WDL input
        file is missing
        '''
        workflow_obj = Workflow.objects.get(workflow_id=5, version_id=1)
        with self.assertRaises(WdlCountException):
            validate_workflow_dir(workflow_obj)

    def test_corrupted_workflow_raises_exception_case3(self):
        '''
        Here, we test that an exception is raised if the HTML
        template is missing
        '''
        workflow_obj = Workflow.objects.get(workflow_id=3, version_id=1)
        with self.assertRaises(MissingHtmlTemplateException):
            validate_workflow_dir(workflow_obj)

    def test_corrupted_workflow_raises_exception_case4(self):
        '''
        Here, we test that an exception is raised if there are zero
        WDL files
        '''
        workflow_obj = Workflow.objects.get(workflow_id=5, version_id=1)
        with self.assertRaises(WdlCountException):
            validate_workflow_dir(workflow_obj)

    def test_corrupted_workflow_raises_exception_case5(self):
        '''
        Here, we test that an exception is raised if there are >1
        WDL files
        '''
        workflow_obj = Workflow.objects.get(workflow_id=6, version_id=1)
        with self.assertRaises(WdlCountException):
            validate_workflow_dir(workflow_obj)

    def test_valid_case_works(self):
        '''
        Here, the data sent from the front-end is OK. 
        '''
        mock_request = mock.MagicMock(user=self.regular_user)

        r1_pk = self.r1.pk
        r2_pk = self.r2.pk
        valid_workflow = Workflow.objects.get(workflow_id=1, version_id=1)
        payload = {}
        payload[USER_PK] = self.regular_user.pk
        payload[WORKFLOW_LOCATION] = valid_workflow.workflow_location
        payload['input_files'] = [r1_pk, r2_pk]
        payload['TestWorkflow.outputFilename'] = 'output.txt'
        expected_dict = {}
        expected_dict['TestWorkflow.outputFilename'] = 'output.txt'
        expected_dict['TestWorkflow.inputs'] = [self.r1.path, self.r2.path]
        returned_dict = fill_wdl_input(payload)
        self.assertEqual(returned_dict, expected_dict)


    def test_fill_wdl_template_case1(self):
        '''
        Here, the data sent from the front-end does NOT contain a required
        input.  Should raise an exception
        '''
        mock_request = mock.MagicMock(user=self.regular_user)

        # first send a bad payload-- 
        valid_workflow = Workflow.objects.get(workflow_id=1, version_id=1)
        payload = {}
        payload[USER_PK] = self.regular_user.pk
        payload[WORKFLOW_LOCATION] = valid_workflow.workflow_location
        with self.assertRaises(MissingDataException):
            fill_wdl_input(payload)

        # now try a payload where the primary keys are good, but missing the string param:
        r1_pk = self.r1.pk
        r2_pk = self.r2.pk
        payload = {}
        payload[USER_PK] = self.regular_user.pk
        payload[WORKFLOW_LOCATION] = valid_workflow.workflow_location
        payload['input_files'] = [r1_pk, r2_pk]
        with self.assertRaises(MissingDataException):
            fill_wdl_input(payload)

    def test_fill_wdl_template_case2(self):
        '''
        Here, the data sent from the front-end does is not necessary as an
        input to the WDL input.  Should just ignore it.  Receiving extra ddata
        from the front end is distinct from any custom mapping code that ends up
        providing an incorrect data object to the WDL input
        '''
        mock_request = mock.MagicMock(user=self.regular_user)

        # create a correct dict and assert that's ok:
        r1_pk = self.r1.pk
        r2_pk = self.r2.pk
        payload = {}
        valid_workflow = Workflow.objects.get(workflow_id=1, version_id=1)
        payload[USER_PK] = self.regular_user.pk
        payload[WORKFLOW_LOCATION] = valid_workflow.workflow_location
        payload['input_files'] = [r1_pk, r2_pk]
        payload['TestWorkflow.outputFilename'] = 'output.txt'
        expected_dict = {}
        expected_dict['TestWorkflow.outputFilename'] = 'output.txt'
        expected_dict['TestWorkflow.inputs'] = [self.r1.path, self.r2.path]
        returned_dict = fill_wdl_input(payload)
        self.assertEqual(returned_dict, expected_dict)

        # now add some garbage and try again.
        payload['garbage_key'] = 'foo'
        returned_dict = fill_wdl_input(payload)
        self.assertEqual(returned_dict, expected_dict)

    def test_fill_wdl_template_case8(self):
        '''
        The gui spec was more complex than a string, so it is a dict.
        Here, the handler code will return a dictionary which is supposed
        to directly map to the WDL inputs.  Here we test that an exception
        is raised if the handler fails while parsing/manipulating that
        payload from the front-end (the handler is syntactically valid, however)
        '''
        mock_request = mock.MagicMock(user=self.regular_user)

        # create a correct dict and assert that's ok:
        r1_pk = self.r1.pk
        r2_pk = self.r2.pk
        payload = {}
        payload[WORKFLOW_ID] = 14
        payload[VERSION_ID] = 1
        payload['input_files'] = [r1_pk, r2_pk]
        payload['TestWorkflow.outputFilename'] = 'output.txt'
        expected_dict = {}
        expected_dict['TestWorkflow.outputFilename'] = 'output.txt'
        expected_dict['TestWorkflow.inputs'] = [self.r1.path, self.r2.path]
        with self.assertRaises(Exception):
            fill_wdl_input(mock_request, payload)

    def test_fill_wdl_template_case9(self):
        '''
        The gui spec was more complex than a string, so it is a dict.
        Here, the handler code will return a dictionary which is supposed
        to directly map to the WDL inputs.  Here we test that an exception
        is raised if the set of required keys for the WDL input is not
        completely satisfied.

        Note that this is not necessarily due to either an incomplete payload from the frontend,
        or the GUI spec not correctly specify the proper mapping.  Rather, it reflects potential
        errors during runtime that result in the handler code not returning the dictionary
        it expects. 
        '''
        mock_request = mock.MagicMock(user=self.regular_user)

        # create a correct dict and assert that's ok:
        r1_pk = self.r1.pk
        r2_pk = self.r2.pk
        workflow = Workflow.objects.get(workflow_id=11, version_id=1)
        payload = {}
        payload[WORKFLOW_LOCATION] = workflow.workflow_location
        payload[USER_PK] = self.regular_user.pk
        payload['input_files'] = [r1_pk, r2_pk]
        payload['TestWorkflow.outputFilename'] = 'output.txt'
        expected_dict = {}
        expected_dict['TestWorkflow.outputFilename'] = 'output.txt'
        expected_dict['TestWorkflow.inputs'] = [self.r1.path, self.r2.path]
        with self.assertRaises(InputMappingException):
            fill_wdl_input(payload)
