# Generated manually on 2025-11-18

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("glidepath_app", "0015_alter_assumptionupload_user"),
    ]

    operations = [
        migrations.CreateModel(
            name="CategoryAssumptionMapping",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "horizon",
                    models.CharField(
                        choices=[
                            ("5yr", "5 Year"),
                            ("7yr", "7 Year"),
                            ("10yr", "10 Year"),
                            ("15yr", "15 Year"),
                            ("20yr", "20 Year"),
                            ("25yr", "25 Year"),
                            ("30yr", "30 Year"),
                        ],
                        default="10yr",
                        help_text="The time horizon for expected returns",
                        max_length=10,
                    ),
                ),
                (
                    "assumption_data",
                    models.ForeignKey(
                        blank=True,
                        help_text="The assumption data to use (null means use class defaults)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="category_mappings",
                        to="glidepath_app.assumptiondata",
                    ),
                ),
                (
                    "category",
                    models.OneToOneField(
                        help_text="The asset category this mapping applies to",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assumption_mapping",
                        to="glidepath_app.assetcategory",
                    ),
                ),
            ],
            options={
                "ordering": ["category__asset_class__name", "category__name"],
            },
        ),
    ]
