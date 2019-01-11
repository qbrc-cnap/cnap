'''
This script guides users to answer questions and fills in the
details in config and settings files as appropriate.
'''

import os
import glob
import sys
import re
from jinja2 import Environment, FileSystemLoader
from Crypto.Cipher import DES

def take_inputs():

    params = {}

    print('Please enter inputs as prompted\n')

    domain = input('Enter your domain.  Note that callbacks will often not work with raw IPs : ')
    params['domain'] = domain

    print('\n\n\n')
    cloud_environment = input('Which cloud provider? (google, aws): ')
    cloud_environment = cloud_environment.lower()
    if cloud_environment == 'google':
        google_project = input('Enter the Google project ID (NOT the numerical ID): ')
        google_project_number = input('Enter the Google project number: ')
        google_zone = input('Enter the desired zone (e.g. "us-east1-b"): ')

        params['cloud_environment'] = cloud_environment
        params['google_project_id'] = google_project 
        params['google_project_number'] = google_project_number 
        params['google_zone'] = google_zone

    elif cloud_environment == 'aws':
        print('Have not implemented AWS config')
        sys.exit(0)
    else:
        sys.exit(1)

    use_at_least_one_service = False
    print('\n\n\n')
    use_dropbox = input('Are you connecting to Dropbox?: (y/n) ')[0].lower()
    if use_dropbox == 'y':
        use_at_least_one_service = True
        dropbox_client_id = input('Enter the Dropbox client ID: ')
        dropbox_secret = input('Enter the Dropbox secret: ')
        params['dropbox_client_id'] = dropbox_client_id
        params['dropbox_secret'] = dropbox_secret
        params['dropbox_enabled'] = True
        print('***Ensure you have registered the callback URL with Dropbox***')
    else:
        params['dropbox_enabled'] = False
    print('\n\n\n')
    use_drive = input('Are you connecting to Google Drive?: (y/n) ')[0].lower()
    if use_drive == 'y':
        use_at_least_one_service = True
        drive_client_id = input('Enter the Drive client ID: ')
        drive_secret = input('Enter the Drive secret: ')
        drive_api_key = input('Enter the API key for Google Drive. '
                              'Note that this is a public key used to identify '
                              'your application to Google, in addition to the '
                              'client ID/secret above: ')
        params['drive_client_id'] = drive_client_id
        params['drive_secret'] = drive_secret
        params['drive_api_key'] = drive_api_key
        params['drive_enabled'] = True
        print('***Ensure you have registered the callback URL with Google Drive***')
    else:
        params['drive_enabled'] = False


    if not use_at_least_one_service:
        print('You need to select at least one storage provider.')
        sys.exit(1)

    accepted = False
    print('\n\n\n')
    while not accepted:
        cromwell_server_url = input('Enter the URL for the Cromwell server, including the port, if any '
                                      '(for example, "https://example.com:8000"):')
        m = re.match('^https?://.*', cromwell_server_url)
        if m and (m.group() == cromwell_server_url):
            params['cromwell_server_url'] = cromwell_server_url
            accepted = True
        else:
            print('Try again-- make sure you have http/https at the front.')


    accepted = False
    print('\n\n\n')
    while not accepted:
        storage_bucket_prefix = input('Enter a prefix for storage buckets that will '
                                      'be created (lowercase letters, numbers, and dashes are accepted): ')
        m = re.match('[a-z0-9-]+', storage_bucket_prefix)
        if m.group() != storage_bucket_prefix:
            print('We enforce stricter guidelines than the storage providers and only '
                  'allow lowercase letters, numbers, and dashes.  Try again.')
        else:
            params['storage_bucket_prefix'] = storage_bucket_prefix
            accepted = True

    accepted = False
    print('\n\n\n')
    while not accepted:
        app_token = input('Enter a series of characters (letters/numbers) that is a multiple of 8. '
                          'This should be relatively long, and allows worker machines to communicate '
                          'with the main machine.  Enter:  ')
        if (len(app_token.encode('utf-8')) % 8)  != 0:
            print('The token needs to be a multiple of 8 in length (when cast as a byte string).  Try again')
        else:
            params['app_token'] = app_token
            accepted = True

    accepted = False
    print('\n\n\n')
    while not accepted:
        app_token_key = input('Enter a series of 8 characters (letters/numbers) to be used for encryptping the token: ')
        if len(app_token_key.encode('utf-8')) != 8:
            print('The key needs to be 8 bytes long.  Try again.')
        else:
            params['app_token_key'] = app_token_key
            accepted = True

    accepted=False
    print('\n\n\n')
    while not accepted:
        use_email = input('Will you be using email notifications? '
                          'You will still need to setup any credentials.  Instructions for Gmail integration '
                          'are provided in the documentation:  ')
        if use_email.lower()[0] == 'y':
            params['email_enabled'] = True
            accepted=True
        elif use_email.lower()[0] == 'n':
            params['email_enabled'] = False
            accepted=True
        else:
            print('Try again.  Please enter y or n.')

    return params


def fill_template(config_dir, params):
    env = Environment(loader=FileSystemLoader(config_dir))
    template = env.get_template('general.template.cfg')
    with open(os.path.join(config_dir, 'general.cfg'), 'w') as outfile:
        outfile.write(template.render(params))

def fill_settings(params):
    pattern = os.path.join(os.environ['APP_ROOT'], '*', 'settings.template.py')
    matches = glob.glob(pattern)
    if len(matches) == 1:
        template_path = matches[0]
        settings_dir = os.path.dirname(template_path)
        env = Environment(loader=FileSystemLoader(settings_dir))
        template = env.get_template(os.path.basename(template_path))
        with open(os.path.join(settings_dir, 'settings.py'), 'w') as outfile:
            outfile.write(template.render(params))
    else:
        print('Found multiple files matching the pattern %s.  This should not be the case' % pattern)
        sys.exit(1)


if __name__ == '__main__':
    config_dir = os.path.join(os.environ['APP_ROOT'], 'config')
    params = take_inputs()
    fill_template(config_dir, params)

    fill_settings(params)
