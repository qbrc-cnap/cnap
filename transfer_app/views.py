import base64
import json
import datetime
from Crypto.Cipher import DES
import httplib2

from django.contrib.sites.models import Site
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from django.conf import settings

from rest_framework import generics, permissions, renderers, status
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.exceptions import ParseError
from rest_framework.views import exception_handler, APIView

from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth import get_user_model

from transfer_app.models import Transfer, TransferCoordinator, FailedTransfer
from transfer_app.serializers import TransferSerializer, \
     TransferCoordinatorSerializer, \
     TransferredResourceSerializer

import transfer_app.utils as utils
import base.exceptions as exceptions
import transfer_app.tasks as transfer_tasks
import transfer_app.uploaders as _uploaders
import transfer_app.downloaders as _downloaders

class TransferList(generics.ListAPIView):
    '''
    This only allows a listing.  Creation of Transfer objects
    is handled by a TransferCoordinator.  We cannot explicitly
    create Transfer instances via the API since they would be 
    "untracked"
    '''
    queryset = Transfer.objects.all()
    serializer_class = TransferSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('completed', 'success', 'download')

    def get_queryset(self):
        '''
        This overrides the get_queryset method of rest_framework.generics.GenericAPIView
        This allows us to return only Transfer instances belonging to the user.
        If an admin is requesting, then we return all
        '''
        queryset = super(TransferList, self).get_queryset()
        if not self.request.user.is_staff:
            queryset = Transfer.objects.user_transfers(self.request.user)
        return queryset


class TransferDetail(generics.RetrieveAPIView):
    '''
    Here we allow only retrieval of objects.  We have no reason to edit or destroy
    info about the Transfers
    '''
    queryset = Transfer.objects.all()
    serializer_class = TransferSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self):
        '''
        Custom behavior for object retrieval- admins can get anything
        Regular users can only get objects they own.  
        Instead of the default 403 (which exposes that a particular object
        does exist), return 404 if they are not allowed to access an object.
        '''
        obj = super(TransferDetail, self).get_object()
        if (self.request.user.is_staff) or (obj.originator == self.request.user):
            return obj
        else:
            raise Http404


class UserTransferList(generics.ListAPIView):
    '''
    This lists the Transfer instances for a particular user
    This view is entirely protected-- only accessible by staff
    Since regular users can only see the Resources they own,
    they can just use the "vanilla" listing endpoint
    '''
    serializer_class = TransferSerializer
    permission_classes = (permissions.IsAdminUser,)
    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('completed', 'success', 'download')

    def get_queryset(self):
        user_pk = self.kwargs['user_pk']
        try:
            user = get_user_model().objects.get(pk=user_pk)
            return Transfer.objects.user_transfers(user)
        except ObjectDoesNotExist as ex:
            raise Http404


class TransferredResourceList(generics.ListAPIView):
    '''
    This creates a shortcut API which effectively joins
    a Transfer with the Resource it wraps.  Mainly used to limit
    the number of requests needed for the frontend.  
    '''
    queryset = Transfer.objects.all()
    serializer_class = TransferredResourceSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        queryset = super(TransferredResourceList, self).get_queryset()
        if not self.request.user.is_staff:
            queryset = Transfer.objects.user_transfers(self.request.user)
        return queryset

class BatchList(generics.ListAPIView):
    '''
    This only allows a listing of the TransferCoordinators.  
    Creation of TransferCoordinator objects is handled 
    elsewhere.
    '''
    queryset = TransferCoordinator.objects.all()
    serializer_class = TransferCoordinatorSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('completed',)

    def get_queryset(self):
        '''
        This overrides the get_queryset method of rest_framework.generics.GenericAPIView
        This allows us to return only TransferCoordinator instances belonging to the user.
        If an admin is requesting, then we return all instances
        '''
        queryset = super(BatchList, self).get_queryset()
        if not self.request.user.is_staff:
            queryset = TransferCoordinator.objects.user_transfer_coordinators(self.request.user)
        return queryset


class BatchDetail(generics.RetrieveAPIView):
    '''
    Here we allow only retrieval of objects.  We have no reason to edit or destroy
    TransferCoordinators
    '''
    queryset = TransferCoordinator.objects.all()
    serializer_class = TransferCoordinatorSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self):
        '''
        Custom behavior for object retrieval- admins can get anything
        Regular users can only get objects they own.  
        Instead of the default 403 (which exposes that a particular object
        does exist), return 404 if they are not allowed to access an object.
        '''
        obj = super(BatchDetail, self).get_object()
        obj_owners = list(set([x.resource.owner for x in Transfer.objects.filter(coordinator = obj)]))
        if len(obj_owners) == 1:            
            if (self.request.user.is_staff) or (obj_owners[0] == self.request.user):
                return obj
            else:
                raise Http404
        else:
            raise Http404


class UserBatchList(generics.ListAPIView):
    '''
    This lists the TransferCoordinator instances for a particular user
    This view is entirely protected-- only accessible by staff
    Since regular users can only see the Resources they own,
    they can just use the "vanilla" listing endpoint
    '''
    serializer_class = TransferCoordinatorSerializer
    permission_classes = (permissions.IsAdminUser,)
    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('completed',)

    def get_queryset(self):
        user_pk = self.kwargs['user_pk']
        try:
            user = get_user_model().objects.get(pk=user_pk)
            return TransferCoordinator.objects.user_transfer_coordinators(user)
        except ObjectDoesNotExist as ex:
            raise Http404


class TransferComplete(APIView):

    permission_classes = (permissions.AllowAny,)

    def post(self, request, format=None):    
        data = request.data
        if 'token' in data:
            b64_enc_token = data['token']
            enc_token = base64.decodestring(b64_enc_token.encode('ascii'))
            expected_token = settings.CONFIG_PARAMS['token'] 
            obj=DES.new(settings.CONFIG_PARAMS['enc_key'], DES.MODE_ECB)
            decrypted_token = obj.decrypt(enc_token)
            if decrypted_token == expected_token.encode('ascii'):
                # we can trust the content since it contained the proper token
                try:
                    transfer_pk = data['transfer_pk']
                    success = bool(int(data['success']))
                except KeyError as ex:
                    raise exceptions.RequestError('The request did not have the correct formatting.')  
                try:
                    transfer_obj = Transfer.objects.get(pk=transfer_pk)
                    transfer_obj.completed = True
                    transfer_obj.success = success
                    tz = transfer_obj.start_time.tzinfo
                    now = datetime.datetime.now(tz)
                    duration = now - transfer_obj.start_time
                    transfer_obj.duration = duration
                    transfer_obj.finish_time = now
                    transfer_obj.save()

                    # get the transfer coordinator primary key.
                    tc_pk = transfer_obj.coordinator.pk

                    try:
                        tc = TransferCoordinator.objects.get(pk=tc_pk)
                    except ObjectDoesNotExist as ex:
                        raise exceptions.RequestError('TransferCoordinator with pk=%d did not exist' % tc_pk)

                    if success:
                        if transfer_obj.download:
                            resource = transfer_obj.resource

                            # did they use the last download?  If so, set the Resource inactive
                            if (resource.total_downloads + 1) >= \
                                int(settings.CONFIG_PARAMS['maximum_downloads']):
                                resource.is_active = False                                
                            resource.total_downloads += 1
                            resource.save()
                        else: # upload
                            resource = transfer_obj.resource
                            resource.is_active = True
                            resource.save()
                    else: # failed the transfer process somehow
                        # note this failed transfer:
                        ft = FailedTransfer(
                            was_download = transfer_obj.download,
                            intended_path = transfer_obj.destination,
                            start_time = transfer_obj.start_time,
                            resource_name = transfer_obj.resource.name,
                            coordinator = tc
                        )
                        ft.save()

                        if not transfer_obj.download:
                            # if upload, we need to clean up the Resource since it was previously
                            # saved as a placeholder.  
                            resource = transfer_obj.resource
                            resource.delete()

                    # now check if all the Transfers belonging to this TransferCoordinator are complete:
                    all_transfers = Transfer.objects.filter(coordinator = tc)
                    if all([x.completed for x in all_transfers]):
                        tc.completed = True
                        tc.finish_time = datetime.datetime.now()
                        tc.save()
                        all_originators = list(set([x.originator.email for x in all_transfers]))
                        utils.post_completion(tc, all_originators)
                    return Response({'message': 'thanks'})
                except ObjectDoesNotExist as ex:
                    raise exceptions.RequestError('Transfer with pk=%s did not exist' % transfer_pk)
            else:
                raise Http404
        else:
            raise Http404


class InitDownload(generics.CreateAPIView):
    '''
    This endpoint is where we POST data for the creation of 
    download transfers (e.g. TO dropbox).
    In this case, we already have Resource objects in the database.  
    Users are transferring these known Resources out of our system
    '''

    def post(self, request, *args, **kwargs):
        # Parse the submitted data:
        data = request.data
        try:
            json_str = data['data'] # j is a json-format string
            data = json.loads(json_str)
            resource_pks = data['resource_pks']
            resource_pks = [x for x in resource_pks if x] # remove any None that may have gotten through
            download_destination = data['destination']
        except KeyError as ex:
            raise exceptions.RequestError('''
                Missing required information for initiating transfer.
            ''')

        # Here, we first do a spot-check on the data that was passed, BEFORE we invoke any asynchronous methods.
        # We prepare/massage the necessary data for the upload here, and then pass a simple dictionary to the asynchronous
        # method call.  We do this since it is easiest to pass a simple native dictionary to celery. 

        user_pk = request.user.pk
        try:
            # Depending on which download destination was requested (and which compute environment we are in), grab the proper class:
            downloader_cls = _downloaders.get_downloader(download_destination)

            # Check that the upload data has the required format to work with this uploader implementation:
            download_info, error_messages = downloader_cls.check_format(resource_pks, user_pk)

            if len(error_messages) > 0:
                return Response({'errors': error_messages}, status=409)
            else:
                # stash the download info, since we will be redirecting through an authentication flow
                request.session['download_info'] = download_info 
                request.session['download_destination'] = download_destination
                return Response({'success': True})

        except exceptions.ExceptionWithMessage as ex:
            raise exceptions.RequestError(ex.message)

        except Exception as ex:
            response = exception_handler(ex, None)

        return Response({'message': 'thanks'})


    def get(self, request, *args, **kwargs):
        download_destination = request.session['download_destination']
        downloader_cls = _downloaders.get_downloader(download_destination)
        return downloader_cls.authenticate(request)
        

class InitUpload(generics.CreateAPIView):

    def post(self, request, *args, **kwargs):
        data = request.data
        try:
            upload_source = data['upload_source'] # (dropbox, drive, etc)
            upload_info = data['upload_info']
            upload_info = json.loads(upload_info)
            #raise Exception('temp!');
        except KeyError as ex:
            raise exceptions.RequestError('The request JSON body did not contain the required data (%s).' % ex)

        # Here, we first do a spot-check on the data that was passed, BEFORE we invoke any asynchronous methods.
        # We prepare/massage the necessary data for the upload here, and then pass a simple dictionary to the asynchronous
        # method call.  We do this since it is easiest to pass a simple native dictionary to celery. 

        user_pk = request.user.pk

        try:
            # Depending on which upload method was requested (and which compute environment we are in), grab the proper class:
            uploader_cls = _uploaders.get_uploader(upload_source)

            # Check that the upload data has the required format to work with this uploader implementation:
            upload_info, error_messages = uploader_cls.check_format(upload_info, user_pk)
            if len(error_messages) > 0:
                return Response({'errors': error_messages})
            elif len(upload_info) > 0:
                # call async method:
                transfer_tasks.upload.delay(upload_info, upload_source)
                return Response({})
            else: # no errors, but also nothing to do...
                return Response({})
        except exceptions.ExceptionWithMessage as ex:
            raise exceptions.RequestError(ex.message)

        except Exception as ex:
            print('Exception: %s' % ex)
            response = exception_handler(ex, None)
            return response


