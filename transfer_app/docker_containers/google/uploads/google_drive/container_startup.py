#! /usr/bin/python3

import os
import io
import subprocess
import argparse
import datetime
from Crypto.Cipher import DES
import base64
import requests
import google
from google.cloud import storage, logging
from apiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.oauth2.credentials

WORKING_DIR = '/workspace'
HOSTNAME_REQUEST_URL = 'http://metadata/computeMetadata/v1/instance/hostname'
GOOGLE_BUCKET_PREFIX = 'gs://'


def create_logger():
	"""
	Creates a log in Stackdriver
	"""
	instance_name = get_hostname()
	logname = '%s.log' % instance_name
	logging_client = logging.Client()
	logger = logging_client.logger(logname)
	return logger


def notify_master(params, logger, error=False):
	'''
	This calls back to the head machine to let it know the work is finished.
	'''
	logger.log_text('Notifying the master that this job has completed')

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
	logger.log_text('Status code: %s' % response.status_code)
	logger.log_text('Response text: %s' % response.text)


def send_to_bucket(local_filepath, params, logger):
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
		logger.log_text('See if bucket at %s exists' % bucket_name)
		destination_bucket = storage_client.get_bucket(bucket_name)
	except (google.api_core.exceptions.BadRequest, google.api_core.exceptions.NotFound) as ex:
		logger.log_text('Bucket did not exist.  Creating now...')
		# try to create the bucket:
		try:
			destination_bucket = storage_client.create_bucket(bucket_name)
		except google.api_core.exceptions.BadRequest as ex2:
			logger.log_text('Still could not create the bucket.  Error was %s' % ex2)
			raise Exception('Could not find or create bucket.  Error was ' % ex2)
	try:
		logger.log_text('Upload %s to %s' % (local_filepath, object_name))
		destination_blob = destination_bucket.blob(object_name)
		destination_blob.upload_from_filename(local_filepath)
		logger.log_text('Successful upload to bucket')
	except Exception as ex:
		logger.log_text('Error with upload process.')
		raise Exception('Could not create or upload the blob with name %s' % object_name)

	# calculate the hash in storage:
	storage_client = build('storage', 'v1')
	try:
		response = storage_client.objects().list(bucket=bucket_name, prefix=object_name).execute()
		object_hash = response['items'][0]['md5Hash']
		logger.log_text('Hash from within bucket: %s' % object_hash)
	except:
		logger.log_text('Error with querying hash in the bucket.')
		object_hash = None
	return object_hash


def download_to_disk(params, logger):
	'''
	local_filepath is the path on the VM/container of the file that
	will be downloaded.
	'''
	local_path = os.path.join(WORKING_DIR, 'download')
	access_token = params['access_token']
	credentials = google.oauth2.credentials.Credentials(access_token)
	drive_service = build('drive', 'v3', credentials=credentials)

	request = drive_service.files().get_media(fileId=params['file_id'])
	fh = io.FileIO(local_path, 'wb')
	downloader = MediaIoBaseDownload(fh, request)
	done = False
	while done is False:
		status, done = downloader.next_chunk()
		logger.log_text("Download %d%%." % int(status.progress() * 100))

	logger.log_text('Download completed.')
	return local_path


def get_local_hash(local_path, logger):
	'''
	Given the local path, uses gsutil to calculate the hash and returns that
	If the hash fails, just continue, returning None
	'''
	cmd = 'gsutil hash -m %s | grep md5' % local_path
	p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	stdout,stderr = p.communicate()
	if p.returncode != 0:
		logger.log_text('Calculating local hash did not succeed.')
		h = None
	else:
		s = stdout.decode('utf-8')
		h = s.strip().split('\t')[-1]
		logger.log_text('Local hash: %s' % h)
	return h


def get_hostname():
	headers = {'Metadata-Flavor':'Google'}
	response = requests.get(HOSTNAME_REQUEST_URL, headers=headers)
	content = response.content.decode('utf-8')
	instance_name = content.split('.')[0]
	return instance_name


def kill_instance(params):
	'''
	Removes the virtual machine
	'''
	instance_name = get_hostname()
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
	parser.add_argument("-file_id", help="The unique file ID obtained from Google Drive.", dest='file_id', required=True)
	parser.add_argument("-drive_token", help="The OAuth2 token for Google Drive", dest='access_token', required=True)
	parser.add_argument("-destination", help="The bucket/object where the upload will be stored.  Include the gs:// prefix", dest='destination', required=True)
	parser.add_argument("-proj", help="Google project ID", dest='google_project_id', required=True)
	parser.add_argument("-zone", help="Google project zone", dest='google_zone', required=True)
	args = parser.parse_args()
	params = {}
	params['token'] = args.token
	params['enc_key'] =  args.enc_key
	params['transfer_pk'] = args.transfer_pk
	params['callback_url'] = args.callback_url
	params['file_id'] = args.file_id
	params['access_token'] = args.access_token
	params['destination'] = args.destination
	params['google_project_id'] = args.google_project_id
	params['google_zone'] = args.google_zone
	return params


if __name__ == '__main__':
	try:
		params = parse_args()
		os.mkdir(WORKING_DIR)
		logger = create_logger()
		local_filepath = download_to_disk(params, logger)
		local_hash = get_local_hash(local_filepath, logger)
		hash_in_bucket = send_to_bucket(local_filepath, params, logger)
		if local_hash and hash_in_bucket:
			# if both hashes were successfully acquired, compare
			if local_hash == hash_in_bucket:
				notify_master(params, logger)
			else:
				# we were able to get both hashes and they do NOT match, so error
				logger.log_text('Hashes did not match!')
				notify_master(params, logger, error=True)
		else:
			# missing one of the hashes, so just continue on as if no error
			notify_master(params, logger)

	except Exception as ex:
		logger.log_text('Caught some unexpected exception.')
		logger.log_text(str(type(ex)))
		logger.log_text(str(ex))
		notify_master(params, logger, error=True)
	
	kill_instance(params)
