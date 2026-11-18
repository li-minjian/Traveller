from django.urls import path

from planning import views

urlpatterns = [
    path("places/", views.PlaceListView.as_view(), name="place-list"),
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
    path(
        "planning-sessions/<uuid:pk>/trip-state/",
        views.TripStateView.as_view(),
        name="planning-session-trip-state",
    ),
    path(
        "planning-sessions/<uuid:pk>/messages/",
        views.MessageListCreateView.as_view(),
        name="planning-session-messages",
    ),
]
