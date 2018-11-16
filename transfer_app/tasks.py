from celery.decorators import task

from transfer_app import uploaders, downloaders

@task(name='upload')
def upload(upload_info, upload_source):
    '''
    upload_info is a list, with each entry a dictionary.
    Each of those dictionaries has keys which are specific to the upload source
    '''
    uploader_cls = uploaders.get_uploader(upload_source)
    uploader = uploader_cls(upload_info)
    uploader.upload()

@task(name='download')
def download(download_info, download_destination):
    '''
    download_info is a list, with each entry a dictionary.
    Each of those dictionaries has keys which are specific to the upload source
    '''
    downloader_cls = downloaders.get_downloader(download_destination)
    downloader = downloader_cls(download_info)
    downloader.download()
