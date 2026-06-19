from django.contrib import admin
from django.utils import timezone

from .models import (
    ModerationAction,
    ModerationCase,
    ModerationReport,
    ModerationRule,
    UserRestriction,
)
from .services import apply_action


@admin.action(description='Hide selected targets')
def hide_cases(modeladmin, request, queryset):
    for case in queryset:
        apply_action(case=case, actor=request.user, action_type='hide', reason='Bulk hide from admin')


@admin.action(description='Restore selected targets')
def restore_cases(modeladmin, request, queryset):
    for case in queryset:
        apply_action(case=case, actor=request.user, action_type='restore', reason='Bulk restore from admin')


@admin.action(description='Reject selected reports')
def reject_cases(modeladmin, request, queryset):
    for case in queryset:
        apply_action(
            case=case, actor=request.user, action_type='reject_report', reason='Bulk reject from admin'
        )


@admin.action(description='Assign selected cases to me')
def assign_cases_to_me(modeladmin, request, queryset):
    updated = queryset.update(assigned_to=request.user, status='in_review')
    modeladmin.message_user(request, f'Cases assigned to you: {updated}.')


@admin.action(description='Close selected cases as resolved')
def resolve_cases(modeladmin, request, queryset):
    updated = queryset.update(status='resolved', resolved_at=timezone.now())
    modeladmin.message_user(request, f'Cases resolved: {updated}.')


@admin.action(description='Reopen selected cases')
def reopen_cases(modeladmin, request, queryset):
    updated = queryset.update(status='open', resolved_at=None)
    modeladmin.message_user(request, f'Cases reopened: {updated}.')


@admin.register(ModerationCase)
class ModerationCaseAdmin(admin.ModelAdmin):
    list_display = ('id', 'summary', 'status', 'scope', 'organization', 'target_label', 'created_at')
    list_filter = ('status', 'scope', 'created_at')
    search_fields = ('summary', 'object_id', 'organization__name')
    readonly_fields = ('created_at', 'updated_at', 'resolved_at')
    autocomplete_fields = ('opened_by', 'assigned_to', 'organization')
    list_select_related = ('opened_by', 'assigned_to', 'organization')
    actions = (assign_cases_to_me, resolve_cases, reopen_cases, hide_cases, restore_cases, reject_cases)
    date_hierarchy = 'created_at'

    def target_label(self, obj):
        return str(obj.target)[:80] if obj.target is not None else ''


@admin.register(ModerationReport)
class ModerationReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'case', 'reporter', 'reason', 'status', 'created_at')
    list_filter = ('reason', 'status', 'created_at')
    search_fields = ('details', 'reporter__username', 'case__summary')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('case', 'reporter')
    list_select_related = ('case', 'reporter')
    date_hierarchy = 'created_at'


@admin.register(ModerationAction)
class ModerationActionAdmin(admin.ModelAdmin):
    list_display = ('id', 'case', 'actor', 'action_type', 'created_at')
    list_filter = ('action_type', 'created_at')
    search_fields = ('reason', 'actor__username', 'case__summary')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('case', 'actor')
    list_select_related = ('case', 'actor')
    date_hierarchy = 'created_at'


@admin.register(UserRestriction)
class UserRestrictionAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'restriction_type',
        'scope',
        'organization',
        'starts_at',
        'expires_at',
        'lifted_at',
    )
    list_filter = ('restriction_type', 'scope', 'created_at', 'lifted_at')
    search_fields = ('user__username', 'user__email', 'reason')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('user', 'organization', 'created_by')
    list_select_related = ('user', 'organization', 'created_by')
    date_hierarchy = 'created_at'


@admin.register(ModerationRule)
class ModerationRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'scope', 'organization', 'applies_to', 'action', 'is_active', 'updated_at')
    list_filter = ('scope', 'is_active', 'applies_to')
    search_fields = ('name', 'description', 'applies_to', 'action')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ('organization', 'created_by')
    list_select_related = ('organization', 'created_by')
