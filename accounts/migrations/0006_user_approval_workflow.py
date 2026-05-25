from django.db import migrations, models
import django.db.models.deletion


def populate_approval_state(apps, schema_editor):
    User = apps.get_model('accounts', 'User')

    User.objects.filter(is_superuser=True).update(approval_status='APPROVED')
    User.objects.filter(is_superuser=False, is_active=True).update(approval_status='APPROVED')
    User.objects.filter(is_superuser=False, is_active=False).update(approval_status='PENDING')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_expand_subscription_tiers'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='approval_status',
            field=models.CharField(
                choices=[('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')],
                default='PENDING',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='approved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='approved_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='approved_accounts',
                to='accounts.user',
            ),
        ),
        migrations.RunPython(populate_approval_state, migrations.RunPython.noop),
    ]
