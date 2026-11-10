from django.urls import path

from reference_data import views

urlpatterns = [
    path(
        "reference-cases/",
        views.ReferenceCaseListView.as_view(),
        name="reference-case-list",
    ),
    path(
        "reference-cases/<slug:case_id>/",
        views.ReferenceCaseDetailView.as_view(),
        name="reference-case-detail",
    ),
]
