import subprocess as sp
import os
import uuid

from django.conf import settings

def clone_repository(url):
    '''
    This clones the repository and parses the git log for the commit hash
    Returns a tuple of the destination dir and the commit hash
    '''
    # clone the repo
    uuid_str = str(uuid.uuid4())
    dest = os.path.join(settings.CLONE_STAGING, uuid_str)
    clone_cmd = 'git clone %s %s' % (url, dest)
    clone_cmd = clone_cmd.split(' ')
    p = sp.Popen(clone_cmd, stdout=sp.PIPE, stderr=sp.STDOUT)
    stdout, stderr = p.communicate()

    # if there was a problem, return a tuple of Nones:
    if p.returncode != 0:
        print('Problem when cloning the repository from %s' % url)
        print(stderr)
        print(stdout)
        return (None, None)

    # get the commit ID
    cmd = 'git --git-dir %s/.git show -s --format=%%H' % dest
    cmd = cmd.split(' ')
    p = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.STDOUT)
    stdout, stderr = p.communicate()
    if p.returncode != 0:
        print('Problem with querying the commit hash from the git repo at %s' % dest)
        print(stderr)
        print(stdout)
        return (None, None)
    else:
        commit_hash = stdout.strip().decode('utf-8')
        return (dest, commit_hash)
