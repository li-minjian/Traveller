from rest_framework import serializers

from reference_data.models import BenchmarkCase, BenchmarkDataset

DATA_KIND = "historical_benchmark"


class DatasetSerializer(serializers.ModelSerializer):
    class Meta:
        model = BenchmarkDataset
        fields = [
            "slug",
            "name",
            "version",
            "license",
            "license_url",
            "source_url",
            "homepage_url",
            "citation",
            "notice",
        ]


class ReferenceCaseListSerializer(serializers.ModelSerializer):
    """Case without the large reference information and annotated plan."""

    id = serializers.CharField(source="case_id")
    data_kind = serializers.SerializerMethodField()
    dataset = DatasetSerializer()
    budget = serializers.SerializerMethodField()
    has_annotated_plan = serializers.BooleanField()

    class Meta:
        model = BenchmarkCase
        fields = [
            "id",
            "data_kind",
            "dataset",
            "split",
            "level",
            "query",
            "org",
            "dest",
            "days",
            "visiting_city_number",
            "date",
            "people_number",
            "local_constraint",
            "budget",
            "has_annotated_plan",
        ]

    def get_data_kind(self, case) -> str:
        return DATA_KIND

    def get_budget(self, case) -> dict | None:
        if case.budget is None:
            return None
        return {
            "amount": case.budget,
            "currency": BenchmarkCase.BUDGET_CURRENCY,
            "basis": BenchmarkCase.BUDGET_BASIS,
        }


class ReferenceCaseDetailSerializer(ReferenceCaseListSerializer):
    class Meta(ReferenceCaseListSerializer.Meta):
        fields = ReferenceCaseListSerializer.Meta.fields + [
            "annotated_plan",
            "reference_information",
        ]


class ReferenceCaseFilterSerializer(serializers.Serializer):
    split = serializers.ChoiceField(choices=BenchmarkCase.Split.choices, required=False)
    level = serializers.ChoiceField(choices=BenchmarkCase.Level.choices, required=False)
    days = serializers.IntegerField(min_value=1, required=False)
