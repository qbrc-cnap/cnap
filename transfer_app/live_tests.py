import unittest.mock as mock

from django.test import TestCase
from django.conf import settings
from django.urls import reverse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required

import transfer_app.downloaders as downloaders
from base.models import Resource


@login_required
def live_test(request):
    return render(request, 'transfer_app/live_test.html', {})

@login_required
def dropbox_code_exchange_test(request):
    test = LiveOauthTest()
    return test.dropbox_code_exchange_test(request)

def dropbox_token_exchange_test(request):
    test = LiveOauthTest()
    return test.dropbox_token_exchange_test(request)

@login_required
def drive_code_exchange_test(request):
    test = LiveOauthTest()
    return test.drive_code_exchange_test(request)

def drive_token_exchange_test(request):
    test = LiveOauthTest()
    return test.drive_token_exchange_test(request)

@login_required
def dropbox_code_exchange_transfer_test(request):
    test = LiveTransferTest()
    return test.dropbox_code_exchange_test(request)

def dropbox_token_exchange_transfer_test(request):
    test = LiveTransferTest()
    return test.dropbox_token_exchange_test(request)

@login_required
def drive_code_exchange_transfer_test(request):
    test = LiveTransferTest()
    return test.drive_code_exchange_test(request)

def drive_token_exchange_transfer_test(request):
    test = LiveTransferTest()
    return test.drive_token_exchange_test(request)


class LiveOauthTest(TestCase):

    def dropbox_code_exchange_test(self, request):
        downloader_cls = downloaders.get_downloader(settings.DROPBOX)
        request.session['download_info'] = []
        request.session['download_destination'] = settings.DROPBOX
        callback_url = reverse(settings.LIVE_TEST_CONFIG_PARAMS['dropbox_oauth_callback'])
        with mock.patch.dict(downloaders.settings.CONFIG_PARAMS, {'dropbox_callback':callback_url}):
            return downloader_cls.authenticate(request)

    @mock.patch('transfer_app.downloaders.transfer_tasks')
    def dropbox_token_exchange_test(self, request, mock_tasks):
        downloader_cls = downloaders.get_downloader(settings.DROPBOX)
        callback_url = reverse(settings.LIVE_TEST_CONFIG_PARAMS['dropbox_oauth_callback'])
        with mock.patch.dict(downloaders.settings.CONFIG_PARAMS, {'dropbox_callback': callback_url}):
            response = downloader_cls.finish_authentication_and_start_download(request)
            self.assertEqual(response.status_code, 200)
            return response

    def drive_code_exchange_test(self, request):
        downloader_cls = downloaders.get_downloader(settings.GOOGLE_DRIVE)
        request.session['download_info'] = []
        request.session['download_destination'] = settings.DROPBOX
        callback_url = reverse(settings.LIVE_TEST_CONFIG_PARAMS['drive_oauth_callback'])
        with mock.patch.dict(downloaders.settings.CONFIG_PARAMS, {'drive_callback': callback_url}):
            return downloader_cls.authenticate(request)

    @mock.patch('transfer_app.downloaders.transfer_tasks')
    def drive_token_exchange_test(self, request, mock_tasks):
        downloader_cls = downloaders.get_downloader(settings.GOOGLE_DRIVE)
        callback_url = reverse(settings.LIVE_TEST_CONFIG_PARAMS['drive_oauth_callback'])
        with mock.patch.dict(downloaders.settings.CONFIG_PARAMS, {'drive_callback': callback_url}):
            response = downloader_cls.finish_authentication_and_start_download(request)
            self.assertEqual(response.status_code, 200)
            return response


class LiveTransferTest(TestCase):

    def dropbox_code_exchange_test(self, request):
        user = request.user

        # ensure we have the correct user for the test:
        if user.email == settings.LIVE_TEST_CONFIG_PARAMS['test_email']:

            # need to ensure we have the Resource already in the database:
            try:
                r = Resource.objects.get(path=settings.LIVE_TEST_CONFIG_PARAMS['file_to_transfer'],
                    size = settings.LIVE_TEST_CONFIG_PARAMS['file_size_in_bytes'],
                    owner = user
                )
                download_info = [{
                    'resource_pk':r.pk,
                    'originator':user.pk,
                    'destination':settings.DROPBOX
                },]
                downloader_cls = downloaders.get_downloader(settings.DROPBOX)
                request.session['download_info'] = download_info
                request.session['download_destination'] = settings.DROPBOX
                callback_url = reverse(settings.LIVE_TEST_CONFIG_PARAMS['dropbox_transfer_callback'])
                with mock.patch.dict(downloaders.settings.CONFIG_PARAMS, {'dropbox_callback': callback_url}):
                    return downloader_cls.authenticate(request)
            except Exception as ex:
                print('Could not find!')
                return HttpResponse('Could not find the test resource')


    def dropbox_token_exchange_test(self, request):
        downloader_cls = downloaders.get_downloader(settings.DROPBOX)
        callback_url = reverse(settings.LIVE_TEST_CONFIG_PARAMS['dropbox_transfer_callback'])
        with mock.patch.dict(downloaders.settings.CONFIG_PARAMS, {'dropbox_callback': callback_url}):
            response = downloader_cls.finish_authentication_and_start_download(request)
            self.assertEqual(response.status_code, 200)
            return response

    def drive_code_exchange_test(self, request):
        user = request.user

        # ensure we have the correct user for the test:
        if user.email == settings.LIVE_TEST_CONFIG_PARAMS['test_email']:

            # need to ensure we have the Resource already in the database:
            try:
                r = Resource.objects.get(path=settings.LIVE_TEST_CONFIG_PARAMS['file_to_transfer'],
                    size = settings.LIVE_TEST_CONFIG_PARAMS['file_size_in_bytes'],
                    owner = user
                )
                download_info = [{
                    'resource_pk':r.pk,
                    'originator':user.pk,
                    'destination':settings.GOOGLE_DRIVE
                },]
                downloader_cls = downloaders.get_downloader(settings.GOOGLE_DRIVE)
                request.session['download_info'] = download_info
                request.session['download_destination'] = settings.GOOGLE_DRIVE
                callback_url = reverse(settings.LIVE_TEST_CONFIG_PARAMS['drive_transfer_callback'])
                with mock.patch.dict(downloaders.settings.CONFIG_PARAMS, {'drive_callback': callback_url}):
                    return downloader_cls.authenticate(request)
            except Exception as ex:
                print('Could not find!')
                return HttpResponse('Could not find the test resource')


    def drive_token_exchange_test(self, request):
        downloader_cls = downloaders.get_downloader(settings.GOOGLE_DRIVE)
        callback_url = reverse(settings.LIVE_TEST_CONFIG_PARAMS['drive_transfer_callback'])
        with mock.patch.dict(downloaders.settings.CONFIG_PARAMS, {'drive_callback': callback_url}):
            response = downloader_cls.finish_authentication_and_start_download(request)
            self.assertEqual(response.status_code, 200)
            return response
