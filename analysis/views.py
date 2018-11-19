import os

from django.conf import settings
from django.shortcuts import render
from django.http import HttpResponseBadRequest
from django.views import View
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

from .models import Workflow
from .view_utils import get_workflow, \
    validate_workflow_dir, \
    fill_context


def home(request):
    return render(request, 'analysis/home.html', {'msg': 'hello'})


class AnalysisView(View):

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        '''
        When the url is requested using the GET method, we display the form.

        Depending on the implementation of the workflow, this could require 
        dynamic content to be loaded from the database.  Hence, we need to 
        look at the workflow details to determine if any such details are needed.
        '''

        # The kwargs dict carries the URL parameters.
        # We expect at least a `workflow_id`.  An optional
        # `version_id` can also be provided.
        workflow_id = kwargs['workflow_id']
        try:
            version_id = kwargs['version_id']
        except KeyError:
            version_id = None
        
        try:
            workflow_obj = get_workflow(workflow_id, version_id, request.user.is_staff)
        except Exception:
            return HttpResponseBadRequest('Error when querying for workflow.')

        # if we are here, we have a workflow object from the database.
        # We can use that to find the appropriate workflow directory where
        # everything lives.

        # prepare and empty context which we will fill-in
        context_dict = {}

        # now that we have an allegedly valid workflow directory,
        # we look at the GUI spec and load the 'handlers' for each input 
        # element.  These are snippets of python code that specify how
        # dynamic, database-driven data is queried for the UI.
        fill_context(request, workflow_obj, context_dict)
        workflow_dir = workflow_obj.workflow_location
        template = os.path.join(settings.WORKFLOWS_DIR, workflow_dir, settings.HTML_TEMPLATE_NAME)
        return render(request, template, context_dict)

    def post(self, request, *args, **kwargs):
        '''
        With a POST request, the form is being submitted.  We parse the contents
        of that request, prepare a pending analysis, and prepare a summary.
        '''
        return render(request, 'analysis/home.html', {'msg': 'post view'})

