import os
import sys
import shutil
import uuid
import json
import datetime
from importlib import invalidate_caches


from django.test import TestCase
import unittest.mock as mock

from django.contrib.auth import get_user_model

from analysis.models import Workflow, \
    AnalysisProject, \
    SubmittedJob
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
    start_workflow, \
    check_job, \
    register_outputs, \
    parse_outputs, \
    MissingDataException, \
    InputMappingException, \
    WORKFLOW_LOCATION, \
    USER_PK

class TasksTestCase(TestCase):
    '''
    This test class covers some of the operations performed
    by the functions in the asynchronous tasks (celery) code.

    We are NOT testing the async nature-- only that the code does what is
    expected whenever it happens to be executed.
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

        # create a mock analysis project, tying it to
        # the valid workflow and the 'regular' user
        self.analysis_uuid = uuid.uuid4()
        project = AnalysisProject.objects.create(
            analysis_uuid = self.analysis_uuid,
            workflow = w1,
            owner = self.regular_user,
            start_time = datetime.datetime.now()
        )
        self.analysis_project = project

        # create a 'data' dict that we can use repeatedly:
        self.data = {
            'analysis_uuid': self.analysis_uuid,
            WORKFLOW_LOCATION: w1.workflow_location,
            USER_PK: self.regular_user.pk,
            'input_files': [self.r1.pk, self.r2.pk],
            'TestWorkflow.outputFilename': 'output.txt'
        }

    def tearDown(self):
        pass

    def _mock_response(self, status_code, status_str=None):
        '''
        helper function which constructs the mock return object 
        so there is less test code copied
        '''
        mock_return = mock.MagicMock()
        mock_return.status_code = status_code
        d = {'message': 'some msg'}
        if status_str:
            d['status'] = status_str
        mock_return.text = json.dumps(d)
        return mock_return

    def _create_submission(self):
        '''
        helper function for use when checking job status.  Creates a database
        object that is necessary to execute loop
        '''
        # create a job that we are pretending to query
        mock_uuid = 'e442e52a-9de1-47f0-8b4f-e6e565008cf1'
        job = SubmittedJob(project=self.analysis_project, job_id=mock_uuid, job_status='Submitted')
        job.save()
        return job

    @mock.patch('analysis.tasks.handle_exception')
    @mock.patch('analysis.tasks.requests')
    def test_inform_staff_if_cromwell_returns_error_case404(self, mock_requests, mock_handle_ex)
        '''
        This test covers the case when the job has finished.  After it has finished, 
        we check for outputs, which will be added to the downloads
        '''
        mock_requests.get.return_value = self._mock_response(404)
        job = self._create_submission()
        register_outputs(job)
        self.assertTrue(mock_handle_ex.called)

    @mock.patch('analysis.tasks.handle_exception')
    @mock.patch('analysis.tasks.requests')
    def test_inform_staff_if_cromwell_returns_error_case400(self, mock_requests, mock_handle_ex)
        '''
        This test covers the case when the job has finished.  After it has finished, 
        we check for outputs, which will be added to the downloads
        '''
        mock_requests.get.return_value = self._mock_response(400)
        job = self._create_submission()
        register_outputs(job)
        self.assertTrue(mock_handle_ex.called)

    @mock.patch('analysis.tasks.handle_exception')
    @mock.patch('analysis.tasks.requests')
    def test_inform_staff_if_cromwell_returns_error_case500(self, mock_requests, mock_handle_ex)
        '''
        This test covers the case when the job has finished.  After it has finished, 
        we check for outputs, which will be added to the downloads
        '''
        mock_requests.get.return_value = self._mock_response(500)
        job = self._create_submission()
        register_outputs(job)
        self.assertTrue(mock_handle_ex.called)

    @mock.patch('analysis.tasks.handle_exception')
    @mock.patch('analysis.tasks.requests')
    def test_inform_staff_if_cromwell_unreachable_during_output_registration(self, mock_requests, mock_handle_ex)
        '''
        This test covers the case when the job has finished.  After it has finished, 
        we check for outputs, which will be added to the downloads
        '''
        mock_requests.get.return_value = self._mock_response(404)
        job = self._create_submission()
        with self.assertRaises(Exception):
            register_outputs(job)
        self.assertTrue(mock_handle_ex.called)

    @mock.patch('analysis.tasks.parse_outputs')
    @mock.patch('analysis.tasks.get_resource_size')
    @mock.patch('analysis.tasks.handle_exception')
    @mock.patch('analysis.tasks.requests')
    def test_add_resources_after_job_completion(self, 
        mock_requests, 
        mock_handle_ex, 
        mock_resource_size,
        mock_output_parser
    )
        '''
        This test covers the case when the job has finished.  After it has finished, 
        we check for outputs, which will be added to the downloads
        '''
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        path = 'prefix://some-bucket/folder/foo.txt'
        # doesn't matter what this is since we mocked out the parse_outputs func
        mock_output = {'outputs': {'abc':'def'}}
        mock_response.text = json.dumps(mock_output)

        mock_job = mock.MagicMock()
        mock_job.project = self.analysis_project

        mock_output_parser.return_value = [path,]

        mock_resource_size.return_value = 2000

        mock_requests.get.return_value = mock_response
        
        register_outputs(job)
        expected_resource = Resource.objects.get(path=path, name='foo.txt')

    def test_output_parser_case1(self):
        '''
        If there is only a single output, returns a single element list
        '''
        d = {'workflow.some_output': 'prefix://some-bucket/folder/foo.txt'}
        expected_return = 'prefix://some-bucket/folder/foo.txt'
        return_val = parse_outputs(d)
        self.assertEqual(return_val, expected_return)

    def test_output_parser_case2(self):
        '''
        If there is a scatter within a subworkflow (final output
        if a Array[Array[File]]), you can get a series of nested lists
        That should be collapsed to a single list of files.
        '''
        d = {'workflow.some_output': [
            ['prefix://some-bucket/folder/foo1.txt', 'prefix://some-bucket/folder/foo2.txt'],
            ['prefix://some-bucket/folder/bar1.txt', 'prefix://some-bucket/folder/bar2.txt']
            ]
        }
        expected_return = ['prefix://some-bucket/folder/foo1.txt',
            'prefix://some-bucket/folder/foo2.txt',
            'prefix://some-bucket/folder/bar1.txt',
            'prefix://some-bucket/folder/bar2.txt'
        ]
        return_val = parse_outputs(d)
        self.assertEqual(return_val, expected_return)

    def test_output_parser_case3(self):
        '''
        If there are multiple outputs, returns a dictionary
        where each key is a single file
        '''
        d = {'workflow.some_output1': 'prefix://some-bucket/folder/foo.txt'}
            'workflow.some_output2': 'prefix://some-bucket/folder/bar.txt'}
        expected_return = ['prefix://some-bucket/folder/foo.txt', 
            'prefix://some-bucket/folder/bar.txt'
        ]
        return_val = parse_outputs(d)
        self.assertEqual(return_val, expected_return)

    def test_output_parser_case4(self):
        '''
        If there is one Array[File] output
        '''
        d = {'workflow.some_output1': ['prefix://some-bucket/folder/foo.txt'}
            'prefix://some-bucket/folder/bar.txt']}
        expected_return = ['prefix://some-bucket/folder/foo.txt', 
            'prefix://some-bucket/folder/bar.txt'
        ]
        return_val = parse_outputs(d)
        self.assertEqual(return_val, expected_return) 

    @mock.patch('analysis.tasks.handle_exception')
    @mock.patch('analysis.tasks.requests')
    def test_catch_ex_if_unreachable_cromwell_case1(self, mock_requests, mock_handle_ex):
        '''
        This covers where the requests.post function raises an exception
        '''
        myex = Exception('Some ex')
        mock_requests.post.side_effect = myex
        with self.assertRaises(Exception):
          start_workflow(self.data)
        self.assertTrue(mock_handle_ex.called)

    @mock.patch('analysis.tasks.handle_exception')
    @mock.patch('analysis.tasks.requests')
    def test_catch_ex_if_unreachable_cromwell_case2(self, mock_requests, mock_handle_ex):
        '''
        This covers where the requests.post receives a 500 from the cromwell server
        '''
        mock_requests.post.return_value = self._mock_response(500)
        start_workflow(self.data)
        self.assertTrue(mock_handle_ex.called)

    @mock.patch('analysis.tasks.handle_exception')
    @mock.patch('analysis.tasks.requests')
    def test_catch_ex_if_unreachable_cromwell_case3(self, mock_requests, mock_handle_ex):
        '''
        This covers where the requests.post receives a 400 from the cromwell server
        '''
        mock_requests.post.return_value = self._mock_response(400)
        start_workflow(self.data)
        self.assertTrue(mock_handle_ex.called)

    @mock.patch('analysis.tasks.handle_exception')
    @mock.patch('analysis.tasks.requests')
    def test_catch_ex_if_unreachable_cromwell_case4(self, mock_requests, mock_handle_ex):
        '''
        This covers where the requests.post receives a 404 from the cromwell server
        '''
        mock_requests.post.return_value = self._mock_response(404)
        start_workflow(self.data)
        self.assertTrue(mock_handle_ex.called)

    @mock.patch('analysis.tasks.handle_exception')
    @mock.patch('analysis.tasks.requests')
    def test_catch_ex_if_unreachable_cromwell_case5(self, mock_requests, mock_handle_ex):
        '''
        This covers where the requests.get receives a 404 from the cromwell server
        '''
        self._create_submission()
        mock_requests.get.return_value = self._mock_response(404)
        check_job()
        self.assertTrue(mock_handle_ex.called)

    @mock.patch('analysis.tasks.handle_exception')
    @mock.patch('analysis.tasks.requests')
    def test_catch_ex_if_unreachable_cromwell_case6(self, mock_requests, mock_handle_ex):
        '''
        This covers where the requests.get receives a 400 from the cromwell server
        '''
        self._create_submission()
        mock_requests.get.return_value = self._mock_response(400)
        check_job()
        self.assertTrue(mock_handle_ex.called)

    @mock.patch('analysis.tasks.handle_exception')
    @mock.patch('analysis.tasks.requests')
    def test_catch_ex_if_unreachable_cromwell_case7(self, mock_requests, mock_handle_ex):
        '''
        This covers where the requests.get receives a 500 from the cromwell server
        '''
        self._create_submission()
        mock_requests.get.return_value = self._mock_response(500)
        check_job()
        self.assertTrue(mock_handle_ex.called)

    @mock.patch('analysis.tasks.requests')
    def test_still_running_job_updates_status(self, mock_requests):
        '''
        This covers the case where we check on a job that is still running.  Ensure
        that the status is reset appropriately
        '''
        project_pk = self.analysis_project.pk
        project = AnalysisProject.objects.get(pk=project_pk)
        self.assertFalse(project.completed)

        job = self._create_submission()
        job_uuid = job.job_id
        self.assertTrue(job.job_status == 'Submitted')
        mock_requests.get.return_value = self._mock_response(200, status_str='Running')
        check_job()

        # query the database for updated object:
        job = SubmittedJob.objects.get(job_id=job_uuid)
        self.assertTrue(job.job_status == 'Running')
        project = job.project
        self.assertFalse(project.completed)


    @mock.patch('analysis.tasks.handle_exception')
    @mock.patch('analysis.tasks.requests')
    def test_unexpected_but_successful_response(self, mock_requests, mock_handle_ex):
        '''
        This covers the case where we check on a job that returns 200, but the
        status is unrecognized.  We then set the status, and inform staff
        '''
        project_pk = self.analysis_project.pk
        project = AnalysisProject.objects.get(pk=project_pk)
        self.assertFalse(project.completed)

        self._create_submission()
        mock_requests.get.return_value = self._mock_response(200, status_str='Something')
        check_job()

        # check that the success method was called:
        self.assertTrue(mock_handle_ex.called)

        # ensure the SubmittedJob item was cleaned up
        all_jobs = SubmittedJob.objects.all()
        self.assertTrue(len(all_jobs) == 1)

    @mock.patch('analysis.tasks.send_email')
    @mock.patch('analysis.tasks.requests')
    def test_successful_job_triggers_downstream_actions(self, mock_requests, mock_email_send):
        '''
        This covers the case where we check on a job that is successful.  Ensure
        the follow-up actions are followed
        '''
        project_pk = self.analysis_project.pk
        project = AnalysisProject.objects.get(pk=project_pk)
        self.assertFalse(project.completed)

        self._create_submission()
        mock_requests.get.return_value = self._mock_response(200, status_str='Succeeded')
        check_job()

        # check that the success method was called:
        self.assertTrue(mock_email_send.called)
        project = AnalysisProject.objects.get(pk=project_pk)
        self.assertTrue(project.completed)
        self.assertTrue(project.success)
        self.assertFalse(project.error)

        # ensure the SubmittedJob item was cleaned up
        all_jobs = SubmittedJob.objects.all()
        self.assertTrue(len(all_jobs) == 0)

    @mock.patch('analysis.tasks.notify_admins')
    @mock.patch('analysis.tasks.requests')
    def test_failed_job_triggers_downstream_actions(self, mock_requests, mock_admin_email):
        '''
        This covers the case where we check on a job that has failed.  Ensure
        the follow-up actions are followed
        '''
        project_pk = self.analysis_project.pk
        project = AnalysisProject.objects.get(pk=project_pk)

        self._create_submission()
        mock_requests.get.return_value = self._mock_response(200, status_str='Failed')
        check_job()

        # check that the success method was called:
        self.assertTrue(mock_admin_email.called)
        project = AnalysisProject.objects.get(pk=project_pk)
        self.assertTrue(project.completed)
        self.assertFalse(project.success)
        self.assertTrue(project.error)

        # ensure the SubmittedJob item was cleaned up
        all_jobs = SubmittedJob.objects.all()
        self.assertTrue(len(all_jobs) == 0)

    @mock.patch('analysis.tasks.requests')
    def test_successful_submission_creates_database_objects(self, mock_requests):
        '''
        This covers a case where the Cromwell server responds to a workflow status query with 201,
        and we see that all the database changes were made
        '''

        mock_uuid = 'e442e52a-9de1-47f0-8b4f-e6e565008cf1'
        mock_return = mock.MagicMock()
        mock_return.status_code = 201
        mock_return.text = json.dumps({'id': mock_uuid,
            'status': 'Submitted'
        })
        mock_requests.post.return_value = mock_return

        # before doing anything, check the status of the projects:
        project = AnalysisProject.objects.get(analysis_uuid=self.analysis_uuid)
        self.assertFalse(project.started)

        # "start" it...
        start_workflow(self.data)

        # ensure that the proper objects were created in the db:
        submitted_job = SubmittedJob.objects.get(job_id=mock_uuid)
        self.assertTrue(submitted_job.project.analysis_uuid == self.data['analysis_uuid'])

        # check that the project was marked as stated in the db
        project = AnalysisProject.objects.get(analysis_uuid=self.analysis_uuid)
        self.assertTrue(project.started)


    @mock.patch('analysis.tasks.handle_exception')
    @mock.patch('analysis.tasks.requests')
    def test_unknown_response_generates_notification(self, mock_requests, mock_handle_ex):
        '''
        This covers a case where the Cromwell server responds to a workflow submission with 201,
        but has an unexpected status payload
        '''
        mock_uuid = 'e442e52a-9de1-47f0-8b4f-e6e565008cf1'
        mock_return = mock.MagicMock()
        mock_return.status_code = 201
        mock_return.text = json.dumps({'id': mock_uuid,
            'status': 'Something unexpected...'
        })
        mock_requests.post.return_value = mock_return

        # "start" it...
        start_workflow(self.data)

        # check that everything was unchanged:
        self.assertTrue(mock_handle_ex.called) # notification was sent
        project = AnalysisProject.objects.get(analysis_uuid=self.analysis_uuid)
        self.assertFalse(project.started)
        self.assertEqual(len(SubmittedJob.objects.all()), 0)

    @mock.patch('analysis.tasks.handle_exception')
    @mock.patch('analysis.tasks.requests')
    def test_unknown_response_generates_notification_case2(self, mock_requests, mock_handle_ex):
        '''
        This covers a case where the Cromwell server responds to a workflow status query with 200,
        but has an unexpected status payload
        '''
        # create a SubmittedJob to start
        mock_uuid = 'e442e52a-9de1-47f0-8b4f-e6e565008cf1'
        job = SubmittedJob(project=self.analysis_project, job_id=mock_uuid, job_status='Submitted')
        job.save()

        mock_return = mock.MagicMock()
        mock_return.status_code = 200
        mock_return.text = json.dumps({'status': 'Something unexpected...'})
        mock_requests.get.return_value = mock_return

        # now mock a query that returns something we do not expect:
        check_job()
        self.assertTrue(mock_handle_ex.called) # notification was sent


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
