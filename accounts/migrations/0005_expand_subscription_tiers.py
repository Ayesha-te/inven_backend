from django.db import migrations, models


def migrate_subscription_tiers_forward(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    User.objects.filter(subscription_plan='OTHER').update(subscription_plan='PREMIUM')
    User.objects.filter(subscription_plan='PRO').update(subscription_plan='PREMIUM')
    User.objects.filter(subscription_plan='FREE').update(subscription_plan='STARTER')


def migrate_subscription_tiers_backward(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    User.objects.filter(subscription_plan='PREMIUM').update(subscription_plan='OTHER')
    User.objects.filter(subscription_plan='STARTER').update(subscription_plan='BASIC')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_rename_subscription_tiers'),
    ]

    operations = [
        migrations.RunPython(migrate_subscription_tiers_forward, migrate_subscription_tiers_backward),
        migrations.AlterField(
            model_name='user',
            name='subscription_plan',
            field=models.CharField(
                choices=[('STARTER', 'Starter'), ('BASIC', 'Basic'), ('STANDARD', 'Standard'), ('PREMIUM', 'Premium')],
                default='STARTER',
                max_length=10,
            ),
        ),
    ]
