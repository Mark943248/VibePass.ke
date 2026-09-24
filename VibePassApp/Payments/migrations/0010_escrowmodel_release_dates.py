from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("Payments", "0009_escrowmodel"),
    ]

    operations = [
        migrations.AddField(
            model_name="escrowmodel",
            name="release_date",
            field=models.DateTimeField(
                db_index=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="escrowmodel",
            name="released_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                null=True,
            ),
        ),
    ]
