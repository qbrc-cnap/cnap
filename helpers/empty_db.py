import sys
import os

os.chdir(os.path.dirname(os.path.realpath(__file__)))
sys.path.append(os.path.realpath(os.pardir))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cnap_v2.settings')

import django
from django.conf import settings
django.setup()

from custom_auth.models import CustomUser
from transfer_app.models import *

for u in CustomUser.objects.all():
  u.delete()

for r in Resource.objects.all():
  r.delete()

for t in Transfer.objects.all():
  t.delete()

for t in TransferCoordinator.objects.all():
  t.delete()
