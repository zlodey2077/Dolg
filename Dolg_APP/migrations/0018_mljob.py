from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('Dolg_APP', '0017_functionalblock'),
    ]

    operations = [
        migrations.CreateModel(
            name='MLJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('job_type', models.CharField(choices=[('dataset_import', 'Dataset import'), ('training', 'Training'), ('validation', 'Validation'), ('export', 'Export'), ('promotion', 'Promotion')], db_index=True, max_length=32)),
                ('status', models.CharField(choices=[('queued', 'queued'), ('running', 'running'), ('success', 'success'), ('error', 'error'), ('cancelled', 'cancelled'), ('stale', 'stale')], db_index=True, default='queued', max_length=20)),
                ('progress_percent', models.PositiveSmallIntegerField(default=0)),
                ('source', models.CharField(blank=True, max_length=160)),
                ('message', models.CharField(blank=True, max_length=260)),
                ('parameters', models.JSONField(blank=True, default=dict)),
                ('result', models.JSONField(blank=True, default=dict)),
                ('stdout_tail', models.TextField(blank=True)),
                ('error', models.TextField(blank=True)),
                ('processed', models.PositiveIntegerField(default=0)),
                ('created_count', models.PositiveIntegerField(default=0)),
                ('updated_count', models.PositiveIntegerField(default=0)),
                ('skipped_count', models.PositiveIntegerField(default=0)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('heartbeat_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ml_jobs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='mljob',
            index=models.Index(fields=['job_type', 'status', '-created_at'], name='mljob_type_status_created_idx'),
        ),
        migrations.AddIndex(
            model_name='mljob',
            index=models.Index(fields=['status', '-heartbeat_at'], name='mljob_status_heartbeat_idx'),
        ),
    ]
