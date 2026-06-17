from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('Dolg_APP', '0019_hash_organization_api_tokens'),
    ]

    operations = [
        migrations.CreateModel(
            name='EngineJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('engine_id', models.CharField(db_index=True, max_length=80)),
                ('engine_name', models.CharField(blank=True, max_length=120)),
                ('analysis_type', models.CharField(db_index=True, default='unknown', max_length=32)),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('queued', 'queued'),
                            ('running', 'running'),
                            ('success', 'success'),
                            ('error', 'error'),
                            ('cancelled', 'cancelled'),
                            ('stale', 'stale'),
                        ],
                        db_index=True,
                        default='queued',
                        max_length=20,
                    ),
                ),
                ('progress_percent', models.PositiveSmallIntegerField(default=0)),
                ('message', models.CharField(blank=True, max_length=260)),
                ('external_id', models.CharField(blank=True, db_index=True, max_length=160)),
                ('worker', models.CharField(blank=True, max_length=120)),
                ('netlist', models.TextField(blank=True)),
                ('scheme_data', models.JSONField(blank=True, default=dict)),
                ('options', models.JSONField(blank=True, default=dict)),
                ('input_payload', models.JSONField(blank=True, default=dict)),
                ('result', models.JSONField(blank=True, default=dict)),
                ('warnings', models.JSONField(blank=True, default=list)),
                ('artifacts', models.JSONField(blank=True, default=list)),
                ('error', models.TextField(blank=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('heartbeat_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'project',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='engine_jobs',
                        to='Dolg_APP.schematicproject',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='engine_jobs',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='enginejob',
            index=models.Index(fields=['user', 'status', '-created_at'], name='ej_user_status_created_idx'),
        ),
        migrations.AddIndex(
            model_name='enginejob',
            index=models.Index(fields=['engine_id', 'status', '-created_at'], name='ej_engine_status_created_idx'),
        ),
        migrations.AddIndex(
            model_name='enginejob',
            index=models.Index(fields=['project', '-created_at'], name='ej_project_created_idx'),
        ),
    ]
