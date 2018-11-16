#! /usr/bin/python3

import os
import sys
import io
import subprocess
import argparse
import datetime
import logging
from Crypto.Cipher import DES
import base64
import requests
import google
from google.cloud import storage
from apiclient.discovery import build


WORKING_DIR = '/workspace'
HOSTNAME_REQUEST_URL = 'http://metadata/computeMetadata/v1/instance/hostname'
GOOGLE_BUCKET_PREFIX = 'gs://'

def create_logger():
	"""
	Creates a logfile
	"""
	timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
	logfile = os.path.join(WORKING_DIR, str(timestamp)+".dropbox_transfer.log")
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


def send_to_bucket(local_filepath, params):
	'''
	Uploads the local file to the bucket
	'''
	full_destination_w_prefix = params['destination']
	full_destination = full_destination_w_prefix[len(GOOGLE_BUCKET_PREFIX):]
	contents = full_destination.split('/')
	bucket_name = contents[0]
	object_name = '/'.join(contents[1:])

	storage_client = storage.Client()
	# trying to get an existing bucket.  If raises exception, means bucket did not exist (or similar)
	try:
		destination_bucket = storage_client.get_bucket(bucket_name)
	except (google.api_core.exceptions.NotFound, google.api_core.exceptions.BadRequest) as ex:

		# try to create the bucket:
		try:
			destination_bucket = storage_client.create_bucket(bucket_name)
		except google.api_core.exceptions.BadRequest as ex2:
			raise Exception('Could not find or create bucket.  Error was ' % ex2)
	try:
		destination_blob = destination_bucket.blob(object_name)
		destination_blob.upload_from_filename(local_filepath)
	except Exception as ex:
		raise Exception('Could not create or upload the blob with name %s' % object_name)


def download_to_disk(params):
	'''
	local_filepath is the path on the VM/container of the file that
	will be downloaded.
	'''
	source_link = params['resource_path']
	local_path = os.path.join(WORKING_DIR, 'download')
	cmd = 'wget -q -O %s "%s"' % (local_path, source_link)
	p = subprocess.Popen(cmd, shell=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
	stdout, stderr = p.communicate()
	if p.returncode != 0:
		print('Failed on transfering %s' % source_link.split('/')[-1])
		print(stdout)
		print('--'*10)
		print(stderr)
	else:
		return local_path


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
	parser.add_argument("-destination", help="The bucket/object where the upload will be stored.  Include the gs:// prefix", dest='destination', required=True)
	parser.add_argument("-proj", help="Google project ID", dest='google_project_id', required=True)
	parser.add_argument("-zone", help="Google project zone", dest='google_zone', required=True)
	args = parser.parse_args()
	params = {}
	params['token'] = args.token
	params['enc_key'] =  args.enc_key
	params['transfer_pk'] = args.transfer_pk
	params['callback_url'] = args.callback_url
	params['resource_path'] = args.resource_path
	params['destination'] = args.destination
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
		send_to_bucket(local_filepath, params)
		notify_master(params)
		kill_instance(params)
	except Exception as ex:
		logging.error('Caught some unexpected exception.')
		logging.error(str(type(ex)))
		logging.error(ex)
		notify_master(params, error=True)
