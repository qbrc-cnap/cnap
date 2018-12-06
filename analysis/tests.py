import os
import shutil

from django.test import TestCase

from analysis.models import Workflow

THIS_DIR = os.path.realpath(os.path.abspath(os.path.dirname(__file__)))
TEST_UTILS_DIR = os.path.join(THIS_DIR, 'test_utils')

class ViewUtilsTest(TestCase):
    '''
    This test class covers the "background" parts 
    of the view.  It is assumed that the Workflow has
    already been imported and is live (e.g. users can access)
    the workflow url
    '''

    def setUp(self):

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

        # create a workflow where the dir is missing the WDL input template
        w4_dir = os.path.join(TEST_UTILS_DIR, 'invalid_workflow3')
        w4 = Workflow.objects.create(
            workflow_id = 4,
            version_id = 1,
            workflow_name = 'invalidWorkflow3',
            is_default=True,
            is_active=True,
            workflow_location=w4_dir
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
        # that lacks the proper method
        w7_dir = os.path.join(TEST_UTILS_DIR, 'invalid_workflow6')
        w7 = Workflow.objects.create(
            workflow_id = 7,
            version_id = 1,
            workflow_name = 'invalidWorkflow6',
            is_default=True,
            is_active=True,
            workflow_location=w7_dir
        )

        # create a workflow where the gui specifies a handler module
        # that has the correct method name but wrong signature
        w9_dir = os.path.join(TEST_UTILS_DIR, 'invalid_workflow7')
        w9 = Workflow.objects.create(
            workflow_id = 9,
            version_id = 1,
            workflow_name = 'invalidWorkflow7',
            is_default=True,
            is_active=True,
            workflow_location=w9_dir
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
            is_default=False,
            is_active=False,
            workflow_location=w8_dir
        )





    def test_missing_gui_spec_raises_exception(self):
        '''
        Test that a missing GUI spec json file in the workflow dir raises an
        exception
        '''
        

    def test_gui_element_handler_module_missing_proper_method_raises_ex(self):
        '''
        If a handler is defined in the GUI specification for this workflow
        it needs to have a `add_to_context` method.  If it does not, have it
        raise an exception.

        The existence of this method should also be checked in the ingestion 
        of the workflow, so this is a double-check
        '''
        pass

    def test_nonexistent_workflow_id_raises_exception(self):
        '''
        If a non-existent workflow id is sent to the `get_workflow` method
        it raises an exception
        '''
        pass

    def test_multiple_workflows_with_same_id_raises_exception(self):
        '''
        Ensure that we cannot have multiple workflows with the same ID
        '''
        pass
    
    def test_inactive_workflow_request_from_regular_user_raises_exception(self):
        '''
        If the workflow is valid, but inactive, we do not let a 'regular' user
        instantiate a workflow.  
        '''
        pass

    def test_inactive_workflow_request_from_admin_user_succeeds(self):
        '''
        If the workflow is valid, but inactive, we let an admin user
        instantiate a workflow. 
        '''
        pass

    def test_corrupted_workflow_raises_exception_case1(self):
        '''
        Here, we test that an exception is raised if the GUI spec file
        (the one describing the UI for this workflow) is missing
        '''
        pass

    def test_corrupted_workflow_raises_exception_case2(self):
        '''
        Here, we test that an exception is raised if the WDL input
        file is missing
        '''
        pass

    def test_corrupted_workflow_raises_exception_case3(self):
        '''
        Here, we test that an exception is raised if the HTML
        template is missing
        '''
        pass

    def test_corrupted_workflow_raises_exception_case4(self):
        '''
        Here, we test that an exception is raised if there are zero
        WDL files
        '''
        pass

    def test_corrupted_workflow_raises_exception_case5(self):
        '''
        Here, we test that an exception is raised if there are >1
        WDL files
        '''
        pass

    def test_fill_wdl_template_case1(self):
        '''
        Here, the data sent from the front-end does NOT contain a required
        input.  Should raise an exception
        '''
        pass

    def test_fill_wdl_template_case2(self):
        '''
        Here, the data sent from the front-end does is not necessary as an
        input to the WDL input.  Should raise an exception
        '''
        pass

    def test_fill_wdl_template_case3(self):
        '''
        The gui spec was more complex than a string, so it is a dict.
        The dict needs to have a `name` attribute so we know which WDL
        input to map it to.  Here, we test that an exception is raised
        if the GUI spec does NOT have a name attribute
        '''
        pass

    def test_fill_wdl_template_case4(self):
        '''
        The gui spec was more complex than a string, so it is a dict.
        The dict needs to have a `name` attribute so we know which WDL
        input to map it to.  Here, we test that an exception is raised
        if the front-end did not send data for this input
        '''
        pass

    def test_fill_wdl_template_case5(self):
        '''
        The gui spec was more complex than a string, so it is a dict.
        The GUI spec needs to define a "handler" which is some python
        code that maps the front-end payload to the format necessary
        for the WDL input.  Here we test that we raise an exception
        if the code for the handler is missing
        '''
        pass

    def test_fill_wdl_template_case6(self):
        '''
        The gui spec was more complex than a string, so it is a dict.
        The GUI spec needs to define a "handler" which is some python
        code that maps the front-end payload to the format necessary
        for the WDL input.  Here we test that we raise an exception
        if the code for the handler has a syntax error (import fails)     
        '''
        pass

    def test_fill_wdl_template_case7(self):
        '''
        The gui spec was more complex than a string, so it is a dict.
        Here, the handler code will return a dictionary which is supposed
        to directly map to the WDL inputs.  Here we test that an exception
        is raised if one of those inputs is NOT in fact a WDL input
        '''
        pass

    def test_fill_wdl_template_case8(self):
        '''
        The gui spec was more complex than a string, so it is a dict.
        Here, the handler code will return a dictionary which is supposed
        to directly map to the WDL inputs.  Here we test that an exception
        is raised if the handler fails while parsing/manipulating that
        payload from the front-end (the handler is syntactically valid, however)
        '''
        pass

    def test_fill_wdl_template_case9(self):
        '''
        The gui spec was more complex than a string, so it is a dict.
        Here, the handler code will return a dictionary which is supposed
        to directly map to the WDL inputs.  Here we test that an exception
        is raised if the set of required keys for the WDL input is not
        completely satisfied.
        This can be due to either an incomplete payload from the frontend,
        or the GUI spec does not correctly specify the proper mapping 
        '''
        pass

    def test_fill_wdl_template_case10(self):
        '''
        The gui spec was more complex than a string, so it is a dict.
        The GUI spec needs to define a "handler" which is some python
        code that maps the front-end payload to the format necessary
        for the WDL input.  Here we test that we raise an exception
        if the handler module does not have a function with the 
        correct name (import succeeds, but runtime call fails 
        with method not found)     
        '''
        pass

    def test_fill_wdl_template_case11(self):
        '''
        The gui spec was more complex than a string, so it is a dict.
        The GUI spec needs to define a "handler" which is some python
        code that maps the front-end payload to the format necessary
        for the WDL input.  Here we test that we raise an exception
        if the code for the handler has the wrong function signature syntax error
        (import succeeds, but call fails)
        '''
        pass
