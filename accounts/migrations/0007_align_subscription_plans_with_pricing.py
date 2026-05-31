from django.db import migrations, models


def align_subscription_plans(apps, schema_editor):
    User = apps.get_model('accounts', 'User')

    User.objects.filter(subscription_plan='FREE').update(subscription_plan='BASIC')
    User.objects.filter(subscription_plan='STARTER').update(subscription_plan='BASIC')
    User.objects.filter(subscription_plan='STANDARD').update(subscription_plan='STARTER')
    User.objects.filter(subscription_plan='PREMIUM').update(subscription_plan='PRO')
    User.objects.filter(subscription_plan='OTHER').update(subscription_plan='PRO')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_user_approval_workflow'),
    ]

    operations = [
        migrations.RunPython(align_subscription_plans, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='user',
            name='subscription_plan',
            field=models.CharField(
                choices=[('BASIC', 'Basic'), ('STARTER', 'Starter'), ('PRO', 'Pro')],
                default='BASIC',
                max_length=10,
            ),
        ),
    ]
