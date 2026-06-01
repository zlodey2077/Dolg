from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class ModerationCase(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_review', 'In review'),
        ('resolved', 'Resolved'),
        ('rejected', 'Rejected'),
    ]
    SCOPE_CHOICES = [
        ('global', 'Global'),
        ('organization', 'Organization'),
    ]

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=64)
    target = GenericForeignKey('content_type', 'object_id')
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default='global', db_index=True)
    organization = models.ForeignKey(
        'Dolg_APP.Organization',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='moderation_cases',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open', db_index=True)
    summary = models.CharField(max_length=240, blank=True)
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='opened_moderation_cases',
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_moderation_cases',
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['scope', 'status']),
            models.Index(fields=['content_type', 'object_id']),
        ]
        verbose_name = 'Moderation case'
        verbose_name_plural = 'Moderation cases'

    def __str__(self):
        return f'case #{self.id}: {self.content_type}:{self.object_id} ({self.status})'

    @classmethod
    def get_or_open(cls, *, target, reporter=None, organization=None, summary=''):
        content_type = ContentType.objects.get_for_model(target, for_concrete_model=False)
        scope = 'organization' if organization else 'global'
        case, created = cls.objects.get_or_create(
            content_type=content_type,
            object_id=str(target.pk),
            status__in=['open', 'in_review'],
            defaults={
                'scope': scope,
                'organization': organization,
                'opened_by': reporter if getattr(reporter, 'is_authenticated', False) else None,
                'summary': summary[:240],
            },
        )
        if not created and not case.organization_id and organization:
            case.organization = organization
            case.scope = 'organization'
            case.save(update_fields=['organization', 'scope', 'updated_at'])
        return case


class ModerationReport(models.Model):
    STATUS_CHOICES = [
        ('new', 'New'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('duplicate', 'Duplicate'),
    ]
    REASON_CHOICES = [
        ('spam', 'Spam'),
        ('abuse', 'Abuse'),
        ('unsafe', 'Unsafe'),
        ('wrong_data', 'Wrong data'),
        ('offtopic', 'Offtopic'),
        ('other', 'Other'),
    ]

    case = models.ForeignKey(ModerationCase, on_delete=models.CASCADE, related_name='reports')
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='moderation_reports',
    )
    reason = models.CharField(max_length=32, choices=REASON_CHOICES, default='other')
    details = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', '-created_at'])]
        verbose_name = 'Moderation report'
        verbose_name_plural = 'Moderation reports'

    def __str__(self):
        return f'report #{self.id}: {self.reason} ({self.status})'


class ModerationAction(models.Model):
    ACTION_CHOICES = [
        ('hide', 'Hide'),
        ('restore', 'Restore'),
        ('remove', 'Remove'),
        ('warn', 'Warn'),
        ('mute', 'Mute'),
        ('ban', 'Ban'),
        ('read_only', 'Read only'),
        ('mark_reviewed', 'Mark reviewed'),
        ('reject_report', 'Reject report'),
    ]

    case = models.ForeignKey(ModerationCase, on_delete=models.CASCADE, related_name='actions')
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='moderation_actions',
    )
    action_type = models.CharField(max_length=32, choices=ACTION_CHOICES, db_index=True)
    reason = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['action_type', '-created_at'])]
        verbose_name = 'Moderation action'
        verbose_name_plural = 'Moderation actions'

    def __str__(self):
        return f'{self.action_type} on case #{self.case_id}'


class UserRestriction(models.Model):
    RESTRICTION_CHOICES = [
        ('mute', 'Mute'),
        ('ban', 'Ban'),
        ('read_only', 'Read only'),
    ]
    SCOPE_CHOICES = [
        ('global', 'Global'),
        ('organization', 'Organization'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='restrictions')
    restriction_type = models.CharField(max_length=20, choices=RESTRICTION_CHOICES, db_index=True)
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default='global', db_index=True)
    organization = models.ForeignKey(
        'Dolg_APP.Organization',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='user_restrictions',
    )
    reason = models.TextField(blank=True)
    starts_at = models.DateTimeField(default=timezone.now, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    lifted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_user_restrictions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'restriction_type', 'scope']),
            models.Index(fields=['scope', 'organization']),
        ]
        verbose_name = 'User restriction'
        verbose_name_plural = 'User restrictions'

    def __str__(self):
        return f'{self.user_id}: {self.restriction_type}/{self.scope}'

    def is_active(self):
        now = timezone.now()
        if self.lifted_at:
            return False
        if self.starts_at and self.starts_at > now:
            return False
        if self.expires_at and self.expires_at <= now:
            return False
        return True


class ModerationRule(models.Model):
    SCOPE_CHOICES = [
        ('global', 'Global'),
        ('organization', 'Organization'),
    ]

    name = models.CharField(max_length=160)
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default='global')
    organization = models.ForeignKey(
        'Dolg_APP.Organization',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='moderation_rules',
    )
    applies_to = models.CharField(max_length=80, blank=True, help_text='Example: comment, chat, product')
    action = models.CharField(max_length=80, blank=True, help_text='Example: hide, warn, needs_review')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_moderation_rules',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['scope', 'name']
        verbose_name = 'Moderation rule'
        verbose_name_plural = 'Moderation rules'

    def __str__(self):
        return self.name
