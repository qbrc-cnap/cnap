import os
from celery import Celery
from django.conf import settings
from django.apps import apps

from celery.schedules import crontab

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cnap_v2.settings')

app = Celery('cnap_v2')

# Using a string here means the worker will not have to
# pickle the object when using Windows.
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks(lambda: [n.name for n in apps.get_app_configs()])

app.conf.beat_schedule = {
    'check_jobs':{
        'task': 'check_job',
        'schedule': 60.0
    },
    'manage_file': {
        'task': 'manage_files',
        'schedule': crontab(hour=8, minute=15)
    }
}

@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))
