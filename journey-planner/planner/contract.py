"""Search request of the Main-Agent, see docs/SEARCH_CONTRACT.md (AG04 #33)."""

from rest_framework import serializers

SUPPORTED_MODES = ("flight",)
PRICE_BASES = ("per_person", "trip_total")


class DepartureSerializer(serializers.Serializer):
    earliest = serializers.DateField()
    latest = serializers.DateField()

    def validate(self, attrs):
        if attrs["latest"] < attrs["earliest"]:
            raise serializers.ValidationError(
                {"latest": ["Must not be before the earliest departure date."]}
            )
        return attrs


class MoneySerializer(serializers.Serializer):
    amount = serializers.FloatField(min_value=0.01)
    currency = serializers.RegexField(r"^[A-Za-z]{3}$")
    basis = serializers.ChoiceField(choices=PRICE_BASES)

    def validate_currency(self, value):
        return value.upper()


class SearchRequestSerializer(serializers.Serializer):
    origin = serializers.CharField(max_length=100)
    destination = serializers.CharField(max_length=100)
    departure = DepartureSerializer()
    travelers = serializers.IntegerField(min_value=1)
    max_price = MoneySerializer(allow_null=True)
    max_stops = serializers.IntegerField(min_value=0, allow_null=True)
    modes = serializers.ListField(
        child=serializers.ChoiceField(choices=SUPPORTED_MODES), allow_empty=False
    )

    def get_fields(self):
        fields = super().get_fields()
        # "return" is a Python keyword and cannot be declared as an attribute.
        # A window makes the search a round trip; null means one-way.
        fields["return"] = DepartureSerializer(allow_null=True)
        return fields

    def validate(self, attrs):
        back = attrs.get("return")
        if back and back["latest"] < attrs["departure"]["earliest"]:
            raise serializers.ValidationError(
                {"return": ["Must not be before the departure."]}
            )
        return attrs
