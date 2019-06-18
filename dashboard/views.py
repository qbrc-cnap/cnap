from django.shortcuts import render
from django.http import HttpResponseForbidden, JsonResponse
from django.urls import reverse
from django.conf import settings

from base.models import Issue
from analysis.models import AnalysisProject, Warning, PendingWorkflow, CompletedJob, SubmittedJob

from .dashboard_utils import clone_repository
import dashboard.tasks as dashboard_tasks

class CompletedJobObject(object):
    pass

class CurrentProject(object):
    pass

def dashboard_index(request):
    user = request.user
    if user.is_staff:

        # get the current analyses that have been created.  We would like to view their status
        open_analysis_projects = AnalysisProject.objects.filter(completed=False)
        analysis_project_list = []
        for p in open_analysis_projects:
            c = CurrentProject()
            c.workflow_name = p.workflow.workflow_name
            c.version = p.workflow.version_id
            c.cnap_uuid = str(p.analysis_uuid)
            c.client = p.owner.email
            started = p.started
            c.started = started
            c.failed = p.error
            if started and not p.error: # still running
                sj = SubmittedJob.objects.filter(project=p)
                print(p)
                sj = sj[0]
                c.cromwell_uuid = str(sj.job_id)
                c.status = sj.job_status
            else:
                c.cromwell_uuid = None
                c.status = None
            analysis_project_list.append(c)

        # get the completed jobs.  This can allow us to see multiple failures for a single project.  The JOB may be complete, 
        # but the project may still be open since it has not succeeded.
        completed_jobs = CompletedJob.objects.all()
        completed_jobs_list = [] 
        for j in completed_jobs:
            job_obj = CompletedJobObject()
            project = j.project
            job_obj.workflow_name = project.workflow.workflow_name
            job_obj.version = project.workflow.version_id
            job_obj.cnap_uuid = str(project.analysis_uuid)
            job_obj.cromwell_uuid = str(j.job_id)
            job_obj.client = project.owner.email
            datestamp = j.timestamp
            job_obj.date = datestamp
            completed_jobs_list.append(job_obj)

        context = {}
        context['current_projects'] = analysis_project_list
        context['completed_jobs'] = completed_jobs_list
        context['current_region'] = settings.CONFIG_PARAMS['google_zone']
        context['new_workflow_url'] = reverse('dashboard-add-workflow')
        context['reset_project_url'] = reverse('analysis-project-reset')
        context['kill_project_url'] = reverse('analysis-project-kill')
        return render(request, 'dashboard/dashboard.html', context)
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
        #return render(request, 'dashboard/add_new_workflow.html', context)
        return JsonResponse(context)
