from django.urls import path

from planning import views

urlpatterns = [
    path(
        "planning-sessions/",
        views.PlanningSessionCreateView.as_view(),
        name="planning-session-list",
    ),
    path(
        "planning-sessions/<uuid:pk>/",
        views.PlanningSessionDetailView.as_view(),
        name="planning-session-detail",
    ),
]
