import sys
import os
import datetime
import random

os.chdir(os.path.dirname(os.path.realpath(__file__)))
sys.path.append(os.path.realpath(os.pardir))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cnap_v2.settings')

import django
from django.conf import settings
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site

import cnap_v2.utils as utils
from transfer_app.models import Resource, Transfer, TransferCoordinator

def populate():
    # read the live test config to create our dummy user and resource for live testing:
    params = settings.LIVE_TEST_CONFIG_PARAMS
    user_model = get_user_model()
    try:
        test_user = user_model.objects.create_user(email=params['test_email'],
            password=params['test_password']
        )
    except django.db.utils.IntegrityError as ex:
        print('Could not create user.  Likely already exists.')
        #sys.exit(0)

    file_list = [x.strip() for x in params['files_to_transfer'].split(',')]
    size_list = [x.strip() for x in params['file_sizes_in_bytes'].split(',')]
    if len(file_list) != len(size_list):
        print('''Check your live test configuration template-- 
                 you need the same number of items in both the list of files and the file sizes''')
        sys.exit(1)
 
    for f,s in zip(file_list, size_list):
        print('Creating resource for path=%s' % f)
        basename = os.path.basename(f)
        r = Resource(path=f,
            name = basename,
            source = settings.GOOGLE,
            size=s,
            owner=test_user
        )
        r.save()

    print('Done populating for live test.  Moving onto population for UI')

    # Here we populate some items for populating the UI for a dummy user
    # We have some downloads above (Which will actually exist for a real transfer)
    # We add a couple of "inactive" Resources here (since they have been "downloaded").
    # The history needs to reference Transfers, which, in turn, reference Resources
    inactive_resource_sources = [
        settings.GOOGLE,
        settings.GOOGLE,
        settings.DROPBOX,
        settings.DROPBOX,
        settings.GOOGLE_DRIVE,
        settings.GOOGLE,
        settings.GOOGLE
    ]

    inactive_resource_paths = [
        'xyz://dummy-bucket/file_1.txt', 
        'xyz://dummy-bucket/file_2.txt',
        'https://dropbox-link/file_3.txt', # an upload from dropbox
        'https://dropbox-link/failed_upload.txt', # will be a FAILED upload from dropbox
        'abcd1234/drive_upload.txt', #mock the ID we get from Drive, which is effectively a path (upload)
        'xyz://dummy-bucket/ongoing.txt', # will be an ongoing download to drive
        'xyz://dummy-bucket/failed_download.txt' # will be a failed dropbox download 
    ]

    file_names = [os.path.basename(x) for x in inactive_resource_paths]

    destinations = [settings.DROPBOX,
        settings.DROPBOX,
        settings.GOOGLE,
        settings.GOOGLE,
        settings.GOOGLE,
        settings.GOOGLE_DRIVE,
        settings.DROPBOX
    ]
    completion_status = [True, True, True, True, True, False, True]
    success_status = [True, True, True, False, True, False, False]
    inactive_resource_sizes = [random.randint(1000,1000000) for x in range(len(inactive_resource_sources))]
    inactive_resource_dates = [datetime.datetime(
                                   year=random.randint(2016, 2018), 
                                   month=random.randint(1,12), 
                                   day=random.randint(1,28)) for x in range(len(inactive_resource_sources))]

    inactive_resources = []
    for src,p,s,d,f in zip(inactive_resource_sources, 
            inactive_resource_paths, 
            inactive_resource_sizes, 
            inactive_resource_dates,
            file_names
        ):
        r = Resource(path=p,
            name = f,
            source=src,
            size=s,
            owner=test_user, 
            date_added = d,
            is_active = False,
        )
        r.save()
        inactive_resources.append(r)
        

    # We populate a history here, so there is content in that view.
    for i, r in enumerate(inactive_resources):

        is_complete = completion_status[i]
        was_success = success_status[i]

        # Make up some random time offsets so we can mock "real"
        # transfer start and finish times (relative to the date
        # the mock resource was "added")
        dt1 = datetime.timedelta(days=random.randint(0,5),
                 hours=random.randint(1,12),
                 minutes=random.randint(0,59),
                 seconds=random.randint(0,59)
             )
        dt2 = datetime.timedelta(days=random.randint(0,1),
                 hours=random.randint(1,12),
                 minutes=random.randint(0,59),
                 seconds=random.randint(0,59)
             )
        start_time = r.date_added + dt1

        if is_complete:
            finish_time = start_time + dt2

        if (r.source == settings.GOOGLE):
            download_state = True
            destination = destinations[i]
        else: # mocked upload
            download_state = False
            # if it was an upload, then the destination is a bucket, so make up a name
            destination = destinations[i]

        # since we are creating Transfer objects below, we need
        # them to refer to a TransferCoordinator.  Just make 
        # a single TransferCoordinator for each Transfer, rather 
        # than grouping them as would happen when a user transfers >1 files
        tc = TransferCoordinator(completed=is_complete, 
                 start_time=start_time, 
                 finish_time=finish_time if is_complete else None
        )
        tc.save()

        t = Transfer(download=download_state, 
                resource=r, 
                completed=is_complete,
                success=was_success,
                start_time = start_time,
                finish_time = finish_time if is_complete else None,
                destination = destination,
                # just make the originator same as the resource owner (does not have to be)
                originator=r.owner, 
                coordinator=tc
            )
        t.save()


def edit_domain():
    expected_site_id = settings.SITE_ID
    site = Site.objects.get(pk=expected_site_id)
    site.name = settings.ALLOWED_HOSTS[0]
    site.domain = settings.ALLOWED_HOSTS[0]
    site.save()


if __name__ == '__main__':
    print('Starting database population for live testing...')
    populate()

    print('Editing database for your domain...')
    edit_domain()
