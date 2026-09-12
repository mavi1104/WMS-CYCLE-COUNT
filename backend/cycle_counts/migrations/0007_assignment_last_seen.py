from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [("cycle_counts", "0006_cycle_count_assignment")]

    operations = [
        migrations.AddField(
            model_name="cyclecountassignment",
            name="last_seen_at",
            field=models.DateTimeField(auto_now=True, default=timezone.now),
            preserve_default=False,
        ),
    ]
