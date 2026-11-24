import uuid

from django.db import models


class PlanningSession(models.Model):
    """A travel planning session; later anchor for trip state and chat history."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    browser_owner = models.UUIDField(null=True, editable=False)
    title = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    # Known trip data with provenance; read and written via planning.trip_state.
    trip_state = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class Message(models.Model):
    """One chat message of a planning session, from the user or the Main-Agent."""

    class Role(models.TextChoices):
        USER = "user"
        ASSISTANT = "assistant"

    # The primary key keeps the order of the conversation; `public_id` is the
    # ID the API shows.
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    session = models.ForeignKey(
        PlanningSession, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    # Search result attached to an answer of the agent, otherwise null.
    result = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:50]}"
