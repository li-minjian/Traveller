from django.urls import include, path, re_path

from config import views

urlpatterns = [
    path("api/v1/health/", views.health, name="health"),
    path("api/v1/", include("planning.urls")),
    # Unknown API paths answer with the JSON error body, also when DEBUG is on.
    re_path(r"^api/", views.not_found),
]

handler404 = "config.views.not_found"
handler500 = "config.views.server_error"
