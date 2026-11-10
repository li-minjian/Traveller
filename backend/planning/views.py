from rest_framework import generics

from planning.models import PlanningSession
from planning.serializers import PlanningSessionSerializer


class PlanningSessionCreateView(generics.CreateAPIView):
    """POST /api/v1/planning-sessions/"""

    queryset = PlanningSession.objects.all()
    serializer_class = PlanningSessionSerializer


class PlanningSessionDetailView(generics.RetrieveAPIView):
    """GET /api/v1/planning-sessions/{id}/"""

    queryset = PlanningSession.objects.all()
    serializer_class = PlanningSessionSerializer
