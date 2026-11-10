from django.db import models


class BenchmarkDataset(models.Model):
    """Origin, version and license of an imported benchmark dataset."""

    slug = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    version = models.CharField(max_length=100)
    source_url = models.URLField()
    homepage_url = models.URLField(blank=True)
    license = models.CharField(max_length=100)
    license_url = models.URLField()
    citation = models.TextField()
    retrieved_on = models.DateField()
    changes = models.TextField()
    notice = models.TextField()
    imported_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.name} ({self.version[:7]})"


class BenchmarkCase(models.Model):
    """One historical TravelPlanner query with its parameters and references.

    Field names follow the original dataset. Complex values (reference
    information, annotated plan) are stored unchanged as JSON.
    """

    # TravelPlanner budgets are US dollars for the whole trip and all travelers.
    BUDGET_CURRENCY = "USD"
    BUDGET_BASIS = "trip_total"

    class Split(models.TextChoices):
        TRAIN = "train"
        VALIDATION = "validation"
        TEST = "test"

    class Level(models.TextChoices):
        EASY = "easy"
        MEDIUM = "medium"
        HARD = "hard"

    case_id = models.CharField(max_length=100, unique=True)
    dataset = models.ForeignKey(
        BenchmarkDataset, on_delete=models.PROTECT, related_name="cases"
    )
    split = models.CharField(max_length=20, choices=Split.choices)
    source_row = models.PositiveIntegerField()
    level = models.CharField(max_length=10, choices=Level.choices)
    query = models.TextField()
    org = models.CharField(max_length=200)
    dest = models.CharField(max_length=200)
    days = models.PositiveSmallIntegerField()
    visiting_city_number = models.PositiveSmallIntegerField(null=True)
    date = models.JSONField()
    people_number = models.PositiveSmallIntegerField(null=True)
    local_constraint = models.JSONField(null=True)
    budget = models.PositiveIntegerField(null=True)
    annotated_plan = models.JSONField(null=True)
    reference_information = models.JSONField()
    content_sha256 = models.CharField(max_length=64)
    imported_at = models.DateTimeField()

    class Meta:
        ordering = ["case_id"]
        indexes = [models.Index(fields=["split", "level", "days"])]

    def __str__(self) -> str:
        return self.case_id
