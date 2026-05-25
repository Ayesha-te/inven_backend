from django.db import migrations, models


def migrate_subscription_tiers(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    User.objects.filter(subscription_plan='STARTER').update(subscription_plan='STANDARD')
    User.objects.filter(subscription_plan='PRO').update(subscription_plan='OTHER')
    User.objects.filter(subscription_plan='FREE').update(subscription_plan='BASIC')
    User.objects.filter(subscription_plan='PREMIUM').update(subscription_plan='OTHER')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_update_subscription_tiers'),
    ]

    operations = [
        migrations.RunPython(migrate_subscription_tiers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='user',
            name='subscription_plan',
            field=models.CharField(
                choices=[('BASIC', 'Basic'), ('STANDARD', 'Standard'), ('OTHER', 'Other')],
                default='BASIC',
                max_length=10,
            ),
        ),
    ]
