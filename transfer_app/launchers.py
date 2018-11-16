import subprocess as sb

from django.conf import settings


class Launcher(object):
    def __init__(self):
        pass

class GoogleLauncher(Launcher):   
    def go(self, cmd):
        print('Launch: %s' % cmd)
        p = sb.Popen(cmd, shell=True, stdout=sb.PIPE, stderr=sb.STDOUT)
        stdout, stderr = p.communicate()
        if p.returncode != 0:
            print('There was a problem:')
            print('stdout: %s' % stdout)
            print('stderr: %s' % stderr)


class AWSLauncher(Launcher):
    pass
