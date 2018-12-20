from django.urls import re_path
from rest_framework.urlpatterns import format_suffix_patterns

from transfer_app import views
from transfer_app.downloaders import *

from transfer_app import live_tests
'''
For all the endpoints given here, consult the specific view for
details about the actual methods they support, and what sorts of 
info they provide back
'''
urlpatterns = [

    # endpoints related to querying Transfers:
    re_path(r'^$', views.TransferList.as_view(), name='transfer-list'),
    re_path(r'^upload/init/$', views.InitUpload.as_view(), name='upload-transfer-initiation'),
    re_path(r'^download/init/$', views.InitDownload.as_view(), name='download-transfer-initiation'),
    re_path(r'^(?P<pk>[0-9]+)/$', views.TransferDetail.as_view(), name='transfer-detail'),
    re_path(r'^user/(?P<user_pk>[0-9]+)/$', views.UserTransferList.as_view(), name='user-transfer-list'),
    re_path(r'^transferred-resources/$', views.TransferredResourceList.as_view(), name='transferred-resource-list'),

    # endpoints related to querying TransferCoordinators, so we can group the Transfer instances
    re_path(r'^batch/$', views.BatchList.as_view(), name='batch-list'),
    re_path(r'^batch/(?P<pk>[0-9]+)/$', views.BatchDetail.as_view(), name='batch-detail'),
    re_path(r'^batch/user/(?P<user_pk>[0-9]+)/$', views.UserBatchList.as_view(), name='user-batch-list'),
]
urlpatterns = format_suffix_patterns(urlpatterns)

urlpatterns.extend([
    # endpoints for communicating from worker machines:
    re_path(r'^complete/$', views.TransferComplete.as_view(), name='transfer-complete'),

    # endpoints for callbacks:
    re_path(r'^dropbox/callback/$', DropboxDownloader.finish_authentication_and_start_download, name='dropbox_token_callback'),
    re_path(r'^drive/callback/$', DriveDownloader.finish_authentication_and_start_download, name='drive_token_callback'),

    re_path(r'^test/$', live_tests.live_test),
    re_path(r'^test/dropbox/$', live_tests.dropbox_code_exchange_test, name='live_oauth_test_dropbox'),
    re_path(r'^test/dropbox-callback/$', live_tests.dropbox_token_exchange_test, name='live_oauth_test_dropbox_callback'),
    re_path(r'^test/drive/$', live_tests.drive_code_exchange_test, name='live_oauth_test_drive'),
    re_path(r'^test/drive-callback/$', live_tests.drive_token_exchange_test, name='live_oauth_test_drive_callback'),

    re_path(r'^test/transfer-test/dropbox/$', live_tests.dropbox_code_exchange_transfer_test, name='live_transfer_test_dropbox'),
    re_path(r'^test/transfer-test/dropbox-callback/$', live_tests.dropbox_token_exchange_transfer_test, name='live_transfer_test_dropbox_callback'),
    re_path(r'^test/transfer-test/drive/$', live_tests.drive_code_exchange_transfer_test, name='live_transfer_test_drive'),
    re_path(r'^test/transfer-test/drive-callback/$', live_tests.drive_token_exchange_transfer_test, name='live_transfer_test_drive_callback')
])
