import os
import sys
import shutil
import django
from django.conf import settings

os.chdir(os.path.dirname(os.path.realpath(__file__)))
sys.path.append(os.path.realpath(os.pardir))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cnap_v2.settings')
django.setup()

dest_dir = settings.STATIC_LOC
src_dir = settings.STATIC_ROOT

dir_contents = [os.path.join(src_dir, x) for x in os.listdir(src_dir)]
for x in dir_contents:
    if os.path.isdir(x):
        shutil.copytree(x, '/%s/static/%s' % (dest_dir, os.path.basename(x)))
    else:
        shutil.copy(x, '/%s/static/' % dest_dir)
