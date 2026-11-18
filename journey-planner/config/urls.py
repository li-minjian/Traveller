from django.urls import path, re_path

from planner import views

urlpatterns = [
    path("health", views.health, name="health"),
    path("plan", views.PlanView.as_view(), name="plan"),
    path("places", views.places, name="places"),
    re_path(r"^", views.not_found),
]

handler404 = "planner.views.not_found"
handler500 = "planner.views.server_error"
