from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("planning", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="planningsession",
            name="trip_state",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
