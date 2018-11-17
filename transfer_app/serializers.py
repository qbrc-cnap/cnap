from rest_framework import serializers

from base.models import Resource
from transfer_app.models import Transfer, TransferCoordinator
from django.contrib.auth import get_user_model

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ('id', 'email', 'password')

    def create(self, validated_data):
        user = get_user_model()(**validated_data)
        user.set_password(validated_data['password'])
        user.save()
        return user

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


class TransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transfer
        fields = ('id', \
                  'resource', \
                  'download', \
                  'destination', \
                  'completed', \
                  'success', \
                  'start_time', \
                  'finish_time', \
                  'duration', \
                  'coordinator',
        )

class TransferCoordinatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransferCoordinator
        fields = ('id', 'completed')


class TransferredResourceSerializer(serializers.ModelSerializer):
    resource = ResourceSerializer(read_only=True)

    class Meta:
        model = Transfer
        fields = '__all__'
