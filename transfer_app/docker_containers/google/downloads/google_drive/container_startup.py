#! /usr/bin/python3

import os
import sys
import argparse
import time
import random
import datetime
import logging
from Crypto.Cipher import DES
import base64
import requests
from google.cloud import storage
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import google.oauth2.credentials

WORKING_DIR = '/workspace'
HOSTNAME_REQUEST_URL = 'http://metadata/computeMetadata/v1/instance/hostname'
GOOGLE_BUCKET_PREFIX = 'gs://'
MAX_FAILS = 10
BACKOFF_CONST = 1e-4 # for exponential backoff.  See function

def create_logger():
	"""
	Creates a logfile
	"""
	timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
	logfile = os.path.join(WORKING_DIR, str(timestamp)+".drive_transfer.log")
	print('Create logfile at %s' % logfile)
	logging.basicConfig(filename=logfile, level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s")
	return logfile

def notify_master(params, error=False):
	'''
	This calls back to the head machine to let it know the work is finished.
	'''
	logging.info('Notifying the master that this job has completed')

	# the payload dictinary:
	d = {}

	# prepare the token which identifies the VM as a 'known' sender
	token = params['token']
	obj=DES.new(params['enc_key'], DES.MODE_ECB)
	enc_token = obj.encrypt(token)
	b64_str = base64.encodestring(enc_token)
	d['token'] = b64_str

	# Other required params to return:
	d['transfer_pk'] = params['transfer_pk']
	d['success'] = 0 if error else 1
	base_url = params['callback_url']
	response = requests.post(base_url, data=d)
	logging.info('Status code: %s' % response.status_code)
	logging.info('Response text: %s' % response.text)


def download_to_disk(params):
	'''
	Downloads the file from the bucket to the local disk.
	'''
	src = params['resource_path']
	src_without_prefix = src[len(GOOGLE_BUCKET_PREFIX):] # remove the prefix
	contents = src_without_prefix.split('/')
	bucket_name = contents[0]
	object_name = '/'.join(contents[1:])
	basename = os.path.basename(object_name)
	local_path = os.path.join(WORKING_DIR, basename)

	storage_client = storage.Client()
	source_bucket = storage_client.get_bucket(bucket_name)
	source_blob = source_bucket.blob(object_name)
	source_blob.download_to_filename(local_path)
	return local_path

def make_request(drive_service, name, upload):
	'''
	Create the request to google api.  Pulled out here
	in case of errors in repeated requests needed.
	'''
	return drive_service.files().create(
		body={'name': name},
		media_body=upload
	)


def backoff(fail_num):
	if fail_num == 0:
		t = BACKOFF_CONST*random.random()
	else:
		f = 2**fail_num
		t = BACKOFF_CONST*random.randint(1,f)
	time.sleep(t)
	return


def send_to_drive(local_filepath, params):
	'''
	local_filepath is the path on the VM/container of the file that
	was already downloaded.
	'''
	access_token = params['access_token']
	credentials = google.oauth2.credentials.Credentials(access_token)
	drive_service = build('drive', 'v3', credentials=credentials)
	upload = MediaFileUpload(local_filepath, resumable=True)
	request = make_request(drive_service, 
		os.path.basename(local_filepath), 
		upload
	)
	response = None
	fails = 0
	while response is None:
		try:
			status, response = request.next_chunk()
		except apiclient.errors.HttpError as e:
			if e.resp.status in [404]:
				# Start the upload all over again.
				request = make_request(drive_service, 
					os.path.basename(local_filepath), 
					upload 
				)
			elif e.resp.status in [500, 502, 503, 504]:
				# Call next_chunk() again, but use an exponential backoff for repeated errors.
				backoff(fails)
				if fails > MAX_FAILS:
					raise Exception('Too many failures')
				else:
					fails += 1
			else:
				# Do not retry. Raise exception
				raise e
		if status:
			logging.info('Uploaded %d%%.' % int(status.progress() * 100))


def kill_instance(params):
	'''
	Removes the virtual machine
	'''
	headers = {'Metadata-Flavor':'Google'}
	response = requests.get(HOSTNAME_REQUEST_URL, headers=headers)
	content = response.content.decode('utf-8')
	instance_name = content.split('.')[0]
	compute = build('compute', 'v1')
	compute.instances().delete(project=params['google_project_id'],
		zone=params['google_zone'], 
	instance=instance_name).execute()


def parse_args():
	parser = argparse.ArgumentParser()
	parser.add_argument("-token", help="A token for identifying the container with the main application", dest='token', required=True)
	parser.add_argument("-key", help="An encryption key for identifying the container with the main application", dest='enc_key', required=True)
	parser.add_argument("-pk", help="The primary key of the transfer", dest='transfer_pk', required=True)
	parser.add_argument("-url", help="The callback URL for communicating with the main application", dest='callback_url', required=True)
	parser.add_argument("-path", help="The source of the file that is being downloaded", dest='resource_path', required=True)
	parser.add_argument("-access_token", help="The access token for Drive API", dest='access_token', required=True)
	parser.add_argument("-proj", help="Google project ID", dest='google_project_id', required=True)
	parser.add_argument("-zone", help="Google project zone", dest='google_zone', required=True)
	args = parser.parse_args()
	params = {}
	params['token'] = args.token
	params['enc_key'] =  args.enc_key
	params['transfer_pk'] = args.transfer_pk
	params['callback_url'] = args.callback_url
	params['resource_path'] = args.resource_path
	params['access_token'] = args.access_token
	params['google_project_id'] = args.google_project_id
	params['google_zone'] = args.google_zone
	return params


if __name__ == '__main__':
	try:
		params = parse_args()
		os.mkdir(WORKING_DIR)
		logfile = create_logger()
		params['logfile'] = logfile
		local_filepath = download_to_disk(params)
		send_to_drive(local_filepath, params)
		notify_master(params)
		kill_instance(params)
	except Exception as ex:
		logging.error('Caught some unexpected exception.')
		logging.error(str(type(ex)))
		logging.error(ex)
		notify_master(params, error=True)
