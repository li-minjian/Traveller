from rest_framework import serializers

from planning.models import Message, PlanningSession


class PlanningSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanningSession
        fields = ["id", "title", "created_at"]
        read_only_fields = ["id", "created_at"]


class MessageSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Message
        fields = ["id", "role", "content", "created_at", "result"]


class MessageInputSerializer(serializers.Serializer):
    """Body of POST …/messages/: free text, form fields, or both."""

    text = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    fields = serializers.DictField(required=False)

    def validate(self, attrs):
        if not attrs.get("text") and not attrs.get("fields"):
            raise serializers.ValidationError("Send a text, form fields, or both.")
        return attrs
