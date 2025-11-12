# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('glidepath_app', '0011_portfolio_retirement_age_portfolio_year_born'),
    ]

    operations = [
        migrations.AddField(
            model_name='fund',
            name='preference',
            field=models.IntegerField(default=99, help_text='Display order and recommendation priority (1-10 = recommended, lower = higher priority)'),
        ),
    ]
