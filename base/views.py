from rest_framework import generics, permissions, status
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from django.http import Http404
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.decorators import api_view

import base.utils as utils
from base.models import Resource, Organization
from base.serializers import ResourceSerializer, OrganizationSerializer, TreeObjectSerializer
from analysis.models import AnalysisProjectResource

class TreeObject(object):
    '''
    This is used to structure data for the front-end when we display files/resources for selection.  
    We organize the files by grouping them- they belong to analysis projects, uploads, 
    or can be "unattached".  
    They are displayed by providing a header (title) and some children nodes which are the files to select.  
    Each of the children nodes hold information like the file name and the primary key of the resource
    '''
    def __init__(self, title, children):
        '''
        title is the title that would show up in the UI as a "header".  
        For example, the name of the project that the Resource is associated with
        children is a list of Resource instances
        '''
        self.title = title
        self.children = children

    def gui_representation(self):
        '''
        This returns an object that will be passed to the UI.  The serializer uses this method
        to construct the serialized data.  They keys in this object depend on how we are displaying
        the data on the front-end.  
        '''
        d = {}
        d['text'] = self.title
        # below, we use the gui_representation method defined in the Resource class
        d['nodes'] = [x.gui_representation() for x in self.children]
        return d


@api_view(['GET'])
def get_tree_ready_resources(request):
    '''
    This view gives a tree-ready representation of the data for the front-end.
    '''

    # a list of TreeObject instances:
    all_sections = []

    user = request.user

    # Did the request ask for uploaded objects?  If we are showing downloads, we typically would NOT
    # want to show the uploads (why would they download a file they previously uploaded?)
    try:
        include_uploads = request.query_params['include_uploads']
    except KeyError:
        include_uploads=False

    if include_uploads:
        # We want to denote Resource instances that were created via user uploads to be in their own section:
        uploaded_resources = Resource.objects.user_resources(user).filter(originated_from_upload=True).filter(is_active=True)
        upload_section = TreeObject('Uploads', uploaded_resources)
        all_sections.append(upload_section)

    # get the non-uploaded resources, if any.  These would be Resource instances created as part of an analysis project (or similar)
    all_other_resources = Resource.objects.user_resources(user).filter(originated_from_upload=False).filter(is_active=True)

    # get the the subset of non-uploaded Resources that have an association to an AnalysisProject
    analysis_project_resources = AnalysisProjectResource.objects.filter(resource__in = all_other_resources)

    # determine the resources that were NOT uploads, but also not associated with projects:
    # typically these files would not exist, but we provide them for potential flexibility in the future
    ap_resource_list = [x.resource for x in analysis_project_resources]
    unassociated_resources = [x for x in all_other_resources if not x in ap_resource_list]
    if len(unassociated_resources) > 0:
        unassociated_section = TreeObject('Other', unassociated_resources)
        all_sections.append(unassociated_section)

    # for the Resource instances associated with analysis projects, we have to display some header/section title 
    # in the tree.  TODO: change this from the UUID
    d = {}
    for apr in analysis_project_resources:
        project = apr.analysis_project
        ap_uuid = str(project.analysis_uuid)
        if ap_uuid in d:
            d[ap_uuid].append(apr.resource)
        else:
            d[ap_uuid] = [apr.resource,]
    for key, resource_list in d.items():
        all_sections.append(TreeObject(key, resource_list))

    # we now have a list of TreeObject instances.  Serialize.
    serializer = TreeObjectSerializer(all_sections, many=True)
    return Response(serializer.data)


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
    filter_fields = ('is_active', 'originated_from_upload')
    
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
