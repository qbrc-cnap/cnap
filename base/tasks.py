import datetime

from django.conf import settings
from celery.decorators import task
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site

from base.models import Resource
from helpers.email_utils import send_email
from helpers.utils import get_jinja_template


def send_reminder(user, data):
    '''
    Constructs the email message and sends the reminder
    '''
    email_address = user.email
    current_site = Site.objects.get_current()
    domain = current_site.domain
    url = 'https://%s' % domain
    context = {'site': url, 'user_email': email_address, 'data': data}
    email_template = get_jinja_template('email_templates/expiration_reminder.html')
    email_html = email_template.render(context)
    email_plaintxt_template = get_jinja_template('email_templates/expiration_reminder.txt')
    email_plaintxt = email_plaintxt_template.render(context)
    email_subject = open('email_templates/expiration_reminder_subject.txt').readline().strip()
    send_email(email_plaintxt, email_html, email_address, email_subject)


@task(name='manage_files')
def manage_files():
    '''
    This handles expiring/removal of old files, as well as possibly other
    daily tasks related to file management
    '''
    
    # find any expired resources and mark them inactive and delete
    today = datetime.date.today()
    expired_resources = Resource.objects.filter(is_active=True, expiration_date__lt=today)
    for r in expired_resources:
        r.is_active = False
        r.save()
    
    # Now find any resources that will be expiring soon- construct a list of dates:
    target_date_map = {x:today + datetime.timedelta(days=x) for x in settings.EXPIRATION_REMINDER_DAYS}

    # Go through each user and collect Resources that will expire:
    for u in get_user_model().objects.all():
        # map of number of days to a list of the resources that will expire in that many days
        pending_expiration_map = {k:list(Resource.objects.filter(is_active=True, expiration_date = v, owner=u)) for k,v in target_date_map.items()}
        d = {}
        for num_days, resource_list in pending_expiration_map.items():
            if len(resource_list)>0:
                d[num_days] = [x.name for x in resource_list]
        # email that user:
        if len(d.keys()) > 0:
            send_reminder(u, d)
