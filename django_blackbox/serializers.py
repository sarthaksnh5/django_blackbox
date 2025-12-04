from rest_framework import serializers

from django_blackbox.models import (
    Incident,
    RequestActivity,
)

class IncidentSerializer(serializers.ModelSerializer):

    class Meta:
        model = Incident
        fields = '__all__'

class RequestActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = RequestActivity
        fields = '__all__'