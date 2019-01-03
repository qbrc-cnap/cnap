from rest_framework import generics, permissions, status
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from django.http import Http404
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist

import base.utils as utils
from base.models import Resource, Organization
from base.serializers import ResourceSerializer, OrganizationSerializer


class OrganizationList(generics.ListCreateAPIView):
    '''
    This lists or creates the Organizations 
    '''
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = (permissions.IsAdminUser,)


class OrganizationDetail(generics.RetrieveUpdateDestroyAPIView):
    '''
    This is for details, updates, or deletion of a particular instance 
    of an Organization
    '''
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = (permissions.IsAdminUser,)


class ResourceList(generics.ListCreateAPIView):
    '''
    This endpoint allows us to list or create Resources
    See methods below regarding listing logic and creation logic
    Some filtering can be added at some point
    '''
    queryset = Resource.objects.all()
    serializer_class = ResourceSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('is_active',)
    
    def get_queryset(self):
        '''
        This overrides the get_queryset method of rest_framework.generics.GenericAPIView
        This allows us to return only Resource instances belonging to the user.
        If an admin is requesting, then we return all
        '''
        queryset = super(ResourceList, self).get_queryset()
        if not self.request.user.is_staff:
            queryset = Resource.objects.user_resources(self.request.user)
        return queryset


    def create(self, request, *args, **kwargs):
        '''
        This override provides us with the ability to create multiple instances
        Pretty much a verbatim copy of the implementation from CreateMixin except
        that we add the many=... kwarg when we call get_serializer
        '''
        serializer = self.get_serializer(data=request.data, many=isinstance(request.data,list))
        utils.create_resource(serializer, self.request.user)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class ResourceDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Resource.objects.all()
    serializer_class = ResourceSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self):
        '''
        Custom behavior for object retrieval- admins can get anything
        Regular users can only get objects they own.  
        Instead of the default 403 (which exposes that a particular object
        does exist), return 404 if they are not allowed to access an object.
        '''
        obj = super(ResourceDetail, self).get_object()
        if (self.request.user.is_staff) or (obj.get_owner() == self.request.user):
            return obj
        else:
            raise Http404


class UserResourceList(generics.ListAPIView):
    '''
    This lists the Resource instances for a particular user
    This view is entirely protected-- only accessible by staff
    Since regular users can only see the Resources they own,
    they can just use the "vanilla" listing endpoint
    '''
    serializer_class = ResourceSerializer
    permission_classes = (permissions.IsAdminUser,)
    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('is_active',)

    def get_queryset(self):
        user_pk = self.kwargs['user_pk']
        try:
            user = get_user_model().objects.get(pk=user_pk)
            return Resource.objects.user_resources(user)
        except ObjectDoesNotExist as ex:
            raise Http404
