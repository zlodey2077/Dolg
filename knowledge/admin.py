from django.contrib import admin
from django.db.models import Count
from django.utils.text import slugify

from .models import (
    Article,
    ArticleMaterial,
    KnowledgeCategory,
    LearningAttempt,
    LearningLesson,
    LearningProgress,
    LearningTask,
    LearningTrack,
)


# Стандартный prepopulated_fields в admin использует slugify только по ASCII —
# для русских названий он отбрасывает все буквы и slug получается пустой.
# В save_model доавтогенерируем кириллический slug через allow_unicode=True.
class _UnicodeSlugMixin:
    SLUG_SOURCE = ''  # имя поля-источника (title/name)

    def save_model(self, request, obj, form, change):
        if not obj.slug and self.SLUG_SOURCE:
            src = getattr(obj, self.SLUG_SOURCE, '') or ''
            obj.slug = slugify(src, allow_unicode=True)[:100]
        super().save_model(request, obj, form, change)


@admin.register(KnowledgeCategory)
class KnowledgeCategoryAdmin(_UnicodeSlugMixin, admin.ModelAdmin):
    SLUG_SOURCE = 'name'
    list_display = ('name', 'topic', 'icon', 'order', 'articles_count')
    list_editable = ('order',)
    list_filter = ('topic',)
    search_fields = ('name', 'description')

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_articles_count=Count('articles'))

    @admin.display(description='Статей', ordering='_articles_count')
    def articles_count(self, obj):
        return getattr(obj, '_articles_count', 0)


class ArticleMaterialInline(admin.TabularInline):
    model = ArticleMaterial
    extra = 1
    fields = ('material_type', 'title', 'description', 'url', 'file', 'order', 'is_public')


@admin.register(Article)
class ArticleAdmin(_UnicodeSlugMixin, admin.ModelAdmin):
    SLUG_SOURCE = 'title'
    list_display = ('title', 'category', 'is_published', 'reading_minutes', 'order', 'updated_at')
    list_editable = ('is_published', 'order')
    list_filter = ('category', 'is_published')
    search_fields = ('title', 'summary', 'body')
    autocomplete_fields = ('category',)
    readonly_fields = ('created_at', 'updated_at')
    list_select_related = ('category',)
    date_hierarchy = 'updated_at'
    inlines = (ArticleMaterialInline,)
    fieldsets = (
        (None, {'fields': ('category', 'title', 'slug', 'is_published', 'order')}),
        ('Содержимое', {'fields': ('summary', 'body', 'reading_minutes')}),
        ('Связь с каталогом', {'fields': ('related_components_note',)}),
        ('Служебное', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(ArticleMaterial)
class ArticleMaterialAdmin(admin.ModelAdmin):
    list_display = ('title', 'article', 'material_type', 'is_public', 'order')
    list_editable = ('is_public', 'order')
    list_filter = ('material_type', 'is_public')
    search_fields = ('title', 'description', 'article__title')
    autocomplete_fields = ('article',)
    list_select_related = ('article',)


class LearningTaskInline(admin.TabularInline):
    model = LearningTask
    extra = 1
    fields = ('task_type', 'title', 'prompt', 'rubric', 'order', 'is_required')


@admin.register(LearningTrack)
class LearningTrackAdmin(_UnicodeSlugMixin, admin.ModelAdmin):
    SLUG_SOURCE = 'title'
    list_display = ('title', 'level', 'is_published', 'order', 'lessons_count', 'updated_at')
    list_editable = ('is_published', 'order')
    list_filter = ('level', 'is_published')
    search_fields = ('title', 'summary')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'updated_at'

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_lessons_count=Count('lessons'))

    @admin.display(description='Уроков', ordering='_lessons_count')
    def lessons_count(self, obj):
        return getattr(obj, '_lessons_count', 0)


@admin.register(LearningLesson)
class LearningLessonAdmin(_UnicodeSlugMixin, admin.ModelAdmin):
    SLUG_SOURCE = 'title'
    list_display = ('title', 'track', 'is_published', 'estimated_minutes', 'order', 'updated_at')
    list_editable = ('is_published', 'order')
    list_filter = ('track', 'is_published')
    search_fields = ('title', 'summary', 'theory', 'formula')
    autocomplete_fields = ('track', 'article', 'demo_project')
    readonly_fields = ('created_at', 'updated_at')
    list_select_related = ('track', 'article', 'demo_project')
    date_hierarchy = 'updated_at'
    inlines = (LearningTaskInline,)
    fieldsets = (
        (None, {'fields': ('track', 'title', 'slug', 'is_published', 'order')}),
        ('Содержимое', {'fields': ('summary', 'theory', 'formula', 'estimated_minutes')}),
        ('Связи', {'fields': ('article', 'demo_project', 'action_url', 'action_label')}),
        ('Служебное', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(LearningTask)
class LearningTaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'lesson', 'task_type', 'is_required', 'order')
    list_editable = ('is_required', 'order')
    list_filter = ('task_type', 'is_required', 'lesson__track')
    search_fields = ('title', 'prompt', 'lesson__title')
    autocomplete_fields = ('lesson',)
    list_select_related = ('lesson', 'lesson__track')


@admin.register(LearningAttempt)
class LearningAttemptAdmin(admin.ModelAdmin):
    list_display = ('user', 'task', 'is_correct', 'score', 'created_at')
    list_filter = ('is_correct', 'task__task_type', 'created_at')
    search_fields = ('user__username', 'task__title', 'feedback')
    autocomplete_fields = ('user', 'task')
    readonly_fields = ('created_at',)
    list_select_related = ('user', 'task', 'task__lesson')
    date_hierarchy = 'created_at'


@admin.register(LearningProgress)
class LearningProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'lesson', 'is_completed', 'updated_at')
    list_filter = ('completed_at', 'lesson__track')
    search_fields = ('user__username', 'lesson__title')
    autocomplete_fields = ('user', 'lesson')
    readonly_fields = ('updated_at',)
    list_select_related = ('user', 'lesson', 'lesson__track')
    date_hierarchy = 'updated_at'
