from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("Users", "0008_merge_0006_user_mpesa_number_0007_organizerprofile"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrganizerWallet",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "available_withdraw_balance",
                    models.DecimalField(
                        decimal_places=2, default=0.0, max_digits=10
                    ),
                ),
                (
                    "pending_escrow_balance",
                    models.DecimalField(
                        decimal_places=2, default=0.0, max_digits=10
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organiser",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="organiser",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
