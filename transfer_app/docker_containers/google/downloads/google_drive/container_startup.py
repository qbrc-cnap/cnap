#! /usr/bin/python3

import os
import argparse
import time
import random
import datetime
from Crypto.Cipher import DES
import base64
import requests
import subprocess as sp
import googleapiclient
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import google.oauth2.credentials
from google.cloud import logging


MOUNT_DIR = '/gcs_mount'
HOSTNAME_REQUEST_URL = 'http://metadata/computeMetadata/v1/instance/hostname'
GOOGLE_BUCKET_PREFIX = 'gs://'
MAX_FAILS = 10
BACKOFF_CONST = 1e-4 # for exponential backoff.  See function



def fuse_mount(bucketname, logger):
	'''
	Mounts the bucket to MOUNT_DIR
	'''
	cmd = 'gcsfuse %s %s' % (bucketname, MOUNT_DIR)
	logger.log_text('Mount bucket with: %s' % cmd) 
	p = sp.Popen(cmd, shell=True, stdout=sp.PIPE, stderr=sp.STDOUT)
	stdout, stderr = p.communicate()
	if p.returncode != 0:
		logger.log_text('There was a problem with running the following: %s' % cmd)
		logger.log_text('stdout: %s' % stdout)
		logger.log_text('stderr: %s' % stderr)
		raise Exception('gcsfuse mount failed.')
	else:
		logger.log_text('Successfully mounted bucket.')


def unmount_fuse(logger):
	'''
	UNmounts the bucket mounted at MOUNT_DIR
	'''
	cmd = 'fusermount -u %s ' % MOUNT_DIR
	logger.log_text('UNmount bucket with: %s' % cmd) 
	p = sp.Popen(cmd, shell=True, stdout=sp.PIPE, stderr=sp.STDOUT)
	stdout, stderr = p.communicate()
	if p.returncode != 0:
		logger.log_text('There was a problem with running the following: %s' % cmd)
		logger.log_text('stdout: %s' % stdout)
		logger.log_text('stderr: %s' % stderr)
		raise Exception('gcsfuse unmount failed.')
	else:
		logger.log_text('Successfully unmounted the temporary bucket.')


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


def get_hostname():
	headers = {'Metadata-Flavor':'Google'}
	response = requests.get(HOSTNAME_REQUEST_URL, headers=headers)
	content = response.content.decode('utf-8')
	instance_name = content.split('.')[0]
	return instance_name
	

def make_request(drive_service, name, upload):
	'''
	Create the request to google api.  Pulled out here
	in case of errors in repeated requests needed.
	'''
	return drive_service.files().create(
		body={'name': name},
		media_body=upload
	)


def backoff(fail_num, logger):
	logger.log_text('Fail number %d' % fail_num)
	if fail_num == 0:
		t = BACKOFF_CONST*random.random()
	else:
		f = 2**fail_num
		t = BACKOFF_CONST*random.randint(1,f)
	logger.log_text('Sleep for %d' % t)
	time.sleep(t)
	logger.log_text('Done sleeping.  Try request again.')
	return


def send_to_drive(local_filepath, params, logger):
	'''
	local_filepath is the path on the VM/container of the file that
	was already downloaded.
	'''
	access_token = params['access_token']
	credentials = google.oauth2.credentials.Credentials(access_token)
	logger.log_text('About to build Google Drive service')
	drive_service = build('drive', 'v3', credentials=credentials)
	logger.log_text('Drive service built.  Instantiate upload.')
	upload = MediaFileUpload(local_filepath, resumable=True)
	logger.log_text('Make initial request to upload %s to Drive' % local_filepath)

	request = make_request(drive_service, 
		os.path.basename(local_filepath), 
		upload
	)
	response = None
	consecutive_fails = 0
	chunk_number = 0
	while response is None:
		try:
			logger.log_text('Prior to sending chunk %d to Drive' % chunk_number)
			status, response = request.next_chunk()
			logger.log_text('Completed sending chunk %d to Drive' % chunk_number)
			consecutive_fails = 0 # reset the fail counter since a chunk successfully transferred
			chunk_number += 1
		except googleapiclient.errors.HttpError as e:
			logger.log_text('Caught an API exception!')
			if e.resp.status in [404]:
				# Start the upload all over again.
				logger.log_text('The response was a 404.  Restart everything.')
				request = make_request(drive_service, 
					os.path.basename(local_filepath), 
					upload 
				)
			elif e.resp.status in [500, 502, 503, 504]:
				# Call next_chunk() again, but use an exponential backoff for repeated errors.
				logger.log_text('The response was 5xx.  Try a backoff to see if the problem resolves.')
				backoff(consecutive_fails, logger)
				if consecutive_fails > MAX_FAILS:
					logger.log_text('Too many consecutive failures happened.  Bailing.')
					raise Exception('Too many failures')
				else:
					consecutive_fails += 1
			else:
				# Do not retry. Raise exception
				logger.log_text('The error status was not 404 or 5xx.  Bailing since this was an unexpected exception.')
				raise e
		if status:
			logger.log_text('Uploaded %d%%.' % int(status.progress() * 100))


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

		# create the location where we mount the bucket:
		os.mkdir(MOUNT_DIR)

		# instantiate the stackdriver logger:
		logger = create_logger()

		split_resource_path_no_prefix = params['resource_path'][len(GOOGLE_BUCKET_PREFIX):].split('/')
		bucketname = split_resource_path_no_prefix[0]
		object_name = '/'.join(split_resource_path_no_prefix[1:])

		# now mount that bucket
		fuse_mount(bucketname, logger)

		# get the location of the mounted file and send it off.
		local_filepath = os.path.join(MOUNT_DIR, object_name)
		send_to_drive(local_filepath, params, logger)

		# unmount the bucket and cleanup:
		unmount_fuse(logger)

		# notify head node and kill the instance
		notify_master(params, logger)
		kill_instance(params)

	except Exception as ex:
		logger.log_text('ERROR: Caught some unexpected exception.')
		logger.log_text(str(type(ex)))
		logger.log_text(ex)
		notify_master(params, logger, error=True)
