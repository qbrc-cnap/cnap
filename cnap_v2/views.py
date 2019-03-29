from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.conf import settings

from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.decorators import api_view


@login_required
def index(request):
    context = {}
    providers = {'google_drive': settings.GOOGLE_DRIVE, 'dropbox':settings.DROPBOX}
    context['providers'] = providers
    context['dropbox_enabled'] = settings.CONFIG_PARAMS['dropbox_enabled']
    context['drive_enabled'] = settings.CONFIG_PARAMS['drive_enabled']
    context['dropbox_client_id'] = settings.CONFIG_PARAMS['dropbox_client_id']
    return render(request, 'index.html', context)


@api_view(['GET'])
def api_root(request, format=None):
    return Response({
        'users': reverse('user-list', request=request, format=format),
        'resources': reverse('resource-list', request=request, format=format),
        'transfers': reverse('transfer-list', request=request, format=format)
    })
