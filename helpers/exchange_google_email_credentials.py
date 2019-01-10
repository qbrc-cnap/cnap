import json
import os
import argparse

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://mail.google.com/']

def create_credential_file(arg_dict):
    fin = arg_dict['input_json']
    flow = InstalledAppFlow.from_client_secrets_file(fin, SCOPES)
    creds = flow.run_console()
    d = {}
    d['refresh_token'] = creds.refresh_token
    d['token'] = creds.token
    d['token_uri'] = creds.token_uri
    d['client_id'] = creds.client_id
    d['client_secret'] = creds.client_secret
    d['scopes'] = creds.scopes
    fout = open(arg_dict['output_json'], 'w')
    json.dump(d, fout)

def parse_commandline():
    '''
    Commandline arguments/options are specified here.
    
    Returns a dictionary.
    '''
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-i',
        '--input',
        required=True,
        dest='input_json',
        help='Path to an EXISTING credentials JSON file (the one downloaded from Google Console).'
    )
    parser.add_argument(
        '-o',
        '--output',
        required=True,
        dest='output_json',
        help='Path to a destination credentials JSON file (which is usable by Google SDK).'
    )
    args = parser.parse_args()
    return vars(args)

if __name__ == '__main__':
    d = parse_commandline()
    create_credential_file(d)
