import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers, status
from rest_framework.response import Response

from agent import places
from agent.main_agent import handle_message
from agent.planner_client import PlannerClient
from config.exceptions import ServiceUnavailable
from llm import LLMError, get_llm_client
from llm import Message as LLMMessage
from planning.models import Message, PlanningSession
from planning.serializers import (
    MessageInputSerializer,
    MessageSerializer,
    PlanningSessionSerializer,
)
from planning.trip_state import INFERRED, TripState, load_trip_state, save_trip_state

logger = logging.getLogger(__name__)


class PlanningSessionCreateView(generics.CreateAPIView):
    """POST /api/v1/planning-sessions/"""

    queryset = PlanningSession.objects.all()
    serializer_class = PlanningSessionSerializer

    def perform_create(self, serializer):
        # A new trip starts with one traveller, marked as assumed: the form
        # shows 1 instead of an empty field, and the agent asks the user to
        # confirm it before the first search.
        state = TripState()
        state.apply({"travelers": 1}, provenance=INFERRED)
        serializer.save(trip_state=state.to_dict())


class PlanningSessionDetailView(generics.RetrieveAPIView):
    """GET /api/v1/planning-sessions/{id}/"""

    queryset = PlanningSession.objects.all()
    serializer_class = PlanningSessionSerializer


class PlaceListView(generics.GenericAPIView):
    """GET /api/v1/places/ – the places with flight data, for suggestions in the form."""

    def get(self, request):
        listing = places.load(PlannerClient())
        if listing is None:
            raise ServiceUnavailable("The list of places is temporarily unavailable.")
        return Response({"count": len(listing), "next": None, "previous": None, "results": listing})


class TripStateView(generics.GenericAPIView):
    """GET /api/v1/planning-sessions/{id}/trip-state/ – what is known about the trip."""

    queryset = PlanningSession.objects.all()

    def get(self, request, pk):
        state = load_trip_state(self.get_object())
        return Response(
            {"trip_state": state.to_dict(), "missing_fields": state.missing_required_fields()}
        )


class MessageListCreateView(generics.ListAPIView):
    """GET and POST /api/v1/planning-sessions/{id}/messages/ – the chat with the Main-Agent."""

    serializer_class = MessageSerializer

    def get_queryset(self):
        session = get_object_or_404(PlanningSession, pk=self.kwargs["pk"])
        return session.messages.all()

    def post(self, request, pk):
        session = get_object_or_404(PlanningSession, pk=pk)
        body = MessageInputSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        text = body.validated_data.get("text", "").strip()
        fields = body.validated_data.get("fields") or {}

        state = load_trip_state(session)
        previous_state = state.to_dict()
        planner = PlannerClient()
        # Form fields come straight from the user and count as confirmed.
        # Places are matched against the planner's list first.
        fields = dict(fields)
        catalog = places.catalog(planner)
        rejected = catalog.check(fields) if catalog else {}
        rejected.update(state.apply(fields))
        if rejected:
            raise serializers.ValidationError(
                {"fields": {name: [reason] for name, reason in rejected.items()}}
            )
        history = [
            LLMMessage(message.role, message.content) for message in session.messages.all()
        ]
        try:
            turn = handle_message(
                state,
                text,
                history=history,
                llm=get_llm_client(),
                planner=planner,
                previous_state=previous_state,
                # A failed search does not count: the next message tries again.
                searched_before=session.messages.filter(result__isnull=False)
                .exclude(result__status="error")
                .exists(),
            )
        except LLMError as error:
            # Nothing is saved; the client can send the same message again.
            logger.warning("Chat turn failed: %s", type(error).__name__)
            raise ServiceUnavailable("The language model is temporarily unavailable.") from None

        with transaction.atomic():
            save_trip_state(session, state)
            user_message = None
            if text:
                user_message = Message.objects.create(
                    session=session, role=Message.Role.USER, content=text
                )
            reply = Message.objects.create(
                session=session,
                role=Message.Role.ASSISTANT,
                content=turn.reply,
                result=turn.result,
            )
        return Response(
            {
                "user_message": MessageSerializer(user_message).data if user_message else None,
                "reply": MessageSerializer(reply).data,
                "trip_state": state.to_dict(),
                "missing_fields": state.missing_required_fields(),
            },
            status=status.HTTP_201_CREATED,
        )
