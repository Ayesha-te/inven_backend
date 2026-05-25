from django.db import migrations, models


def migrate_legacy_subscription_plans(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    User.objects.filter(subscription_plan='FREE').update(subscription_plan='BASIC')
    User.objects.filter(subscription_plan='PREMIUM').update(subscription_plan='PRO')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_alter_user_managers_alter_user_username'),
    ]

    operations = [
        migrations.RunPython(migrate_legacy_subscription_plans, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='user',
            name='subscription_plan',
            field=models.CharField(
                choices=[('BASIC', 'Basic'), ('STARTER', 'Starter'), ('PRO', 'Pro')],
                default='BASIC',
                max_length=10
            ),
        ),
    ]
