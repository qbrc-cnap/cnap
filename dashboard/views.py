from django.shortcuts import render
from django.http import HttpResponseForbidden
from django.urls import reverse

from base.models import Issue
from analysis.models import AnalysisProject, Warning, PendingWorkflow

from .dashboard_utils import clone_repository
import dashboard.tasks as dashboard_tasks

def dashboard_index(request):
    user = request.user
    if user.is_staff:

        # get the current analyses that have been created.  We would like to view their status
        analysis_projects = AnalysisProject.objects.filter(completed=False)

        # show any errors in submitted jobs
        job_query_warnings = Warning.objects.all()

        # Show any other issues that might have occurred:
        other_issues = Issue.objects.all()

        # allow us to check the status of the cromwell server

        context = {}
        context['projects'] = analysis_projects
        context['warnings'] = job_query_warnings
        context['issues'] = other_issues

        return render(request, 'dashboard/dashboard_home.html', context)
    else:
        return HttpResponseForbidden()


def add_new_workflow(request):
    user = request.user
    if not user.is_staff:
        return HttpResponseForbidden()

    # otherwise continue on:
    if request.method == 'POST':
        payload = request.POST
        clone_url = payload['clone_url']
        clone_dest, commit_hash = clone_repository(clone_url)
        pwf = PendingWorkflow(
            staging_directory = clone_dest, \
            clone_url = clone_url, \
            commit_hash = commit_hash
        )
        pwf.save()
        pk = pwf.pk
        query_url = reverse('pending-workflow-detail', args=[pk,])
        dashboard_tasks.kickoff_ingestion.delay(pk)
        message = 'The ingestion process has started.  You can monitor the progress by querying the API at %s' % query_url
        context = {'message': message}
        return render(request, 'dashboard/add_new_workflow.html', context)
    else:
        context = {}
        return render(request, 'dashboard/add_new_workflow.html', context)
    
