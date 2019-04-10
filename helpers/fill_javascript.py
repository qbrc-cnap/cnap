'''
This script uses the configurations provided by the user and fills out 
template javascript files.  The completed file is then used for the front end

Note that it looks in the $APP_ROOT/static/ directory (skipping admin dir), which means you need
to run python3 manage.py collectstatic prior to this.

This also assumes that any variables you define in your template MUST BE DEFINED
in config/general.cfg

For instance, if the js file has {{foo}}, then your config file must contain:
...
FOO=Bar
...

in one of the sections of general.cfg.  Note that when configparser reads the variables
from the config file, it lowers them, so the key "FOO" above becomes "foo".  The variables
are case-sensitive, so {{foo}} would be replaced by "Bar"
'''

import sys
import os
import configparser
import uuid

os.chdir(os.path.dirname(os.path.realpath(__file__)))
sys.path.append(os.path.realpath(os.pardir))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cnap_v2.settings')

import django
from django.conf import settings
django.setup()

from django.urls import reverse

from jinja2 import Environment, FileSystemLoader

# in the settings.STATIC_ROOT dir, there are subdirs for each
# application.  We are not going to mess with anything that is
# provided out of the box, such as django's admin.  Thus
# this is a list of those dirs we should skip when searching for
# templated javascript files
SKIP_DIRS = ['admin', 'rest_framework']

def fill_template(js_path, params):
    js_dir = os.path.dirname(js_path)
    js_basename = os.path.basename(js_path)

    env = Environment(loader=FileSystemLoader(js_dir))
    template = env.get_template(js_basename)
    # rewrites the template.js to just js, and puts in same directory
    new_js = os.path.join(js_dir, '.'.join(js_basename.split('.')[:-2]) + '.js')
    with open(new_js, 'w') as outfile:
        outfile.write(template.render(params))


def get_javascript_files():
    js_files = []
    app_root = os.environ['APP_ROOT']
    accepted_roots = [os.path.join(settings.STATIC_ROOT, x) for x in os.listdir(settings.STATIC_ROOT) if not x in SKIP_DIRS]
    for start_dir in accepted_roots:
        for root, dirs, files in os.walk(start_dir):
            for f in files:
                # if the file ends with 'template.js'
                if '.'.join(f.split('.')[-2:]).lower() == 'template.js':
                    print('Found: %s' % os.path.join(root,f))
                    js_files.append(os.path.join(root, f))
    return js_files


def get_params():
    cfg = configparser.ConfigParser()
    cfg.read(os.path.join(os.environ['APP_ROOT'], 'config', 'general.cfg'))
    all_sections = [x for x in cfg.sections()]
    all_sections.append('DEFAULT')
    d = {}
    for s in all_sections:
        section = cfg[s]
        for key in section:
            d[key] = section[key]
    return d

def get_urls():
    '''
    The javascript has some API endpoints and other URLs it needs to
    access.  The actual URLs for those could change and we need the URLs
    in the javascript to stay in-sync. Here, we use the 'reverse' functionality
    from django to get the URLs by the NAME of the URLs.  This means you CANNOT
    change the 'name' parameter in the url conf (any of the urls.py files)
    This function returns a dictionary of URLs.  They keys are the names of the params
    in the javascript template, and they point at the URLs.
    '''
    url_dict = {}
    url_dict['resource_tree_endpoint'] = reverse('resource-list-tree')
    url_dict['transferred_resources_endpoint'] = reverse('transferred-resource-list')
    url_dict['upload_url'] = reverse('upload-transfer-initiation')
    url_dict['download_url'] = reverse('download-transfer-initiation')
    url_dict['logout_url'] = reverse('logout')
    url_dict['analysis_list_endpoint'] = reverse('analysis-project-list')

    # for the project URLs, the only way to get the 'form' of the url is to submit a
    # dummy uuid and strip it off
    full_dummy_project_url = reverse('analysis-project-execute', args=[uuid.uuid4()])
    # go from 1 to -2 since the url is returned with leading and trailing slashes, so the
    # split ends up with empty strings in the first and last position of the list.  the second
    # to last element is the uuid, which we are removing.
    project_endpoint = '/'.join(full_dummy_project_url.split('/')[1:-2])
    project_endpoint = '/' + project_endpoint + '/' 
    url_dict['analysis_project_endpoint'] = project_endpoint
    return url_dict


def get_other_params():
    return {'dropbox': settings.DROPBOX, 'google_drive': settings.GOOGLE_DRIVE}

if __name__ == '__main__':
    js_files = get_javascript_files()
    params = get_params()
    params.update(get_urls())
    params.update(get_other_params())
    for js in js_files:
        fill_template(js, params)
