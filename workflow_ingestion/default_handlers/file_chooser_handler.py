import os

from base.models import Resource

class ResourceDisplay(object):
    '''
    Simple class which aids for simple templating
    on the front end.
    '''
    @staticmethod
    def get_human_readable_size(size):
        '''
        Converts the file size (in bytes)
        to a form like 10.2 MB, 2.1 GB, etc.
        Returns a string
        '''
        suffix = ['kB', 'MB', 'GB', 'TB']
        threshold = 1024
        if size <= threshold:
            return '%d B' % size
        running_size = size
        i = 1
        while( (running_size/threshold) > threshold ):
            running_size /= threshold
            i += 1
        return '%.2f %s' % (running_size/threshold, suffix[i-1])

    def __init__(self, name, size):
        self.name = name
        self.size = size
        self.human_readable_size = self.get_human_readable_size(self.size)

def add_to_context(request, context_dict):
    '''
    This method is called by the view for the workflow.
    Dictates which dynamic content is sent to the front-end
    '''
    user = request.user
    r = Resource.objects.user_resources(user)
    display_resources = []
    for rr in r:
        if rr.is_active:
            display_resources.append(ResourceDisplay(rr.name, rr.size))
    context_dict['user_resources'] = display_resources
