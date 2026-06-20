from django.contrib import admin
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    AITrainingExample,
    Announcement,
    AuditLog,
    ChatReply,
    ChatTopic,
    Comment,
    EngineeringArtifact,
    EngineJob,
    MLJob,
    Organization,
    OrganizationInvite,
    OrganizationMember,
    OrgConversation,
    OrgConversationMessage,
    ProjectEvent,
    ProjectMeasurement,
    ProjectReview,
    ProjectVersion,
    SchematicProject,
    SimulationRun,
)


@admin.register(SchematicProject)
class SchematicProjectAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'user',
        'organization',
        'category',
        'status',
        'approval_state',
        'visibility',
        'difficulty',
        'versions_count',
        'runs_count',
        'reviews_count',
        'measurements_count',
        'updated_at',
    )
    list_filter = (
        'category',
        'status',
        'approval_state',
        'visibility',
        'difficulty',
        'is_demo',
        'created_at',
        'updated_at',
    )
    search_fields = ('name', 'description', 'user__username', 'user__email')
    readonly_fields = ('quick_links', 'created_at', 'updated_at')
    list_select_related = ('user', 'organization')
    list_editable = ('status', 'approval_state', 'visibility', 'difficulty')
    actions = (
        'mark_inprogress',
        'mark_completed',
        'submit_for_review',
        'approve_projects',
        'reject_projects',
        'publish_projects',
        'make_private',
        'restore_projects',
        'soft_delete_projects',
    )
    change_list_template = 'admin/dolg_app/schematicproject/change_list.html'
    fieldsets = (
        (None, {'fields': ('user', 'organization', 'name', 'description')}),
        (
            'Классификация',
            {'fields': ('category', 'status', 'approval_state', 'visibility', 'difficulty', 'is_demo')},
        ),
        (
            'Публикация и доступ',
            {'fields': ('share_token', 'deleted_at', 'quick_links'), 'classes': ('collapse',)},
        ),
        ('Данные схемы', {'fields': ('scheme_data',), 'classes': ('collapse',)}),
        ('Метаданные', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def get_queryset(self, request):
        return SchematicProject.all_objects.select_related('user', 'organization').annotate(
            _versions_count=Count('versions', distinct=True),
            _runs_count=Count('simulation_runs', distinct=True),
            _reviews_count=Count('reviews', distinct=True),
            _measurements_count=Count('measurements', distinct=True),
        )

    def changelist_view(self, request, extra_context=None):
        stats = {
            'total': SchematicProject.all_objects.count(),
            'active': SchematicProject.objects.count(),
            'demo': SchematicProject.all_objects.filter(is_demo=True).count(),
            'public': SchematicProject.all_objects.filter(visibility='public').count(),
            'team': SchematicProject.all_objects.filter(visibility='team').count(),
            'pending_review': SchematicProject.all_objects.filter(approval_state='pending_review').count(),
            'reviews': ProjectReview.objects.count(),
            'simulation_runs': SimulationRun.objects.count(),
            'measurements': ProjectMeasurement.objects.count(),
        }
        extra_context = extra_context or {}
        extra_context['project_dashboard'] = stats
        return super().changelist_view(request, extra_context=extra_context)

    def versions_count(self, obj):
        return getattr(obj, '_versions_count', obj.versions.count())

    versions_count.short_description = 'Версий'

    def runs_count(self, obj):
        return getattr(obj, '_runs_count', obj.simulation_runs.count())

    runs_count.short_description = 'Симуляций'

    @admin.display(description='Review', ordering='_reviews_count')
    def reviews_count(self, obj):
        return getattr(obj, '_reviews_count', obj.reviews.count())

    @admin.display(description='Измерений', ordering='_measurements_count')
    def measurements_count(self, obj):
        return getattr(obj, '_measurements_count', obj.measurements.count())

    @admin.display(description='Связанные данные')
    def quick_links(self, obj):
        if not obj.pk:
            return 'Сохраните проект, чтобы увидеть ссылки.'
        links = [
            ('Версии', reverse('admin:Dolg_APP_projectversion_changelist') + f'?project__id__exact={obj.pk}'),
            (
                'Симуляции',
                reverse('admin:Dolg_APP_simulationrun_changelist') + f'?project__id__exact={obj.pk}',
            ),
            ('Engine jobs', reverse('admin:Dolg_APP_enginejob_changelist') + f'?project__id__exact={obj.pk}'),
            ('Review', reverse('admin:Dolg_APP_projectreview_changelist') + f'?project__id__exact={obj.pk}'),
            (
                'Измерения',
                reverse('admin:Dolg_APP_projectmeasurement_changelist') + f'?project__id__exact={obj.pk}',
            ),
        ]
        return format_html(
            ' · '.join('<a href="{}">{}</a>' for _label, _url in links),
            *[value for link in links for value in (link[1], link[0])],
        )

    def _bulk_project_update(self, request, queryset, *, action, message, **fields):
        ids = list(queryset.values_list('id', flat=True)[:50])
        updated = queryset.update(**fields)
        AuditLog.log(
            actor=request.user,
            action=f'admin.projects.{action}',
            object_type='schematic_project',
            object_id='bulk',
            payload={'updated': updated, 'sample_ids': ids, 'fields': fields},
            request=request,
        )
        self.message_user(request, f'{message}: {updated}.')

    @admin.action(description='Статус: в работе')
    def mark_inprogress(self, request, queryset):
        self._bulk_project_update(
            request, queryset, action='mark_inprogress', message='Проектов в работе', status='inprogress'
        )

    @admin.action(description='Статус: завершено')
    def mark_completed(self, request, queryset):
        self._bulk_project_update(
            request, queryset, action='mark_completed', message='Проектов завершено', status='completed'
        )

    @admin.action(description='Отправить на ревью')
    def submit_for_review(self, request, queryset):
        self._bulk_project_update(
            request,
            queryset,
            action='submit_for_review',
            message='Проектов отправлено на ревью',
            approval_state='pending_review',
        )

    @admin.action(description='Одобрить проекты')
    def approve_projects(self, request, queryset):
        self._bulk_project_update(
            request, queryset, action='approve', message='Проектов одобрено', approval_state='approved'
        )

    @admin.action(description='Отклонить проекты')
    def reject_projects(self, request, queryset):
        self._bulk_project_update(
            request, queryset, action='reject', message='Проектов отклонено', approval_state='rejected'
        )

    @admin.action(description='Сделать публичными')
    def publish_projects(self, request, queryset):
        self._bulk_project_update(
            request, queryset, action='publish', message='Проектов опубликовано', visibility='public'
        )

    @admin.action(description='Сделать приватными')
    def make_private(self, request, queryset):
        self._bulk_project_update(
            request, queryset, action='make_private', message='Проектов скрыто', visibility='private'
        )

    @admin.action(description='Восстановить из корзины')
    def restore_projects(self, request, queryset):
        self._bulk_project_update(
            request, queryset, action='restore', message='Проектов восстановлено', deleted_at=None
        )

    @admin.action(description='Soft-delete выбранные')
    def soft_delete_projects(self, request, queryset):
        self._bulk_project_update(
            request,
            queryset,
            action='soft_delete',
            message='Проектов перенесено в корзину',
            deleted_at=timezone.now(),
        )


class OrganizationMemberInline(admin.TabularInline):
    model = OrganizationMember
    extra = 0
    autocomplete_fields = ('user', 'invited_by')
    fields = ('user', 'role', 'invited_by', 'joined_at', 'deactivated_at')
    readonly_fields = ('joined_at',)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'plan', 'owner', 'is_active', 'created_at')
    list_filter = ('plan', 'is_active', 'created_at')
    search_fields = ('name', 'slug', 'billing_email', 'owner__username')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ('owner',)
    list_select_related = ('owner',)
    inlines = (OrganizationMemberInline,)


@admin.register(OrganizationInvite)
class OrganizationInviteAdmin(admin.ModelAdmin):
    list_display = ('email', 'organization', 'role', 'created_at', 'expires_at', 'accepted_at')
    list_filter = ('role', 'created_at', 'accepted_at')
    search_fields = ('email', 'organization__name')
    autocomplete_fields = ('organization', 'invited_by', 'accepted_by')
    list_select_related = ('organization', 'invited_by', 'accepted_by')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'actor', 'organization', 'action', 'object_type', 'object_id')
    list_filter = ('action', 'timestamp')
    search_fields = ('action', 'object_type', 'object_id', 'actor__username', 'organization__name')
    readonly_fields = ('timestamp',)
    autocomplete_fields = ('actor', 'organization')
    list_select_related = ('actor', 'organization')


@admin.register(ProjectVersion)
class ProjectVersionAdmin(admin.ModelAdmin):
    list_display = ('project', 'version_number', 'change_note', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('project__name', 'project__user__username', 'change_note')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('project',)
    list_select_related = ('project',)


@admin.register(SimulationRun)
class SimulationRunAdmin(admin.ModelAdmin):
    list_display = (
        'project',
        'user',
        'analysis_type',
        'engine',
        'elapsed_ms',
        'progress_badge',
        'status',
        'created_at',
    )
    list_filter = ('analysis_type', 'engine', 'status', 'created_at')
    search_fields = ('project__name', 'user__username', 'netlist')
    readonly_fields = ('created_at', 'started_at', 'finished_at')
    autocomplete_fields = ('project', 'user')
    list_select_related = ('project', 'user')
    date_hierarchy = 'created_at'
    actions = ('mark_success', 'mark_error', 'mark_cancelled')

    @admin.display(description='Прогресс')
    def progress_badge(self, obj):
        color = '#168a3a' if obj.status == 'success' else '#b8860b'
        if obj.status == 'error':
            color = '#b3261e'
        return format_html('<strong style="color:{};">{}%</strong>', color, obj.progress_percent)

    @admin.action(description='Симуляции: success')
    def mark_success(self, request, queryset):
        updated = queryset.update(status='success', progress_percent=100, message='Marked success from admin')
        self.message_user(request, f'Симуляций помечено success: {updated}.')

    @admin.action(description='Симуляции: error')
    def mark_error(self, request, queryset):
        updated = queryset.update(status='error', message='Marked error from admin')
        self.message_user(request, f'Симуляций помечено error: {updated}.')

    @admin.action(description='Симуляции: cancelled')
    def mark_cancelled(self, request, queryset):
        updated = queryset.update(status='cancelled', message='Marked cancelled from admin')
        self.message_user(request, f'Симуляций помечено cancelled: {updated}.')


@admin.register(EngineJob)
class EngineJobAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'engine_id',
        'analysis_type',
        'status',
        'progress_badge',
        'retry_count',
        'project',
        'user',
        'heartbeat_at',
        'created_at',
    )
    list_filter = ('engine_id', 'analysis_type', 'status', 'created_at')
    search_fields = ('engine_id', 'engine_name', 'project__name', 'user__username', 'netlist', 'external_id')
    readonly_fields = ('created_at', 'updated_at', 'started_at', 'heartbeat_at', 'finished_at', 'audit_log')
    autocomplete_fields = ('project', 'user')
    list_select_related = ('project', 'user')
    date_hierarchy = 'created_at'
    actions = ('retry_jobs', 'mark_cancelled', 'mark_stale', 'mark_success')

    @admin.display(description='Progress')
    def progress_badge(self, obj):
        color = '#168a3a' if obj.status == 'success' else '#b8860b'
        if obj.status == 'error':
            color = '#b3261e'
        return format_html('<strong style="color:{};">{}%</strong>', color, obj.progress_percent)

    @admin.action(description='Повторить jobs: queued')
    def retry_jobs(self, request, queryset):
        from Dolg_APP.services.engine_jobs import retry_engine_job

        updated = 0
        rejected = 0
        for job in queryset:
            ok, _message = retry_engine_job(
                job,
                actor=request.user.get_username() or 'admin',
                reason='Retried from Django admin',
            )
            if ok:
                updated += 1
            else:
                rejected += 1
        self.message_user(request, f'Engine jobs поставлено в очередь: {updated}; rejected: {rejected}.')

    @admin.action(description='Отменить jobs')
    def mark_cancelled(self, request, queryset):
        now = timezone.now()
        updated = queryset.update(
            status='cancelled',
            heartbeat_at=now,
            finished_at=now,
            message='Cancelled from Django admin',
            reason='Cancelled from Django admin',
        )
        self.message_user(request, f'Engine jobs отменено: {updated}.')

    @admin.action(description='Пометить stale')
    def mark_stale(self, request, queryset):
        now = timezone.now()
        updated = queryset.update(
            status='stale',
            heartbeat_at=now,
            finished_at=now,
            message='Marked stale from Django admin',
            reason='Marked stale from Django admin',
        )
        self.message_user(request, f'Engine jobs stale: {updated}.')

    @admin.action(description='Пометить success')
    def mark_success(self, request, queryset):
        now = timezone.now()
        updated = queryset.update(
            status='success',
            progress_percent=100,
            heartbeat_at=now,
            finished_at=now,
            message='Marked success from Django admin',
            reason='',
        )
        self.message_user(request, f'Engine jobs success: {updated}.')


@admin.register(ProjectMeasurement)
class ProjectMeasurementAdmin(admin.ModelAdmin):
    list_display = (
        'project',
        'user',
        'metric',
        'value',
        'unit',
        'expected_value',
        'delta_display',
        'status',
        'created_at',
    )
    list_filter = ('metric', 'status', 'source', 'created_at')
    search_fields = ('project__name', 'user__username', 'metric', 'label')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('project', 'user', 'simulation_run')
    list_select_related = ('project', 'user', 'simulation_run')

    @admin.display(description='Δ')
    def delta_display(self, obj):
        if obj.expected_value is None:
            return ''
        delta = obj.value - obj.expected_value
        color = '#168a3a' if obj.status in {'ok', 'pass', 'within_tolerance'} else '#b8860b'
        if obj.status in {'fail', 'risk', 'out_of_range'}:
            color = '#b3261e'
        return format_html('<span style="color:{};">{:+.4g}</span>', color, delta)


@admin.register(ProjectReview)
class ProjectReviewAdmin(admin.ModelAdmin):
    list_display = ('project', 'user', 'score_badge', 'status_badge', 'findings_count', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('project__name', 'user__username', 'summary')
    readonly_fields = ('created_at', 'finding_summary')
    autocomplete_fields = ('project', 'user')
    list_select_related = ('project', 'user')
    date_hierarchy = 'created_at'
    actions = ('mark_ready', 'mark_needs_review', 'mark_risk', 'mark_critical')
    fieldsets = (
        (None, {'fields': ('project', 'user', 'score', 'status', 'summary', 'finding_summary')}),
        (
            'Findings',
            {'fields': ('errors', 'warnings', 'recommendations', 'faults'), 'classes': ('collapse',)},
        ),
        ('Metrics and sections', {'fields': ('metrics', 'sections'), 'classes': ('collapse',)}),
        ('Input snapshots', {'fields': ('scheme_data', 'import_summary'), 'classes': ('collapse',)}),
        ('Metadata', {'fields': ('created_at',), 'classes': ('collapse',)}),
    )

    @admin.display(description='Score', ordering='score')
    def score_badge(self, obj):
        color = '#168a3a'
        if obj.score < 70:
            color = '#b8860b'
        if obj.score < 45:
            color = '#b3261e'
        return format_html('<strong style="color:{};">{}/100</strong>', color, obj.score)

    @admin.display(description='Статус', ordering='status')
    def status_badge(self, obj):
        colors = {
            'ready': '#168a3a',
            'needs_review': '#b8860b',
            'risk': '#d66b00',
            'critical': '#b3261e',
        }
        return format_html(
            '<span style="color:{};font-weight:600;">{}</span>',
            colors.get(obj.status, '#555'),
            obj.get_status_display() if hasattr(obj, 'get_status_display') else obj.status,
        )

    @admin.display(description='Findings')
    def findings_count(self, obj):
        return sum(len(value or []) for value in (obj.errors, obj.warnings, obj.recommendations, obj.faults))

    @admin.display(description='Сводка findings')
    def finding_summary(self, obj):
        if not obj.pk:
            return 'Сохраните review, чтобы увидеть сводку.'
        return format_html(
            '<ul style="margin:0 0 0 1rem;">'
            '<li><strong>Ошибки:</strong> {}</li>'
            '<li><strong>Предупреждения:</strong> {}</li>'
            '<li><strong>Рекомендации:</strong> {}</li>'
            '<li><strong>Fault cases:</strong> {}</li>'
            '</ul>',
            len(obj.errors or []),
            len(obj.warnings or []),
            len(obj.recommendations or []),
            len(obj.faults or []),
        )

    @admin.action(description='Review status: ready')
    def mark_ready(self, request, queryset):
        updated = queryset.update(status='ready')
        self.message_user(request, f'Review ready: {updated}.')

    @admin.action(description='Review status: needs_review')
    def mark_needs_review(self, request, queryset):
        updated = queryset.update(status='needs_review')
        self.message_user(request, f'Review needs_review: {updated}.')

    @admin.action(description='Review status: risk')
    def mark_risk(self, request, queryset):
        updated = queryset.update(status='risk')
        self.message_user(request, f'Review risk: {updated}.')

    @admin.action(description='Review status: critical')
    def mark_critical(self, request, queryset):
        updated = queryset.update(status='critical')
        self.message_user(request, f'Review critical: {updated}.')


@admin.register(ProjectEvent)
class ProjectEventAdmin(admin.ModelAdmin):
    list_display = ('project', 'user', 'event_type', 'created_at')
    list_filter = ('event_type', 'created_at')
    search_fields = ('project__name', 'user__username', 'event_type')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('project', 'user')
    list_select_related = ('project', 'user')


def hide_content(modeladmin, request, queryset):
    queryset.update(
        moderation_status='hidden',
        moderation_reason='Admin bulk hide',
        moderated_by=request.user,
        moderated_at=timezone.now(),
    )


hide_content.short_description = 'Скрыть выбранное'


def restore_content(modeladmin, request, queryset):
    queryset.update(
        moderation_status='visible',
        moderation_reason='',
        moderated_by=request.user,
        moderated_at=timezone.now(),
    )


restore_content.short_description = 'Восстановить выбранное'


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'project', 'article', 'moderation_status', 'created_at')
    list_filter = ('moderation_status', 'is_rich', 'created_at')
    search_fields = ('body', 'user__username', 'project__name', 'article__title')
    readonly_fields = ('created_at', 'edited_at', 'moderated_at')
    autocomplete_fields = ('user', 'project', 'article', 'parent', 'moderated_by')
    list_select_related = ('user', 'project', 'article', 'parent', 'moderated_by')
    actions = (hide_content, restore_content)


@admin.register(EngineeringArtifact)
class EngineeringArtifactAdmin(admin.ModelAdmin):
    list_display = (
        'source_name',
        'project',
        'artifact_type',
        'status',
        'parser',
        'size_kb',
        'facts_count',
        'warnings_count',
        'errors_count',
        'created_at',
    )
    list_filter = ('artifact_type', 'status', 'parser', 'created_at')
    search_fields = ('source_name', 'source_path', 'summary', 'project__name')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('project', 'user')
    list_select_related = ('project', 'user')
    date_hierarchy = 'created_at'
    actions = (
        'mark_parsed',
        'mark_partial',
        'mark_unsupported',
        'create_training_examples',
    )

    @admin.display(description='KB', ordering='size_bytes')
    def size_kb(self, obj):
        return f'{obj.size_bytes / 1024:.1f}' if obj.size_bytes else '0'

    @admin.display(description='Facts')
    def facts_count(self, obj):
        return len(obj.facts or {})

    @admin.display(description='Warn')
    def warnings_count(self, obj):
        return len(obj.warnings or [])

    @admin.display(description='Err')
    def errors_count(self, obj):
        return len(obj.errors or [])

    @admin.action(description='Статус: parsed')
    def mark_parsed(self, request, queryset):
        updated = queryset.update(status='parsed')
        self.message_user(request, f'Артефактов помечено parsed: {updated}.')

    @admin.action(description='Статус: partial')
    def mark_partial(self, request, queryset):
        updated = queryset.update(status='partial')
        self.message_user(request, f'Артефактов помечено partial: {updated}.')

    @admin.action(description='Статус: unsupported')
    def mark_unsupported(self, request, queryset):
        updated = queryset.update(status='unsupported')
        self.message_user(request, f'Артефактов помечено unsupported: {updated}.')

    @admin.action(description='Создать AI examples из summary')
    def create_training_examples(self, request, queryset):
        created = 0
        skipped = 0
        for artifact in queryset.select_related('project', 'user'):
            summary = (artifact.summary or '').strip()
            if not summary:
                skipped += 1
                continue
            AITrainingExample.objects.get_or_create(
                artifact=artifact,
                project=artifact.project,
                kind='artifact_summary',
                prompt=f'Кратко объясни инженерный артефакт: {artifact.source_name}',
                defaults={
                    'user': artifact.user,
                    'target': summary[:4000],
                    'features': {
                        'artifact_type': artifact.artifact_type,
                        'parser': artifact.parser,
                        'status': artifact.status,
                        'evidence_kind': 'engineering_artifact',
                    },
                },
            )
            created += 1
        self.message_user(
            request, f'AI examples создано/найдено: {created}; пропущено без summary: {skipped}.'
        )


@admin.register(AITrainingExample)
class AITrainingExampleAdmin(admin.ModelAdmin):
    list_display = (
        'kind',
        'dataset_kind',
        'graph_ready',
        'prompt_preview',
        'project',
        'artifact',
        'feature_sources',
        'is_validated',
        'created_at',
    )
    list_filter = ('kind', 'is_validated', 'created_at')
    search_fields = ('prompt', 'target', 'project__name', 'artifact__source_name')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('artifact', 'project', 'user')
    list_select_related = ('artifact', 'project', 'user')
    date_hierarchy = 'created_at'
    change_list_template = 'admin/dolg_app/aitrainingexample/change_list.html'
    actions = (
        'normalize_metadata',
        'exclude_from_graph_training',
        'mark_validated',
        'mark_unvalidated',
        'promote_to_private_projects',
        'promote_to_demo_projects',
    )

    def changelist_view(self, request, extra_context=None):
        from Dolg_APP.services.ai_training import (
            summarize_ai_training_examples,
            validate_ai_training_examples,
        )

        summary = summarize_ai_training_examples()
        validation = validate_ai_training_examples(limit=500)
        extra_context = extra_context or {}
        extra_context['ai_dataset_dashboard'] = summary
        extra_context['ai_dataset_validation'] = {
            'ok': validation['ok'],
            'scanned': validation['scanned'],
            'errors_count': validation['errors_count'],
            'warnings_count': validation['warnings_count'],
        }
        return super().changelist_view(request, extra_context=extra_context)

    @admin.display(description='Prompt')
    def prompt_preview(self, obj):
        return obj.prompt[:90]

    @admin.display(description='Dataset')
    def dataset_kind(self, obj):
        return (obj.features or {}).get('dataset_kind') or 'unclassified'

    @admin.display(description='Graph')
    def graph_ready(self, obj):
        return 'yes' if (obj.features or {}).get('graph_training_ready') else 'no'

    @admin.display(description='Sources')
    def feature_sources(self, obj):
        features = obj.features or {}
        source_ids = features.get('source_ids') or []
        teacher_rules = features.get('teacher_rules') or []
        labels = [*source_ids[:2], *teacher_rules[:2]]
        return ', '.join(labels) if labels else ''

    @admin.action(description='Normalize dataset metadata')
    def normalize_metadata(self, request, queryset):
        from Dolg_APP.services.ai_training import normalize_ai_training_example

        scanned = changed = graph_ready = 0
        for example in queryset:
            scanned += 1
            result = normalize_ai_training_example(example)
            changed += int(bool(result.get('changed')))
            graph_ready += int(bool(result.get('graph_training_ready')))
        self.message_user(
            request,
            f'AI examples normalized: scanned={scanned}, changed={changed}, graph_ready={graph_ready}.',
        )

    @admin.action(description='Exclude selected from graph training')
    def exclude_from_graph_training(self, request, queryset):
        updated = 0
        for example in queryset:
            features = dict(example.features or {})
            features['graph_training_ready'] = False
            features['training_role'] = 'retrieval_context'
            features['graph_excluded_by_admin'] = True
            features['graph_excluded_reason'] = 'Excluded from Django admin'
            example.features = features
            example.save(update_fields=['features'])
            updated += 1
        self.message_user(request, f'AI examples excluded from graph training: {updated}.')

    @admin.action(description='Подтвердить для обучения')
    def mark_validated(self, request, queryset):
        updated = queryset.update(is_validated=True)
        self.message_user(request, f'AI examples подтверждено: {updated}.')

    @admin.action(description='Снять подтверждение')
    def mark_unvalidated(self, request, queryset):
        updated = queryset.update(is_validated=False)
        self.message_user(request, f'AI examples снято с обучения: {updated}.')

    @admin.action(description='Create private projects from selected AI examples')
    def promote_to_private_projects(self, request, queryset):
        from Dolg_APP.services.ai_training import promote_ai_examples_to_projects

        result = promote_ai_examples_to_projects(
            owner=request.user,
            example_ids=list(queryset.values_list('id', flat=True)),
            visibility='private',
            approval_state='draft',
            is_demo=False,
            min_quality=60,
            validated_only=False,
        )
        self.message_user(
            request,
            f'Projects created={result["created"]}, updated={result["updated"]}, '
            f'skipped quality={result["skipped_quality"]}.',
        )

    @admin.action(description='Create public demo projects from selected AI examples')
    def promote_to_demo_projects(self, request, queryset):
        from Dolg_APP.services.ai_training import promote_ai_examples_to_projects

        result = promote_ai_examples_to_projects(
            owner=request.user,
            example_ids=list(queryset.values_list('id', flat=True)),
            visibility='public',
            approval_state='approved',
            is_demo=True,
            min_quality=68,
            validated_only=False,
        )
        self.message_user(
            request,
            f'Demo projects created={result["created"]}, updated={result["updated"]}, '
            f'skipped quality={result["skipped_quality"]}.',
        )


@admin.register(MLJob)
class MLJobAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'job_type',
        'status_badge',
        'progress_percent',
        'source',
        'processed',
        'created_count',
        'updated_count',
        'skipped_count',
        'created_by',
        'started_at',
        'heartbeat_at',
        'finished_at',
    )
    list_filter = ('job_type', 'status', 'source', 'created_at', 'finished_at')
    search_fields = ('source', 'message', 'error', 'stdout_tail', 'created_by__username', 'created_by__email')
    readonly_fields = (
        'created_at',
        'updated_at',
        'started_at',
        'heartbeat_at',
        'finished_at',
        'stdout_tail',
        'error',
    )
    autocomplete_fields = ('created_by',)
    list_select_related = ('created_by',)
    date_hierarchy = 'created_at'
    actions = ('mark_cancelled', 'mark_stale', 'mark_success')

    @admin.display(description='Status', ordering='status')
    def status_badge(self, obj):
        colors = {
            'queued': '#6b7280',
            'running': '#2563eb',
            'success': '#168a3a',
            'error': '#b3261e',
            'cancelled': '#7c3aed',
            'stale': '#b8860b',
        }
        return format_html(
            '<strong style="color:{};">{}</strong>',
            colors.get(obj.status, '#555'),
            obj.status,
        )

    @admin.action(description='Mark selected jobs cancelled')
    def mark_cancelled(self, request, queryset):
        now = timezone.now()
        updated = queryset.update(
            status='cancelled',
            heartbeat_at=now,
            finished_at=now,
            message='Cancelled from Django admin',
        )
        self.message_user(request, f'ML jobs cancelled: {updated}.')

    @admin.action(description='Mark selected jobs stale')
    def mark_stale(self, request, queryset):
        now = timezone.now()
        updated = queryset.update(
            status='stale',
            heartbeat_at=now,
            finished_at=now,
            message='Marked stale from Django admin',
        )
        self.message_user(request, f'ML jobs marked stale: {updated}.')

    @admin.action(description='Mark selected jobs success')
    def mark_success(self, request, queryset):
        now = timezone.now()
        updated = queryset.update(
            status='success',
            progress_percent=100,
            heartbeat_at=now,
            finished_at=now,
            message='Marked success from Django admin',
        )
        self.message_user(request, f'ML jobs marked success: {updated}.')


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'level', 'is_published', 'is_pinned', 'expires_at', 'created_at')
    list_filter = ('level', 'is_published', 'is_pinned', 'created_at')
    list_editable = ('is_published', 'is_pinned')
    search_fields = ('title', 'body')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'
    actions = ('publish', 'unpublish', 'pin', 'unpin', 'expire_now')
    fieldsets = (
        (None, {'fields': ('title', 'body', 'level')}),
        ('Публикация', {'fields': ('is_published', 'is_pinned', 'expires_at')}),
        ('Служебное', {'fields': ('author', 'created_at'), 'classes': ('collapse',)}),
    )

    def save_model(self, request, obj, form, change):
        if not obj.author_id:
            obj.author = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description='Опубликовать объявления')
    def publish(self, request, queryset):
        updated = queryset.update(is_published=True)
        self.message_user(request, f'Объявлений опубликовано: {updated}.')

    @admin.action(description='Снять с публикации')
    def unpublish(self, request, queryset):
        updated = queryset.update(is_published=False)
        self.message_user(request, f'Объявлений скрыто: {updated}.')

    @admin.action(description='Закрепить')
    def pin(self, request, queryset):
        updated = queryset.update(is_pinned=True)
        self.message_user(request, f'Объявлений закреплено: {updated}.')

    @admin.action(description='Открепить')
    def unpin(self, request, queryset):
        updated = queryset.update(is_pinned=False)
        self.message_user(request, f'Объявлений откреплено: {updated}.')

    @admin.action(description='Истечь сейчас')
    def expire_now(self, request, queryset):
        updated = queryset.update(expires_at=timezone.now())
        self.message_user(request, f'Объявлений завершено: {updated}.')


@admin.register(ChatTopic)
class ChatTopicAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'author',
        'category',
        'moderation_status',
        'is_pinned',
        'is_resolved',
        'views_count',
        'last_activity_at',
    )
    list_filter = ('category', 'moderation_status', 'is_pinned', 'is_resolved', 'created_at')
    search_fields = ('title', 'body', 'author__username')
    readonly_fields = ('views_count', 'created_at', 'updated_at', 'last_activity_at', 'moderated_at')
    autocomplete_fields = ('author', 'attached_project', 'moderated_by')
    list_select_related = ('author', 'attached_project', 'moderated_by')
    actions = (hide_content, restore_content)


@admin.register(ChatReply)
class ChatReplyAdmin(admin.ModelAdmin):
    list_display = ('topic', 'author', 'moderation_status', 'is_accepted_answer', 'created_at')
    list_filter = ('moderation_status', 'is_accepted_answer', 'created_at')
    search_fields = ('body', 'author__username', 'topic__title')
    readonly_fields = ('created_at', 'updated_at', 'moderated_at')
    autocomplete_fields = ('topic', 'author', 'parent', 'moderated_by')
    list_select_related = ('topic', 'author', 'parent', 'moderated_by')
    actions = (hide_content, restore_content)


@admin.register(OrgConversation)
class OrgConversationAdmin(admin.ModelAdmin):
    list_display = ('title', 'organization', 'created_by', 'is_archived', 'last_activity_at')
    list_filter = ('is_archived', 'created_at')
    search_fields = ('title', 'description', 'organization__name')
    readonly_fields = ('created_at', 'updated_at', 'last_activity_at')
    autocomplete_fields = ('created_by', 'attached_project')
    list_select_related = ('organization', 'created_by', 'attached_project')


@admin.register(OrgConversationMessage)
class OrgConversationMessageAdmin(admin.ModelAdmin):
    list_display = ('conversation', 'author', 'moderation_status', 'created_at', 'is_edited')
    list_filter = ('moderation_status', 'is_edited', 'created_at')
    search_fields = ('body', 'author__username')
    readonly_fields = ('created_at', 'updated_at', 'moderated_at')
    autocomplete_fields = ('conversation', 'author', 'parent', 'moderated_by')
    list_select_related = ('conversation', 'author', 'parent', 'moderated_by')
    actions = (hide_content, restore_content)
