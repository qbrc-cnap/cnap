from rest_framework import serializers

from base.models import Resource, Organization

class ResourceSerializer(serializers.ModelSerializer):

    class Meta:
        model = Resource
        fields = ('id', \
                  'source', \
                  'source_path', \
                  'path', \
                  'name', \
                  'size', \
                  'owner', \
                  'is_active', \
                  'originated_from_upload', \
                  'total_downloads', \
                  'date_added', \
                  'expiration_date' \
        )

class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = '__all__'


class TreeObjectSerializer(serializers.BaseSerializer):
    '''
    This provides a read-only serialization that is used by 
    a view providing a data structure to the front-end. This uses
    the gui_representation method defined in the object we are serializing
    '''
    def to_representation(self, obj):
        return obj.gui_representation()
