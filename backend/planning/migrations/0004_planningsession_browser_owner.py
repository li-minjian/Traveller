from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("planning", "0003_message")]

    operations = [
        migrations.AddField(
            model_name="planningsession",
            name="browser_owner",
            field=models.UUIDField(editable=False, null=True),
        ),
    ]
