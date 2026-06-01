from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('Dolg_APP', '0014_projectevent_simulationrun_async_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='EngineeringArtifact',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_name', models.CharField(max_length=240)),
                ('source_path', models.TextField(blank=True)),
                ('artifact_type', models.CharField(choices=[('document', 'Document'), ('cad_drawing', 'CAD drawing'), ('cad_netlist', 'CAD netlist'), ('check_report', 'Check report'), ('bom', 'BOM'), ('simulation', 'Simulation'), ('unknown', 'Unknown')], default='unknown', max_length=32)),
                ('parser', models.CharField(blank=True, max_length=64)),
                ('status', models.CharField(choices=[('parsed', 'parsed'), ('partial', 'partial'), ('unsupported', 'unsupported'), ('error', 'error')], default='parsed', max_length=20)),
                ('checksum', models.CharField(db_index=True, max_length=64)),
                ('size_bytes', models.PositiveIntegerField(default=0)),
                ('summary', models.TextField(blank=True)),
                ('facts', models.JSONField(blank=True, default=dict)),
                ('warnings', models.JSONField(blank=True, default=list)),
                ('errors', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='engineering_artifacts', to='Dolg_APP.schematicproject')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='engineering_artifacts', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'unique_together': {('project', 'checksum', 'source_name')},
            },
        ),
        migrations.CreateModel(
            name='AITrainingExample',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('artifact_summary', 'Artifact summary'), ('drc_finding', 'DRC finding'), ('fault_case', 'Fault case'), ('review_hint', 'Review hint'), ('user_correction', 'User correction')], max_length=40)),
                ('prompt', models.TextField()),
                ('target', models.TextField()),
                ('features', models.JSONField(blank=True, default=dict)),
                ('is_validated', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('artifact', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='training_examples', to='Dolg_APP.engineeringartifact')),
                ('project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='ai_training_examples', to='Dolg_APP.schematicproject')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ai_training_examples', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='engineeringartifact',
            index=models.Index(fields=['project', '-created_at'], name='artifact_project_created_idx'),
        ),
        migrations.AddIndex(
            model_name='engineeringartifact',
            index=models.Index(fields=['artifact_type', '-created_at'], name='artifact_type_created_idx'),
        ),
        migrations.AddIndex(
            model_name='engineeringartifact',
            index=models.Index(fields=['checksum'], name='artifact_checksum_idx'),
        ),
        migrations.AddIndex(
            model_name='aitrainingexample',
            index=models.Index(fields=['kind', '-created_at'], name='aitrain_kind_created_idx'),
        ),
        migrations.AddIndex(
            model_name='aitrainingexample',
            index=models.Index(fields=['is_validated', '-created_at'], name='aitrain_valid_created_idx'),
        ),
    ]
