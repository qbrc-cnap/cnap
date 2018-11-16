from transfer_app.launchers import GoogleLauncher, AWSLauncher

class GoogleBase(object):
    launcher_cls = GoogleLauncher
    config_keys = ['google',]

class AWSBase(object):
    launcher_cls = AWSLauncher
    config_keys = ['aws',]
