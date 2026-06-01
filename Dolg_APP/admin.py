from django.contrib import admin
from django.db.models import Count
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    Announcement,
    AITrainingExample,
    ChatReply,
    ChatTopic,
    Comment,
    EngineeringArtifact,
    AuditLog,
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
        'name', 'user', 'organization', 'category', 'status', 'approval_state',
        'visibility', 'difficulty', 'versions_count', 'runs_count',
        'reviews_count', 'measurements_count', 'updated_at',
    )
    list_filter = (
        'category', 'status', 'approval_state', 'visibility', 'difficulty',
        'is_demo', 'created_at', 'updated_at',
    )
    search_fields = ('name', 'description', 'user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
    list_select_related = ('user', 'organization')
    change_list_template = 'admin/dolg_app/schematicproject/change_list.html'
    fieldsets = (
        (None, {'fields': ('user', 'organization', 'name', 'description')}),
        ('Классификация', {'fields': ('category', 'status', 'approval_state', 'visibility', 'difficulty', 'is_demo')}),
        ('Публикация и доступ', {'fields': ('share_token', 'deleted_at'), 'classes': ('collapse',)}),
        ('Данные схемы', {'fields': ('scheme_data',), 'classes': ('collapse',)}),
        ('Метаданные', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
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
    list_display = ('project', 'user', 'analysis_type', 'engine', 'elapsed_ms', 'progress_badge', 'status', 'created_at')
    list_filter = ('analysis_type', 'engine', 'status', 'created_at')
    search_fields = ('project__name', 'user__username', 'netlist')
    readonly_fields = ('created_at', 'started_at', 'finished_at')
    autocomplete_fields = ('project', 'user')
    list_select_related = ('project', 'user')

    @admin.display(description='Прогресс')
    def progress_badge(self, obj):
        color = '#168a3a' if obj.status == 'success' else '#b8860b'
        if obj.status == 'error':
            color = '#b3261e'
        return format_html('<strong style="color:{};">{}%</strong>', color, obj.progress_percent)


@admin.register(ProjectMeasurement)
class ProjectMeasurementAdmin(admin.ModelAdmin):
    list_display = ('project', 'user', 'metric', 'value', 'unit', 'expected_value', 'delta_display', 'status', 'created_at')
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
    fieldsets = (
        (None, {'fields': ('project', 'user', 'score', 'status', 'summary', 'finding_summary')}),
        ('Findings', {'fields': ('errors', 'warnings', 'recommendations', 'faults'), 'classes': ('collapse',)}),
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
        'source_name', 'project', 'artifact_type', 'status', 'parser',
        'size_kb', 'facts_count', 'warnings_count', 'errors_count', 'created_at',
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
        self.message_user(request, f'AI examples создано/найдено: {created}; пропущено без summary: {skipped}.')


@admin.register(AITrainingExample)
class AITrainingExampleAdmin(admin.ModelAdmin):
    list_display = ('kind', 'prompt_preview', 'project', 'artifact', 'feature_sources', 'is_validated', 'created_at')
    list_filter = ('kind', 'is_validated', 'created_at')
    search_fields = ('prompt', 'target', 'project__name', 'artifact__source_name')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('artifact', 'project', 'user')
    list_select_related = ('artifact', 'project', 'user')
    date_hierarchy = 'created_at'
    change_list_template = 'admin/dolg_app/aitrainingexample/change_list.html'
    actions = ('mark_validated', 'mark_unvalidated', 'promote_to_private_projects', 'promote_to_demo_projects')

    def changelist_view(self, request, extra_context=None):
        from Dolg_APP.services.ai_training import summarize_ai_training_examples, validate_ai_training_examples

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

    @admin.display(description='Sources')
    def feature_sources(self, obj):
        features = obj.features or {}
        source_ids = features.get('source_ids') or []
        teacher_rules = features.get('teacher_rules') or []
        labels = [*source_ids[:2], *teacher_rules[:2]]
        return ', '.join(labels) if labels else ''

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
            f"Projects created={result['created']}, updated={result['updated']}, "
            f"skipped quality={result['skipped_quality']}."
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
            f"Demo projects created={result['created']}, updated={result['updated']}, "
            f"skipped quality={result['skipped_quality']}."
        )


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'level', 'is_published', 'is_pinned', 'expires_at', 'created_at')
    list_filter = ('level', 'is_published', 'is_pinned', 'created_at')
    search_fields = ('title', 'body')
    readonly_fields = ('created_at',)
    fieldsets = (
        (None, {'fields': ('title', 'body', 'level')}),
        ('Публикация', {'fields': ('is_published', 'is_pinned', 'expires_at')}),
        ('Служебное', {'fields': ('author', 'created_at'), 'classes': ('collapse',)}),
    )

    def save_model(self, request, obj, form, change):
        if not obj.author_id:
            obj.author = request.user
        super().save_model(request, obj, form, change)


@admin.register(ChatTopic)
class ChatTopicAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'category', 'moderation_status', 'is_pinned', 'is_resolved', 'views_count', 'last_activity_at')
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
