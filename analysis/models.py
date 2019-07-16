from jinja2 import Environment, FileSystemLoader

from django.db import models
from django.contrib.auth import get_user_model
import uuid

from django.conf import settings
from django.contrib.sites.models import Site

from base.models import Organization, Resource
from helpers.email_utils import send_email
from helpers.utils import get_jinja_template


class Workflow(models.Model):
    '''
    This class captures the notion of a fully implemented
    workflow/pipeline.

    It is used to track the locations of the potentially many WDL-based
    workflows and subversions of those.
    '''

    # this keeps track of the analysis type, and we reference it in the URL
    workflow_id = models.PositiveSmallIntegerField()

    # this keeps track of potential sub-versions of a workflow
    version_id = models.PositiveSmallIntegerField()

    # the url of the git repository (i.e. the link used in `git clone <url>`)
    git_url = models.CharField(max_length=200, blank=False, null=False)

    # the git commit ID of the workflow repository:
    git_commit_hash = models.CharField(max_length=100, blank=False, null=False)

    # this keeps track of the workflow name. 
    workflow_name = models.CharField(max_length=100)

    # this keeps track of whether a workflow is the most recent or the "default"
    is_default = models.BooleanField(default=False)

    # this tracks whether a particular workflow (workflow_id AND version_id)
    # is active and able to be accessed
    # False by default since we do not necessarily want all the ingested
    # workflows to be automatically live
    is_active = models.BooleanField(default=False)

    # Is this workflow able to be restarted?  As determined by the 
    # presence of a 'pre-check' WDL file.  If bad inputs are encountered
    # the workflow may be restarted.  This flag only controls whether the
    # Workflow CAN be restarted, while the flag in the AnalysisProject model 
    # dictates whether restarts are allowed for that particular project
    restartable = models.BooleanField(default=False) 

    # this keeps track of the location of the folder holding the 
    # WDL and associated files.  Allows us to locate the proper WDL
    # when an analysis is requested.
    workflow_location = models.TextField(max_length=2000)

    # a human-readable name for the 'title' of a workflow/analysis
    # Used for display-- users will see a list of these describing the 
    # workflows they can run.  Can be added to the WDL file in a meta section
    # under the keyword `workflow_title`
    workflow_title = models.CharField(max_length=200, default='Workflow')

    # a SHORT description of the workflow to help users.  Not too long (See max length)
    # Can be added to WDL under meta section with key `workflow_short_description`
    workflow_short_description = models.TextField(max_length=400, default='', blank=True)

    # a longer description of the workflow to help users.  Not too long (See max length)
    # Can be added to WDL under meta section with key `workflow_long_description`
    workflow_long_description = models.TextField(max_length=2000, default='', blank=True)

    class Meta:
        # ensure the the combination of a workflow and a version is unique
        unique_together = ('workflow_id', 'version_id')

    def __str__(self):
        return '%s (version ID: %s)' % (self.workflow_name, self.version_id)


class PendingWorkflow(models.Model):
    '''
    This class is used with the workflow ingestion process.  Typically, a user
    with admin privileges will submit a git repository URL to the dashboard interface
    which will kickoff the process of ingesting and creating a new workflow.  Since
    that process can take a while (and/or have an error), we save the clone URL here
    so that they can check on the progress
    '''
    # The time it was submitted and finished:
    start_time = models.DateTimeField(null=False, auto_now_add=True)
    finish_time = models.DateTimeField(blank=True, null=True)

    # the url submitted for the clone:
    clone_url = models.CharField(max_length=200, blank=False)

    # we track the version by the git commit hash 
    commit_hash = models.CharField(max_length=100, blank=False)

    # A status message for tracking progress
    status = models.CharField(max_length=200, blank=True, default='')

    # Did it experience an error?
    error = models.BooleanField(default=False)

    # Has the ingestion completed?
    complete = models.BooleanField(default=False)

    # The directory where the repo was cloned and staged:
    staging_directory = models.CharField(max_length=200, blank=False)


class AnalysisProject(models.Model):
    '''
    This class captures information that is contained via the combination of a Workflow
    and an actor who instantiates the Workflow instance.  This ties a Workflow to a particular
    user.
    '''
    # field for tracking (perhaps with an external LIMS)
    tracking_id = models.CharField(max_length=200, blank=True, default='')

    # field for url referencing.  Serves the same purpose as primary key, but 
    # when users hit the URL for their analysis, we prefer it not be a simple integer
    analysis_uuid = models.UUIDField(unique=True, default = uuid.uuid4, editable=True)

    # an analysis needs a location where the files are stored.  Filled in the save method
    # technically a bucket and a folder inside that bucket
    analysis_bucketname = models.TextField(max_length=2000, blank=True)

    # foreign key to the Workflow
    workflow = models.ForeignKey('Workflow', on_delete=models.CASCADE)

    # foreign key to the owner/user
    owner = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)

    # boolean for whether the analysis has been started/run
    started = models.BooleanField(default=False)

    # boolean for whether complete
    completed = models.BooleanField(default=False)

    # boolean indicating whether restarts are allowed
    # (perhaps due to bad input)
    restart_allowed = models.BooleanField(default=False)

    # for displaying the job status, as returned by Cromwell
    status = models.CharField(max_length=200, default='', blank=True)

    # for displaying longer messages, like possible errors:
    message = models.TextField(max_length=5000, default='', blank=True)

    # fields to track status
    start_time = models.DateTimeField(blank=True, null=True)
    finish_time = models.DateTimeField(blank=True, null=True)
    success = models.BooleanField(default=False)
    error = models.BooleanField(default=False)

    def save(self, *args, **kwargs):

        if self._state.adding: # if creating, NOT updating
            bucketname = '%s/%s/%s' % (settings.CONFIG_PARAMS['storage_bucket_prefix'], \
                str(self.owner.user_uuid), \
                self.analysis_uuid)
            self.analysis_bucketname = bucketname
            if settings.EMAIL_ENABLED:
                email_address = self.owner.email
                current_site = Site.objects.get_current()
                domain = current_site.domain
                url = 'https://%s' % domain
                context = {'site': url, 'user_email': email_address}
                email_template = get_jinja_template('email_templates/new_project.html')
                email_html = email_template.render(context)
                email_plaintxt_template = get_jinja_template('email_templates/new_project.txt')
                email_plaintxt = email_plaintxt_template.render(context)
                email_subject = open('email_templates/new_project_subject.txt').readline().strip()
                #send_email(email_plaintxt, \
                #    email_html, \
                #    email_address, \
                #    email_subject \
                #)
        super().save(*args, **kwargs)

    def __str__(self):
        return '%s (id: %s, client: %s)' % (self.workflow.workflow_name, str(self.analysis_uuid), self.owner)


class WorkflowContainer(models.Model):
    '''
    This class allows us to track the containers that comprise a workflow.  During ingestion, we get 
    all the containers necessary to run a workflow.  We save those details in this table
    '''
    # foreign key to the Workflow
    workflow = models.ForeignKey('Workflow', on_delete=models.CASCADE)

    # the full tag ID, such as "docker.io/user/image:tag"
    image_tag = models.CharField(max_length=255, blank=False)

    # the digest/hash of the container, obtained by querying dockerhub
    hash_string = models.CharField(max_length=255, blank=False)


class AnalysisProjectResource(models.Model):
    '''
    This class is used to tie Resource instances to AnalysisProject instances so 
    we can better display in the UI.  Some Resources will NOT be associated with 
    AnalysisProjects (e.g. files they upload), but some files will be associated with 
    projects, as they are the outputs of a particular project.
    '''
    analysis_project = models.ForeignKey(AnalysisProject, on_delete=models.CASCADE)
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE)


class OrganizationWorkflow(models.Model):
    '''
    This model joins an Organization to the list of available Workflows
    '''
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE)


class SubmittedJob(models.Model):
    '''
    This model is used for tracking jobs that are ongoing.  
    '''

    # the project that is being run
    project = models.ForeignKey('AnalysisProject', on_delete=models.CASCADE)

    # the job ID returned by Cromwell on the job submission
    job_id = models.CharField(max_length=64, blank=False)

    # status
    job_status = models.CharField(max_length=200, blank=False)

    # where the staging directory is-- for debug purposes.
    # This is an absolute path
    job_staging_dir = models.CharField(max_length=255, blank=False)

    # is this a pre-check job?  We can launch pre-workflows
    # that check user input prior to launching the entire pipeline
    is_precheck = models.BooleanField(default=False)

    def __str__(self):
        return '%s' % (self.job_id)


class CompletedJob(models.Model):
    '''
    This model is used for tracking jobs that have completed.  In the instance that something
    goes awry following completion of a SubmittedJob and marking an AnalysisProject "complete", we 
    log that here.  
    '''

    # the project that is being run
    project = models.ForeignKey('AnalysisProject', on_delete=models.CASCADE)

    # the job ID returned by Cromwell on the job submission
    job_id = models.CharField(max_length=64, blank=False)

    # status
    job_status = models.CharField(max_length=200, blank=False)

    # where the staging directory is-- for debug purposes.
    # This is an absolute path
    job_staging_dir = models.CharField(max_length=255, blank=False)

    # did the job succeed?
    success = models.BooleanField(default=False)

    timestamp = models.DateTimeField(blank=False, null=False, auto_now_add=True)

    def __str__(self):
        return '%s' % (self.job_id)


class Warning(models.Model):
    '''
    This class is used to track when periodic tasks generate errors.
    For example, if the Cromwell server is down and we cannot check job status
    we send an email to the admins.  Since that task might run every minute, that would
    send many, many emails before it can be fixed.  The entries in this database table
    track this so that doesn't happen
    '''
    message = models.TextField(max_length=2000)
    job = models.ForeignKey('SubmittedJob', on_delete=models.CASCADE)


class JobClientError(models.Model):
    '''
    This class/table is used for tracking errors that were due to incorrect user inputs.
    After a pre-check job is complete, the backend parses the stderr files and can then parse 
    an arbitrary number of errors (as strings).  Rather than keep all of those as a large block of text
    we save them here.  Then, when the client visits the page to view errors, they are displayed consistently.
    '''

    # need to know which project it originated from:
    project = models.ForeignKey('AnalysisProject', on_delete=models.CASCADE)

    # the text of the error itself:
    error_text = models.TextField(max_length=2000, blank=True)


class WorkflowConstraint(models.Model):
    '''
    This is a base class that holds information about various constraints we can place
    on workflows.  Fields here should be applicable to the concrete classes that derive
    from this class

    Note that it is marked as abstract, so you cannot instantiate instances of this--
    it has no concept of *how* a constraint might be constructed.
    '''

    # the workflow to which this constraint is applied
    workflow = models.ForeignKey('Workflow', on_delete=models.CASCADE)

    # a name for the constraint.  Not used for anything important, but aim for
    # this to be descriptive so its function is obvious 
    name = models.CharField(max_length=200, blank=False)

    # This is a longer, full-text description of what the constraint does
    description = models.TextField(max_length=5000, blank=False)

    # This is a path to a python module that has a function of the appropriate signature.
    # It contains a function that does the actual logic of checking the constraint
    # The function is run prior to job submission so that the constraints can be checked.
    handler = models.CharField(max_length=255, blank=False)

    # the concrete implementation class which will be used.  Should be one of the 
    # classes derived from this model
    implementation_class = models.CharField(max_length=50, blank=False)

    # is this constraint required on this workflow?
    required = models.BooleanField(default=False)

    def __str__(self):
        return '%s (%s)' % (self.name, self.implementation_class)

class ImplementedConstraint(models.Model):
    workflow_constraint = models.ForeignKey('WorkflowConstraint', on_delete=models.CASCADE)

    def __str__(self):
         return str(type(self).__name__)

class NumericConstraint(ImplementedConstraint):
    '''
    This can be used for any simple numeric constraint.  e.g. if some value
    cannot be more than 10, the "value" can be 10, and the handler function
    in the parent class will do the appropriate check for less-than.
    '''
    value = models.FloatField(null=False)

    def __str__(self):
         return 'NumericConstraint, value=%s' % self.value


class AnalysisUnitConstraint(ImplementedConstraint):
    '''
    This class is used to track the concept of an "analysis unit"
    In most cases, an analysis proceeds on a number of "samples", such as
    fastq files representing biological replicates.  However, this allows 
    the developer of the WDL to define an appropriate unit upon which they can
    quantify the analysis and constrain the analysis
    '''
    value = models.PositiveIntegerField(null=False)

    def __str__(self):
         return 'AnalysisUnitConstraint, value=%s' % self.value


class ProjectConstraint(models.Model):
    '''
    This class holds the information about which constraints are applied
    to which AnalysisProject instances
    '''
    project = models.ForeignKey('AnalysisProject', on_delete=models.CASCADE)
    constraint = models.ForeignKey('ImplementedConstraint', on_delete=models.CASCADE)
