import os
import configparser
from jinja2 import Environment, FileSystemLoader
import requests

from django.conf import settings

import google
from google.cloud import storage

from base.models import CurrentZone
from helpers.email_utils import notify_admins


def get_jinja_template(template_path):

    if template_path[0] != '/':
        template_path = os.path.join(settings.BASE_DIR, template_path)

    # load the environment/template for the jinja template engine: 
    template_dir = os.path.realpath(
        os.path.abspath(
            os.path.dirname(
                template_path
            )
        )
    )
    env = Environment(loader=FileSystemLoader(template_dir))
    return env.get_template(
        os.path.basename(template_path)
    )

def load_config(config_filepath, config_sections=[]):
    '''
    config_filepath is the path to a config/ini file
    config_sections is a list of names for sections in that file
    if None, then just return the [DEFAULT] section
    '''

    config = configparser.ConfigParser()
    config.read(config_filepath)
    main_dict = {}
    for key in config[config.default_section]:
        main_dict[key] =  config[config.default_section][key]

    d = {}
    for config_section in config_sections:
        if config_section in config:
            d1 = {}
            for key in config[config_section]:
                d1[key] =  config[config_section][key]
            keys_intersection = set(d1.keys()).intersection(set(d.keys()))
            if ((len(keys_intersection)==0) 
                 or 
                (set(main_dict.keys()) == keys_intersection)):
                d.update(d1)
            else:
                raise Exception('Config variable collision with variables %s.  '
                    'Check that the variables defined in section %s '
                    'do not match any in other sections of the %s file'
                    % (keys_intersection, config_section, config_filepath)
                )
        else:
            raise configparser.NoSectionError()
    main_dict.update(d)
    return main_dict


def read_general_config(config_filepath, additional_sections=[]):
    '''
    This loads the "main" config file.  We have this function since
    the configuration depends on environment parameters.
    '''
    config_dict = load_config(config_filepath, additional_sections)

    # Based on the choice for the compute environment, read those params also:
    try:
        compute_env = config_dict['cloud_environment']
    except KeyError as ex:
        raise Exception('Your configuration file needs to define a variable named %s which indicates the cloud provider' % ex)

    config_dict.update(load_config(config_filepath, [compute_env,]))

    return config_dict


def perform_get_query(query_url, headers=None):
    '''
    This performs a get request, handling retries if required.
    If it fails MAX_TRIES times, it gives up.

    If query is successful, returns a dictionary
    '''
    # how many times do we try to contact the registry before giving up:
    MAX_TRIES = 5

    success = False
    tries = 0
    while (not success) and (tries < MAX_TRIES):
        if headers:
            response = requests.get(query_url, headers=headers)
        else:
            response = requests.get(query_url)
        if response.status_code == 200:
            success = True
            return response.json()
        else:
            print('Query failed: %s' % response.text)
            tries += 1
    # exited the loop.  if success is still False, exit
    if not success:
        raise Exception('After %d tries, could not get '
        'a successful response from url: %s' % (MAX_TRIES, query_url))


def query_for_digest(image_w_tag):
    '''
    This function constructs the queries for the digest of a particular container
    Returns the hash string

    `image_w_tag` is something like 'docker.io/userA/foo:v0.1'
    '''

    image_name, tag = image_w_tag.split(':')
    image_name = '/'.join(image_name.split('/')[1:])

    # first need to query for a token, which is needed for hitting the registry URL
    auth_url = 'https://auth.docker.io/token?scope=repository:%s:pull&service=registry.docker.io' % image_name
    j1 = perform_get_query(auth_url)
    auth_token = j1['token']

    # with that token, query for the digest:
    h = {}
    h['Accept'] = 'application/vnd.docker.distribution.manifest.v2+json'
    h['Authorization'] = 'Bearer %s' % auth_token
    digest_url = 'https://registry-1.docker.io/v2/%s/manifests/%s' % (image_name, tag)
    j2 = perform_get_query(digest_url, headers=h)
    image_digest = j2['config']['digest']
    return image_digest


def create_regional_bucket(bucketname):
    '''
    Creates a storage bucket in the current region.
    '''
    client = storage.Client()
    b = storage.Bucket(bucketname)
    b.name = bucketname
    current_zone = CurrentZone.objects.all()[0] # something like "us-east1-c"
    current_region = '-'.join(current_zone.split('-')[:2])
    b.location = current_region
    try:
        final_bucket = client.create_bucket(b)
        return
    except google.api_core.exceptions.Conflict as ex:
        message = '''
            An attempt was made to create a bucket at %s.  However, the storage API indicated
            that this was an existing bucket.  Exception reported: %s  
        ''' % (bucketname, ex)
    except google.api_core.exceptions.BadRequest as ex:
        message = '''
            An attempt was made to create a bucket at %s.  However, the storage API indicated
            that there was an error during creation.  Exception reported: %s  
        ''' % (bucketname, ex)
    except Exception as ex:
        message = '''
            An attempt was made to create a bucket at %s.  However, there was an unexpected exception
            raised.  Exception reported: %s  
        ''' % (bucketname, ex)
    subject = 'Error with bucket creation'
    notify_admins(message, subject)