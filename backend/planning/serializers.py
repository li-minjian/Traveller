from rest_framework import serializers

from planning.models import PlanningSession


class PlanningSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanningSession
        fields = ["id", "title", "created_at"]
        read_only_fields = ["id", "created_at"]
