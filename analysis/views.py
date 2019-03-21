import os
import json

from django.conf import settings
from django.shortcuts import render
from django.shortcuts import redirect
from django.http import HttpResponseBadRequest, JsonResponse
from django.views import View
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.urls import reverse
from django.http import Http404
from django.core.exceptions import ObjectDoesNotExist


from rest_framework import generics, permissions, status
from django_filters.rest_framework import DjangoFilterBackend

from helpers.email_utils import notify_admins
from .models import Workflow, \
    AnalysisProject, \
    OrganizationWorkflow, \
    PendingWorkflow, \
    AnalysisProjectResource, \
    JobClientError
from base.models import Issue
from .serializers import WorkflowSerializer, \
    AnalysisProjectSerializer, \
    OrganizationWorkflowSerializer, \
    PendingWorkflowSerializer, \
    AnalysisProjectResourceSerializer
from .view_utils import query_workflow, \
    validate_workflow_dir, \
    fill_context, \
    start_job_on_gcp


class AnalysisQueryException(Exception):
    pass


class OrganizationWorkflowList(generics.ListCreateAPIView):
    queryset = OrganizationWorkflow.objects.all()
    serializer_class = OrganizationWorkflowSerializer
    permission_classes = (permissions.IsAdminUser,)


class OrganizationWorkflowDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = OrganizationWorkflow.objects.all()
    serializer_class = OrganizationWorkflowSerializer
    permission_classes = (permissions.IsAdminUser,)


class AnalysisProjectResourceListCreate(generics.ListCreateAPIView):
    serializer_class = AnalysisProjectResourceSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        queryset = AnalysisProjectResource.objects.all()
        if not self.request.user.is_staff: # a regular user- only give their own resources
            queryset = AnalysisProjectResource.objects.filter(resource__owner=self.request.user)
        return queryset


class WorkflowList(generics.ListAPIView):
    '''
    This lists the available Workflow instances avaiable.  Only available to admins
    '''
    serializer_class = WorkflowSerializer
    permission_classes = (permissions.IsAdminUser,)
    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('is_active', 'is_default')

    def get_queryset(self):
        return Workflow.objects.all()


class WorkflowDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Workflow.objects.all()
    serializer_class = WorkflowSerializer
    permission_classes = (permissions.IsAdminUser,)
    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('is_active', 'is_default')


class PendingWorkflowList(generics.ListAPIView):
    '''
    This lists the PendingWorkflow instances.  Only available to admins
    '''
    serializer_class = PendingWorkflowSerializer
    permission_classes = (permissions.IsAdminUser,)
    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('complete', 'error')

    def get_queryset(self):
        return PendingWorkflow.objects.all()


class PendingWorkflowDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = PendingWorkflow.objects.all()
    serializer_class = PendingWorkflowSerializer
    permission_classes = (permissions.IsAdminUser,)
    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('complete', 'error')


class AnalysisProjectListAndCreate(generics.ListCreateAPIView):
    '''
    This lists or creates instances of AnalysisProjects
    '''
    serializer_class = AnalysisProjectSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('started', 'completed')

    def get_queryset(self):
        user = self.request.user

        # if admin, return all projects.  Otherwise only
        # return those owned by the user
        if user.is_staff:
            return AnalysisProject.objects.all()
        else:
            return AnalysisProject.objects.filter(owner=user)


class AnalysisProjectDetail(generics.RetrieveUpdateDestroyAPIView):
    '''
    This gives access to individual AnalysisProject instances
    '''
    def get_queryset(self):
        user = self.request.user
        uuid = self.kwargs['analysis_uuid']

        try:
            project = AnalysisProject.objects.get(analysis_uuid=uuid)
            
            # check owner just to be sure:
            if project.owner != user:
                # don't acknowledge that an instance has actually been found
                # if a non-owner stumbles upon the correct UUID
                raise Http404

            # now have the proper AnalysisProject instance for this user:
            return project

        except ObjectDoesNotExist as ex:
            raise Http404


class AnalysisView(View):

    '''
    This class specifies the view for a Workflow.  

    Depending on which URL is requested, this view can do a couple of things:
    - if a UUID is given in the URL params, then we are working with an AnalysisProject
    instance and thus, a user is attempting to run a Workflow.

    - if the URL is instead given by one or two integers (and requested by an admin), then
    we are simply using the URL to examine the Workflow in question.  This way admins can make
    alterations to Workflows and see the same thing the end-user sees.
    '''

    # enforces that this view is protected by login:
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    @staticmethod
    def get_url_params(kwargs):
        '''
        The kwargs dict carries the URL parameters.
        Depending on the parameters supplied to the view, we
        can do various things.  

        If a UUID is given, then a particular AnalysisProject
        is being executed.  If an admin simply wants to view
        the interface, then they may request using the `workflow_id`
        with an optional `version_id`.
        
        If any parameters are missing, they are set to None as flags
        '''
        try:
            analysis_uuid = kwargs['analysis_uuid']
        except KeyError:
            analysis_uuid = None

        try:
            workflow_id = kwargs['workflow_id']
        except KeyError:
            workflow_id = None

        try:
            version_id = kwargs['version_id']
        except KeyError:
            version_id = None

        return (analysis_uuid, workflow_id, version_id)

    @staticmethod
    def get_workflow(kwargs, staff_request = False):
        '''
        This method handles the logic of returning a Workflow instance
        based on which parameters were given in the URL.

        Returns a tuple-
        - the first item of the tuple is a Workflow instance
        - the second item of the tuple is either a UUID or None.  It is None
        if a direct request for the workflow was issued by an admin. This helps
        determine if the request is a "mock" or "test" of the Workflow
        '''
        # Get the workflow and possibly version id from the request params:
        analysis_uuid, workflow_id, version_id = AnalysisView.get_url_params(kwargs)
        
        if analysis_uuid:
            # get the workflow object based on the UUID:
            analysis_project = AnalysisProject.objects.get(analysis_uuid=analysis_uuid)
            return (analysis_project.workflow, analysis_project)
        else:

            if staff_request:
                # get the workflow object based on the workflow ID/version
                try:
                    return (query_workflow(workflow_id, version_id, True), None)
                except Exception:
                    raise AnalysisQueryException('Error when querying for workflow.')
            else:
                raise AnalysisQueryException('Error when querying for workflow.'
                    ' Non-admins may not request a workflow directly.  An analysis'
                    ' project must be created first.'
                )

    def get(self, request, *args, **kwargs):
        '''
        When the url is requested using the GET method, we display the form.

        Depending on the implementation of the workflow, this could require 
        dynamic content to be loaded from the database.  Hence, we need to 
        look at the workflow details to determine if any such details are needed.
        '''

        try:
            workflow_obj, analysis_project = AnalysisView.get_workflow(kwargs, request.user.is_staff)
        except AnalysisQueryException as ex:
            message = str(ex)
            return HttpResponseBadRequest(message)

        # if a specific analysis was requested
        if analysis_project:
            if analysis_project.started:
                if not analysis_project.completed:
                    # in progress, return status page
                    context = {}
                    context['job_status'] = analysis_project.status
                    if analysis_project.start_time is not None:
                        context['start_time'] = analysis_project.start_time
                    else:
                        context['start_time'] = '-'
                    if analysis_project.error:
                        context['error'] = True
                    else:
                        context['error'] = False
                    return render(request, 'analysis/in_progress.html', context)
                else: # started AND complete
                    if not analysis_project.error:
                        # return a success page
                        context = {}
                        if analysis_project.finish_time is not None:
                            context['finish_time'] = analysis_project.finish_time
                        else:
                            context['finish_time'] = '-'
                        return render(request, 'analysis/complete_success.html', context)
                    elif analysis_project.error:
                        # return a page indicating error
                        if analysis_project.restart_allowed:
                            context = {}
                            client_errors = JobClientError.objects.filter(project=analysis_project)
                            context['status'] = analysis_project.status
                            context['errors'] = client_errors
                            context['restart_url'] = reverse('analysis-project-restart', args=[analysis_project.analysis_uuid,])
                            return render(request, 'analysis/recoverable_error.html', context)
                        else:
                            return render(request, 'analysis/complete_error.html',{})

        # if we are here, we have a workflow object from the database.
        # We can use that to find the appropriate workflow directory where
        # everything lives.
        workflow_dir = workflow_obj.workflow_location
        template = os.path.join(workflow_dir, settings.HTML_TEMPLATE_NAME)

        # prepare and empty context which we will fill-in
        context_dict = {}

        # now that we have a valid workflow directory,
        # we look at the GUI spec and load the 'handlers' for each input 
        # element.  These are snippets of python code that specify how
        # dynamic, database-driven data is queried for the UI.
        fill_context(request, workflow_obj, context_dict)

        # add the workflow title and description to the context
        context_dict['workflow_title'] = workflow_obj.workflow_title
        context_dict['workflow_long_description'] = workflow_obj.workflow_long_description

        # add some additional elements to the form:
        # Need to link the javascript for the page
        context_dict['form_javascript'] = os.path.join(settings.STATIC_URL, 
            workflow_dir, 
            settings.FORM_JAVASCRIPT_NAME)

        # Need to link the css for the page
        context_dict['form_css'] = os.path.join(settings.STATIC_URL, 
            workflow_dir, 
            settings.FORM_CSS_NAME)

        # the url so the POST goes to the correct URL
        if analysis_project:
            context_dict['submit_url'] = reverse('analysis-project-execute', 
                kwargs={
                    'analysis_uuid': analysis_project.analysis_uuid
                }
            )
        else:
            context_dict['submit_url'] = reverse('workflow_version_view', 
                kwargs={
                    'workflow_id': workflow_obj.workflow_id, 
                    'version_id': workflow_obj.version_id
                }
            )
        return render(request, template, context_dict)


    def post(self, request, *args, **kwargs):
        '''
        With a POST request, the form is being submitted.  We parse the contents
        of that request, prepare a pending analysis, and prepare a summary.
        '''

        try:
            workflow_obj, analysis_project = AnalysisView.get_workflow(kwargs, request.user.is_staff)
        except AnalysisQueryException as ex:
            message = str(ex)
            return HttpResponseBadRequest(message)

        if analysis_project is None:
            return JsonResponse({'message': 'No action taken since workflow was not assigned to a project.'})

        if analysis_project.started:
            return HttpResponseBadRequest('Analysis was already started/run.')

        # parse the payload from the POST request and make a dictionary
        data = request.POST.get('data')
        j = json.loads(data)
        j['analysis_uuid'] = analysis_project.analysis_uuid

        try:
            analysis_project.started = True
            analysis_project.status = 'Preparing workflow'
            analysis_project.save()
            start_job_on_gcp(request, j, workflow_obj)
            return JsonResponse({'message': '''
            Your analysis has been submitted.  You may return to this page to check on the status of the job.  
            If it has been enabled, an email will be sent upon completion'''})
        except Exception as ex:
            message = 'There was a problem instantiating an analysis.  Project was %s.\n' % str(analysis_project.analysis_uuid)
            message += 'Payload sent to backend was: %s' % json.dumps(j)
            subject = 'Error instantiating workflow'
            notify_admins(message, subject)

            issue = Issue(message=message)
            issue.save()

            return HttpResponseBadRequest('Error when instantiating workflow.')


class AnalysisRestartView(View):
    '''
    This is used when a recoverable error was encountered (e.g. bad inputs).  Allow a restart
    if possible.
    '''
    def get(self, request, *args, **kwargs):

        try:
            workflow_obj, analysis_project = AnalysisView.get_workflow(kwargs, request.user.is_staff)
        except AnalysisQueryException as ex:
            message = str(ex)
            return HttpResponseBadRequest(message)

        # check that it was completed and had an error:
        error = analysis_project.error
        completed = analysis_project.completed
        restart_allowed = analysis_project.restart_allowed

        if error and completed and restart_allowed:
            analysis_project.error = False
            analysis_project.completed = False
            analysis_project.started = False
            analysis_project.message = ''
            analysis_project.status ='' 
            analysis_project.save()
            return redirect('analysis-project-execute', analysis_uuid=analysis_project.analysis_uuid)
        else:
            return HttpResponseBadRequest('Cannot perform this action.')
            
