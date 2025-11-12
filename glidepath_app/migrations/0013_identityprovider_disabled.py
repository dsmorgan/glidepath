# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('glidepath_app', '0012_fund_preference'),
    ]

    operations = [
        migrations.AddField(
            model_name='identityprovider',
            name='disabled',
            field=models.BooleanField(default=False, help_text='Prevents new logins from this provider'),
        ),
    ]
