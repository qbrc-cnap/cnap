import os
import json

from django.conf import settings
from django.shortcuts import render
from django.shortcuts import redirect
from django.http import HttpResponseBadRequest, JsonResponse, HttpResponseForbidden, HttpResponse
from django.views import View
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.urls import reverse
from django.http import Http404
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth import get_user_model
from django.forms import modelform_factory
from django.contrib.sites.models import Site
from django.utils.datastructures import MultiValueDictKeyError

from rest_framework import generics, permissions, status
from django_filters.rest_framework import DjangoFilterBackend

from helpers.email_utils import notify_admins
import analysis.models
from analysis.models import Workflow, \
    AnalysisProject, \
    OrganizationWorkflow, \
    PendingWorkflow, \
    AnalysisProjectResource, \
    JobClientError, \
    WorkflowConstraint, \
    ProjectConstraint, \
    ImplementedConstraint
from base.models import Issue
from .serializers import WorkflowSerializer, \
    AnalysisProjectSerializer, \
    OrganizationWorkflowSerializer, \
    PendingWorkflowSerializer, \
    AnalysisProjectResourceSerializer, \
    WorkflowConstraintSerializer
from .view_utils import query_workflow, \
    validate_workflow_dir, \
    fill_context, \
    start_job_on_gcp
from helpers.email_utils import send_email
from helpers.utils import get_jinja_template

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


class AnalysisProjectList(generics.ListAPIView):
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


class WorkflowConstraintList(generics.ListAPIView):
    '''
    This lists the available WorkflowConstraint instances avaiable.  Only available to admins
    '''
    serializer_class = WorkflowConstraintSerializer
    permission_classes = (permissions.IsAdminUser,)

    def get_queryset(self):
        return WorkflowConstraint.objects.all()


class WorkflowConstraintRetrieveUpdateDestroy(generics.RetrieveUpdateDestroyAPIView):
    '''
    This gives details about a particular WorkflowConstraint.  Only available to admins
    '''
    serializer_class = WorkflowConstraintSerializer
    permission_classes = (permissions.IsAdminUser,)


class AnalysisProjectCreateView(View):
    '''
    This handles creation of projects *outside* of the django admin, and gives admins
    the ability to create a project and apply constraints in one place.  For instance, if 
    a project is created in the standard Django admin page, the admin will have to explicitly
    navigate to the admin page for constraints to add constraints to the newly created project
    Here, we guide that process so it's not as clunky. 
    '''

    def get(self, request, *args, **kwargs):
        if request.user.is_staff:
            all_users = get_user_model().objects.all()
            all_workflows = Workflow.objects.all()
            context = {}
            #context['workflow_constraints_endpoint'] = reverse('workflow-constraint-options')
            context['users'] = all_users
            context['workflows'] = all_workflows
            return render(request, 'analysis/create_project.html', context)
        else:
            return HttpResponseForbidden()

    def post(self, request, *args, **kwargs):
        if request.user.is_staff:
            workflow_pk = int(request.POST['workflow'])
            owner_pk = int(request.POST['user'])
            try:
                allow_restart = request.POST['allow_restart']
                allow_restart = True
            except MultiValueDictKeyError:
                allow_restart = False
            w = Workflow.objects.get(pk=workflow_pk)
            o = get_user_model().objects.get(pk=owner_pk)
            project = AnalysisProject(workflow=w, owner=o, restart_allowed=allow_restart)
            project.save()
            #return render(request, 'analysis', {})
            #return HttpResponse('Thanks- %s' % str(project.analysis_uuid))
            return redirect('analysis-project-apply-constraints', analysis_uuid=project.analysis_uuid)
        else:
            return HttpResponseForbidden()


class AnalysisProjectApplyConstraints(View):
    '''
    This view handles applying constraints to a project
    '''
    def get(self, request, *args, **kwargs):
        #TODO- check if there are constraints applied already.
        if request.user.is_staff:
            analysis_uuid = kwargs['analysis_uuid']
            try:
                project = AnalysisProject.objects.get(analysis_uuid=analysis_uuid)
            except:
                return HttpResponseBadRequest('Invalid project ID')

            # show the older constraints, if any
            existing_constraints = ProjectConstraint.objects.filter(project=project)
            applied_constraints = []
            if len(existing_constraints) > 0:
                subclasses = ImplementedConstraint.__subclasses__()
                subclass_names = [x.__name__.lower() for x in subclasses]
                for c in existing_constraints:
                    subclass_found = False
                    idx = 0
                    while not subclass_found and idx < len(subclass_names):
                        try:
                            subclass_name = subclass_names[idx]
                            implemented_constraint = getattr(c.constraint, subclass_name)
                            subclass_found = True
                        except:
                            pass
                        idx += 1
                    if subclass_found:
                        value = implemented_constraint.value
                        description = c.constraint.workflow_constraint.description
                        applied_constraints.append((description, value))
                    else: # the implementation of this constraint was not found-- this is a problem!
                        raise Exception('The constraint subclass could not be located.  There is something wrong.')

            workflow = project.workflow
            constraints = WorkflowConstraint.objects.filter(workflow=workflow)
            all_forms = []
            for c in constraints:
                constraint_class = c.implementation_class
                clazz = getattr(analysis.models, constraint_class)
                label_dict = {'value': c.description}
                modelform = modelform_factory(clazz, fields=['value'], labels=label_dict)
                constraint_required = c.required
                all_forms.append(modelform(prefix=c.name,empty_permitted= not constraint_required, use_required_attribute= constraint_required ))
            return render(request, 'analysis/constraints.html', {'forms': all_forms, 'applied_constraints': applied_constraints})
        else:
            return HttpResponseForbidden()

    def post(self, request, *args, **kwargs):
        if request.user.is_staff:
            analysis_uuid = kwargs['analysis_uuid']
            try:
                project = AnalysisProject.objects.get(analysis_uuid=analysis_uuid)
            except:
                return HttpResponseBadRequest('Invalid project ID')

            # remove the older constraints, if any
            existing_constraints = ProjectConstraint.objects.filter(project=project)
            if len(existing_constraints) > 0:
                for c in existing_constraints:
                    c.delete()

            # now go on to apply new constraints, if any
            workflow = project.workflow
            constraints = WorkflowConstraint.objects.filter(workflow=workflow)
            real_error = False
            all_forms = []
            for c in constraints:
                constraint_class = c.implementation_class
                clazz = getattr(analysis.models, constraint_class)
                label_dict = {'value': c.description}
                modelform = modelform_factory(clazz, fields=['value'], labels=label_dict)
                f = modelform(request.POST, prefix=c.name)
                all_forms.append(f)
                if f.is_valid():
                    constraint_obj = f.save(commit=False)
                    constraint_obj.workflow_constraint = c
                    constraint_obj.save()
                    proj_constraint = ProjectConstraint(project=project, constraint=constraint_obj)
                    proj_constraint.save()
                else:
                    was_required = c.required
                    if was_required:
                        real_error = True
            if real_error:
                return render(request, 'analysis/constraints.html', {'forms': all_forms})

            try:
                do_email = request.POST['send_email']
                do_email = True
            except MultiValueDictKeyError:
                do_email = False
            if do_email and settings.EMAIL_ENABLED:
                email_address = project.owner.email
                current_site = Site.objects.get_current()
                domain = current_site.domain
                url = 'https://%s' % domain
                context = {'site': url, 'user_email': email_address}
                email_template = get_jinja_template('email_templates/new_project.html')
                email_html = email_template.render(context)
                email_plaintxt_template = get_jinja_template('email_templates/new_project.txt')
                email_plaintxt = email_plaintxt_template.render(context)
                email_subject = open('email_templates/new_project_subject.txt').readline().strip()
                send_email(email_plaintxt, \
                    email_html, \
                    email_address, \
                    email_subject \
                )
            return HttpResponse('Project created and constraints applied.')
        else:
            return HttpResponseForbidden()



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

            # remove any error messages as well:
            old_errors = JobClientError.objects.filter(project=analysis_project)
            [o.delete() for o in old_errors] 

            return redirect('analysis-project-execute', analysis_uuid=analysis_project.analysis_uuid)
        else:
            return HttpResponseBadRequest('Cannot perform this action.')
            
