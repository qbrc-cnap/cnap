from django.shortcuts import render
from django.http import HttpResponseForbidden, JsonResponse, HttpResponseNotAllowed
from django.urls import reverse
from django.conf import settings
from django.contrib.auth import get_user_model

from base.models import Issue, AvailableZones, CurrentZone
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
                try:
                    sj = SubmittedJob.objects.filter(project=p)
                    sj = sj[0]
                    c.cromwell_uuid = str(sj.job_id)
                    c.status = sj.job_status
                except Exception as ex:
                    c.cromwell_uuid = 'Project completion steps may have failed, or database may be corrupted.'
                    c.status = '-'
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
            job_obj.success = j.success
            datestamp = j.timestamp
            job_obj.date = datestamp
            completed_jobs_list.append(job_obj)

        # related to changing the current region/zone:
        current_zone = CurrentZone.objects.all()[0]
        available_zones = [x.zone for x in AvailableZones.objects.all()]
        
        all_users = get_user_model().objects.all()

        context = {}
        context['current_projects'] = analysis_project_list
        context['completed_jobs'] = completed_jobs_list
        context['current_region'] = current_zone
        context['available_zones'] = available_zones
        context['users'] = all_users
        context['new_workflow_url'] = reverse('dashboard-add-workflow')
        context['reset_project_url'] = reverse('analysis-project-reset')
        context['kill_project_url'] = reverse('analysis-project-kill')
        context['change_region_url'] = reverse('region-change')
        context['add_bucket_url'] = reverse('import-bucket')
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
    else:
        return HttpResponseNotAllowed(['POST'])

def import_bucket(request):
    print('in import bucket')
    user = request.user
    if not user.is_staff:
        return HttpResponseForbidden()

    if request.method == 'POST':
        payload = request.POST
        print(payload)
        bucket_url = payload['bucket_url']
        try:
            bucket_user_pk = int(payload['bucket_user'])
            print(bucket_user_pk)
        except ValueError:
            return JsonResponse({'error': 'This endpoint expects that the user is specified with an integer primary key.'}, status=400)

        # check that user exists:
        try:
            bucket_user = get_user_model().objects.get(pk=bucket_user_pk)
            print(bucket_user)
        except ObjectDoesNotExist as ex:
            return JsonResponse({'error': 'User with PK=%d does not exist' % bucket_user_pk}, status=400)

        # handle the bucket--
        if bucket_url[:5] == settings.CONFIG_PARAMS['google_storage_gs_prefix']:
            print('Import bucket %s' % bucket_url)
        else:
            return JsonResponse({'error': 'The bucket URL did not include a prefix or was not recognized.'}, status=400)


        return JsonResponse({'message': 'Bucket import process has started.'})


def change_region(request):
    user = request.user
    if not user.is_staff:
        return HttpResponseForbidden()

    if request.method == 'POST':
        payload = request.POST
        new_region = payload['region']
        print(new_region)

        try:
            a = AvailableZones.objects.get(zone=new_region)
        except base.models.AvailableZones.DoesNotExist:
            return HttpResponseBadRequest()

        # delete any existing 'current' zones.  Should only be one
        [x.delete() for x in CurrentZone.objects.all()]

        # set the chosen zone as the current zone.
        c = CurrentZone.objects.create(zone=a)
        c.save()

        return JsonResponse({'message': 'Region has been successfully changed.'})
