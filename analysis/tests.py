from django.test import TestCase
import tempfile

class ViewUtilsTest(unittest.TestCase):
    '''
    This test class covers the "background" parts 
    of the view.  It is assumed that the Workflow has
    already been imported and is live (e.g. users can access)
    the workflow url
    '''
    def test_missing_gui_spec_raises_exception(self):
        pass

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

