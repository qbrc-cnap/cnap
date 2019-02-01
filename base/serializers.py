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
