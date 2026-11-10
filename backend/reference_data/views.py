from django.db.models import BooleanField, Case, ExpressionWrapper, Q, Value, When
from rest_framework import generics

from reference_data.models import BenchmarkCase
from reference_data.serializers import (
    ReferenceCaseDetailSerializer,
    ReferenceCaseFilterSerializer,
    ReferenceCaseListSerializer,
)


def _cases():
    return BenchmarkCase.objects.select_related("dataset").annotate(
        has_annotated_plan=ExpressionWrapper(
            Q(annotated_plan__isnull=False), output_field=BooleanField()
        )
    )


class ReferenceCaseListView(generics.ListAPIView):
    """GET /api/v1/reference-cases/?split=&level=&days=&page= (read-only)"""

    serializer_class = ReferenceCaseListSerializer

    def get_queryset(self):
        filters = ReferenceCaseFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        split_order = Case(
            *(When(split=split, then=Value(rank)) for rank, split in enumerate(BenchmarkCase.Split.values))
        )
        return (
            _cases()
            .defer("reference_information", "annotated_plan")
            .filter(**filters.validated_data)
            .order_by(split_order, "source_row")
        )


class ReferenceCaseDetailView(generics.RetrieveAPIView):
    """GET /api/v1/reference-cases/{id}/ (read-only)"""

    serializer_class = ReferenceCaseDetailSerializer
    lookup_field = "case_id"
    lookup_url_kwarg = "case_id"

    def get_queryset(self):
        return _cases()
