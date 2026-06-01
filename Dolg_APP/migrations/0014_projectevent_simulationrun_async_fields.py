from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('Dolg_APP', '0013_subscription_stripe_customer_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='simulationrun',
            name='finished_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='simulationrun',
            name='message',
            field=models.CharField(blank=True, default='', max_length=240),
        ),
        migrations.AddField(
            model_name='simulationrun',
            name='progress_percent',
            field=models.PositiveSmallIntegerField(default=100),
        ),
        migrations.AddField(
            model_name='simulationrun',
            name='started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='ProjectEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(choices=[('project_created', 'Проект создан'), ('project_updated', 'Проект обновлен'), ('scheme_saved', 'Схема сохранена'), ('simulation_run', 'Запуск симуляции'), ('measurement_added', 'Измерение добавлено'), ('review_created', 'Review создан'), ('bom_exported', 'BOM экспортирован'), ('import_finished', 'Импорт завершен'), ('comment_added', 'Комментарий добавлен')], db_index=True, max_length=40)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='events', to='Dolg_APP.schematicproject')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='project_events', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Событие проекта',
                'verbose_name_plural': 'События проектов',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='projectevent',
            index=models.Index(fields=['project', '-created_at'], name='pe_project_created_idx'),
        ),
        migrations.AddIndex(
            model_name='projectevent',
            index=models.Index(fields=['event_type', '-created_at'], name='pe_type_created_idx'),
        ),
    ]
