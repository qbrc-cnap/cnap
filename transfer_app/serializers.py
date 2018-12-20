from rest_framework import serializers

from base.serializers import ResourceSerializer
from transfer_app.models import Transfer, TransferCoordinator

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
