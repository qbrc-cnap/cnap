from rest_framework import serializers

from base.models import Resource

class ResourceSerializer(serializers.ModelSerializer):

    class Meta:
        model = Resource
        fields = ('id', \
                  'source', \
                  'path', \
                  'name', \
                  'size', \
                  'owner', \
                  'is_active', \
                  'date_added', \
                  'expiration_date' \
        )