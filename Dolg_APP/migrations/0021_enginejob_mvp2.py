from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Dolg_APP', '0020_enginejob'),
    ]

    operations = [
        migrations.AddField(
            model_name='enginejob',
            name='audit_log',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='enginejob',
            name='max_retries',
            field=models.PositiveSmallIntegerField(default=2),
        ),
        migrations.AddField(
            model_name='enginejob',
            name='reason',
            field=models.CharField(blank=True, max_length=180),
        ),
        migrations.AddField(
            model_name='enginejob',
            name='result_contract_version',
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='enginejob',
            name='retry_count',
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
