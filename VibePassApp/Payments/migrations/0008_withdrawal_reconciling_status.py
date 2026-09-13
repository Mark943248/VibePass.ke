from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("Payments", "0007_payment_checkout_data_snapshot"),
    ]

    operations = [
        migrations.AlterField(
            model_name="withdrawal",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("processing", "Processing"),
                    ("reconciling", "Reconciliation Required"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
    ]
