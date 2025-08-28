from django.db import migrations


ASSET_CLASSES = ["Stocks", "Bonds", "Crypto", "Other"]


def create_asset_classes(apps, schema_editor):
    AssetClass = apps.get_model("glidepath_app", "AssetClass")
    for name in ASSET_CLASSES:
        AssetClass.objects.get_or_create(name=name)


def reverse(apps, schema_editor):
    AssetClass = apps.get_model("glidepath_app", "AssetClass")
    AssetClass.objects.filter(name__in=ASSET_CLASSES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("glidepath_app", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_asset_classes, reverse),
    ]
