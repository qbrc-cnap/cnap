import sys
import os

os.chdir(os.path.dirname(os.path.realpath(__file__)))
sys.path.append(os.path.realpath(os.pardir))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cnap_v2.settings')

import django
from django.conf import settings
django.setup()

from base.models import AvailableZones, CurrentZone


if __name__ == '__main__':
    if settings.CONFIG_PARAMS['cloud_environment'] == settings.GOOGLE:
        default_zone = settings.CONFIG_PARAMS['default_google_zone']
        avail_zones_csv = settings.CONFIG_PARAMS['available_google_zones']
        avail_zones = [x.strip() for x in avail_zones_csv.split(',')]
        for z in avail_zones:
            a = AvailableZones.objects.create(cloud_environment=settings.GOOGLE, zone=z)
            a.save()

        dz = AvailableZones.objects.get(zone=default_zone)
        c = CurrentZone.objects.create(zone=dz)
        c.save()
    else:
        print('Only Google-related settings have been implemented so far.  Exiting.')
        sys.exit(1)
