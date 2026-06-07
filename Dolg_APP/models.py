import hashlib
import hmac
import secrets

from django.conf import settings
from django.conf import settings as django_settings
from django.db import models
from django.utils import timezone

MODERATION_STATUS_CHOICES = [
    ('visible', 'Видимый'),
    ('pending', 'На проверке'),
    ('hidden', 'Скрыт'),
    ('removed', 'Удален модератором'),
]


class Subscription(models.Model):
    """Подписка пользователя на Pro-tier.

    Tier-логика:
    - Если у юзера нет Subscription → tier='free'
    - Если есть, и status='active' / 'trial', и period_end > now → tier='pro'
    - Иначе → tier='free' (мягкая деградация при истечении)

    Биллинг mock-only (нет реального Stripe/CloudPayments):
    - provider='manual' — вручную выдан админом
    - provider='trial' — 14-дневный пробный период (один раз на email)
    - provider='stripe' / 'cloudpayments' — задел на будущее

    Auto-renew: при истечении period_end management-команда
    expire_subscriptions либо продлевает (если стоит флаг и есть реальный
    payment provider), либо помечает status='expired'.
    """

    TIER_CHOICES = [
        ('free', 'Free'),
        ('pro', 'Pro'),
    ]
    STATUS_CHOICES = [
        ('trial', 'Пробный период'),
        ('active', 'Активна'),
        ('cancelled', 'Отменена (доступ до конца периода)'),
        ('expired', 'Истекла'),
    ]
    PROVIDER_CHOICES = [
        ('trial', '14-дневный trial'),
        ('manual', 'Выдано админом'),
        ('stripe', 'Stripe'),
        ('cloudpayments', 'CloudPayments'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscription',
        null=True,
        blank=True,  # null если подписка корпоративная (на org, не на user)
    )
    # Корпоративная подписка: один Subscription per organization. Free/Pro user-only
    # подписки имеют user но НЕ имеют organization. Enterprise — наоборот.
    organization = models.OneToOneField(
        'Dolg_APP.Organization',
        on_delete=models.CASCADE,
        related_name='subscription',
        null=True,
        blank=True,
    )
    tier = models.CharField(max_length=10, choices=TIER_CHOICES, default='free')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='active')
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default='manual')
    period_start = models.DateTimeField(auto_now_add=True)
    period_end = models.DateTimeField(null=True, blank=True, db_index=True)
    auto_renew = models.BooleanField(default=False)
    trial_used = models.BooleanField(
        default=False,
        help_text='Trial уже использован — повторно нельзя на этот аккаунт.',
    )
    # Stripe идентификаторы — заполняются после первого Checkout Session.
    # При manual/trial provider остаются пустыми. Используются для:
    #  - идемпотентного матчинга webhook-событий (sub.id → наш Subscription);
    #  - возможности Stripe-CLI/dashboard скорректировать конкретную подписку;
    #  - cancel-flow (сейчас cancel у нас локальный, при live-Stripe нужен
    #    stripe.Subscription.delete(stripe_subscription_id)).
    stripe_customer_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    stripe_subscription_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Подписка'
        verbose_name_plural = 'Подписки'

    def __str__(self):
        return f'{self.user.username}: {self.tier}/{self.status} until {self.period_end}'

    def is_pro_active(self) -> bool:
        """True если юзер имеет активный Pro-доступ ПРЯМО СЕЙЧАС."""
        from django.utils import timezone

        if self.tier != 'pro':
            return False
        if self.status == 'expired':
            return False
        if self.period_end is None:
            return True  # unlimited (например, admin-grant)
        return self.period_end > timezone.now()

    def days_left(self) -> int:
        """Сколько дней до истечения. None если бессрочно."""
        from django.utils import timezone

        if self.period_end is None:
            return None
        delta = self.period_end - timezone.now()
        return max(0, delta.days)


class DailyUsage(models.Model):
    """Дневной счётчик квот-зависимых действий юзера (симуляции, AI).
    Запись per-user-per-day; reset происходит автоматически в 00:00
    локального времени сервера (для DOLG — Europe/Moscow).

    Используется в Dolg_APP/quotas.py через get_or_create по (user, date).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='daily_usage',
    )
    date = models.DateField(default=timezone.localdate, db_index=True)
    simulations_count = models.PositiveIntegerField(default=0)
    ai_requests_count = models.PositiveIntegerField(default=0)
    chat_topics_count = models.PositiveIntegerField(default=0)
    chat_replies_count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('user', 'date')
        indexes = [models.Index(fields=['user', '-date'])]
        verbose_name = 'Дневная активность'
        verbose_name_plural = 'Дневная активность'

    def __str__(self):
        return (
            f'{self.user_id} @ {self.date}: '
            f'sim={self.simulations_count}, ai={self.ai_requests_count}, '
            f'chat_t={self.chat_topics_count}, chat_r={self.chat_replies_count}'
        )

    @classmethod
    def get_today(cls, user):
        """Атомарно возвращает (или создаёт) запись на сегодня."""
        obj, _ = cls.objects.get_or_create(user=user, date=timezone.localdate())
        return obj


class Organization(models.Model):
    """Корпоративный workspace (Enterprise tier).

    Один Org = одна команда/компания. У организации есть owner (создатель),
    members (с ролями), общие проекты (через SchematicProject.organization FK).
    Биллинг централизованный — Subscription.organization связана с Org,
    а не с user'ом.

    Plan-tier'ы:
    - 'team' (self-serve, до 10 seats)
    - 'business' (sales-led, 10-100 seats)
    - 'enterprise' (custom, 100+ seats, SOC2/ISO compliance)
    """

    PLAN_CHOICES = [
        ('team', 'Team (до 10 seats)'),
        ('business', 'Business (10-100 seats)'),
        ('enterprise', 'Enterprise (∞ seats)'),
    ]

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True, db_index=True)
    billing_email = models.EmailField()
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='team')
    seats_max = models.PositiveIntegerField(default=10)
    storage_quota_bytes = models.BigIntegerField(default=100 * 1024**3)  # 100 GB

    # Settings — JSONField для policies (require_2fa, allowed_domains, etc.)
    # см. Etap E плана Enterprise scenario.
    settings = models.JSONField(default=dict, blank=True)

    # Custom branding
    custom_logo = models.ImageField(upload_to='org_logos/', null=True, blank=True)
    custom_color = models.CharField(max_length=20, blank=True, default='')

    owner = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='owned_organizations',
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Организация'
        verbose_name_plural = 'Организации'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.slug})'

    def active_members_count(self) -> int:
        return self.memberships.filter(deactivated_at__isnull=True).count()

    def has_member(self, user) -> bool:
        if not user or not user.is_authenticated:
            return False
        return self.memberships.filter(
            user=user,
            deactivated_at__isnull=True,
        ).exists()

    def get_role(self, user) -> str:
        """Возвращает роль user'а в этой org. Пустая строка если не member."""
        try:
            m = self.memberships.get(user=user, deactivated_at__isnull=True)
            return m.role
        except OrganizationMember.DoesNotExist:
            return ''


class OrganizationMember(models.Model):
    """Связь User-Organization с ролью.

    Роли (от max permissions к min):
    - owner: всё, включая удаление org и billing
    - admin: управление users, проектами, но не billing/удаление org
    - engineer: создание/редактирование проектов в team-workspace
    - reviewer: read + approve/reject BOM
    - viewer: read-only
    """

    ROLE_CHOICES = [
        ('owner', 'Владелец'),
        ('admin', 'Администратор'),
        ('engineer', 'Инженер'),
        ('reviewer', 'Ревьюер'),
        ('moderator', 'Модератор команды'),
        ('viewer', 'Наблюдатель'),
    ]

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='org_memberships',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='engineer')
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',  # обратной связи не нужно
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    deactivated_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        unique_together = ('organization', 'user')
        indexes = [
            models.Index(fields=['user', 'organization']),
            models.Index(fields=['organization', 'role']),
        ]
        verbose_name = 'Член организации'
        verbose_name_plural = 'Члены организации'

    def __str__(self):
        return f'{self.user.username}@{self.organization.slug}:{self.role}'


class OrganizationInvite(models.Model):
    """Pending-приглашение в org. Token-based magic-link.
    Срок жизни 7 дней. После accepted_at преобразуется в OrganizationMember.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='invites',
    )
    email = models.EmailField()
    token = models.CharField(max_length=64, unique=True, db_index=True)
    role = models.CharField(
        max_length=20,
        choices=OrganizationMember.ROLE_CHOICES,
        default='engineer',
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )

    class Meta:
        indexes = [
            models.Index(fields=['organization', 'email']),
            models.Index(fields=['expires_at']),
        ]
        verbose_name = 'Приглашение в организацию'
        verbose_name_plural = 'Приглашения в организацию'

    def __str__(self):
        status = 'accepted' if self.accepted_at else ('expired' if self.is_expired() else 'pending')
        return f'invite {self.email} → {self.organization.slug} ({status})'

    def is_expired(self) -> bool:
        from django.utils import timezone

        return timezone.now() > self.expires_at and not self.accepted_at

    def is_pending(self) -> bool:
        return self.accepted_at is None and not self.is_expired()


class AuditLog(models.Model):
    """Append-only лог действий в org. Используется для compliance/SOX/audit.

    NEVER deleted напрямую — только через purge_old_audit command после retention.
    actor = кто сделал, organization = в какой org, action = что (string-namespace
    типа 'project.create', 'bom.approve', 'user.invite').
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_entries',
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='audit_log',
    )
    action = models.CharField(max_length=80, db_index=True)
    object_type = models.CharField(max_length=40, blank=True, default='')
    object_id = models.CharField(max_length=40, blank=True, default='')
    payload = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True, default='')
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['organization', '-timestamp']),
            models.Index(fields=['actor', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
        ]
        ordering = ['-timestamp']
        verbose_name = 'Запись audit-лога'
        verbose_name_plural = 'Audit-лог'

    def __str__(self):
        who = self.actor.username if self.actor else 'system'
        where = f'@{self.organization.slug}' if self.organization else ''
        return f'{self.timestamp:%Y-%m-%d %H:%M} {who}{where}: {self.action}'

    @classmethod
    def log(cls, actor, action, organization=None, object_type='', object_id='', payload=None, request=None):
        """Хелпер для централизованного логирования.
        request — optional, для IP и User-Agent.
        """
        ip = ''
        ua = ''
        if request is not None:
            ip = request.META.get('REMOTE_ADDR') or None
            ua = (request.META.get('HTTP_USER_AGENT') or '')[:300]
        return cls.objects.create(
            actor=actor if (actor and actor.is_authenticated) else None,
            organization=organization,
            action=action,
            object_type=object_type or '',
            object_id=str(object_id) if object_id else '',
            payload=payload or {},
            ip_address=ip if ip else None,
            user_agent=ua,
        )

    # Алиас — раньше callers иногда писали AuditLog.create(...) по аналогии с
    # ORM Model.objects.create(); это давало AttributeError. Принимаем оба
    # имени, чтобы не натыкаться на ту же ошибку. Каноничный путь — .log().
    record = log
    create_entry = log


class OrganizationApiToken(models.Model):
    """API-токен для интеграций (CI/CD, ERP, custom-скрипты).
    Авторизация: Authorization: Bearer dolg_<token>.
    Scope — список разрешённых действий (например ['projects.read', 'bom.read']).
    """

    TOKEN_PREFIX = 'dolg_'
    HASH_LENGTH = 64

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='api_tokens',
    )
    name = models.CharField(max_length=120, help_text='Что использует токен (для аудита)')
    token = models.CharField(max_length=80, unique=True, db_index=True)
    scope = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='+',
    )
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'API-токен организации'
        verbose_name_plural = 'API-токены организации'

    def __str__(self):
        return f'{self.organization.slug}: {self.name}'

    @classmethod
    def make_raw_token(cls) -> str:
        return cls.TOKEN_PREFIX + secrets.token_urlsafe(40)

    @classmethod
    def hash_token(cls, raw_token: str) -> str:
        if not raw_token:
            raise ValueError('API token cannot be empty')
        return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()

    @classmethod
    def is_hashed_token(cls, token: str) -> bool:
        return len(token) == cls.HASH_LENGTH and all(ch in '0123456789abcdef' for ch in token)

    def set_raw_token(self, raw_token: str) -> None:
        self.token = self.hash_token(raw_token)

    def matches(self, raw_token: str) -> bool:
        if not raw_token:
            return False
        return hmac.compare_digest(self.token, self.hash_token(raw_token))

    def save(self, *args, **kwargs):
        if self.token and not self.is_hashed_token(self.token):
            self.token = self.hash_token(self.token)
        super().save(*args, **kwargs)

    def is_active(self) -> bool:
        return self.revoked_at is None


class EnterpriseInquiry(models.Model):
    """Лиды от sales-led flow (большие компании, custom enterprise plan).
    Заполняется через /enterprise/contact/, обрабатывается admin'ом через
    /admin/ или management-команду provision_enterprise.
    """

    STATUS_CHOICES = [
        ('new', 'Новая заявка'),
        ('contacted', 'Связались'),
        ('demo_scheduled', 'Демо запланировано'),
        ('proposal_sent', 'Предложение отправлено'),
        ('won', 'Закрыт успехом'),
        ('lost', 'Закрыт отказом'),
    ]
    company_name = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=120)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=40, blank=True)
    team_size_range = models.CharField(max_length=30)  # '50-100', '100-500', '500+'
    industry = models.CharField(max_length=80, blank=True)
    requirements = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new', db_index=True)
    notes_internal = models.TextField(blank=True, help_text='Только для admin DOLG')
    converted_to_org = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    contacted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Enterprise-заявка'
        verbose_name_plural = 'Enterprise-заявки'

    def __str__(self):
        return f'{self.company_name} ({self.status})'


class Comment(models.Model):
    """Универсальный комментарий: на проект, на статью или ответ.

    Контент-обвязка:
    - Free-юзер: `body` = plain-text до 500 символов, рендерится с escape.
    - Pro-юзер: `body` = Markdown до 5000 символов, рендерится через
      markdown2 + bleach (whitelist тегов). Auto-determined по `is_rich`.

    Полиморфизм: один из (project, article) обязателен.
    Replies: parent → корневой comment.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comments',
    )
    project = models.ForeignKey(
        'Dolg_APP.SchematicProject',
        on_delete=models.CASCADE,
        related_name='comments',
        null=True,
        blank=True,
    )
    article = models.ForeignKey(
        'knowledge.Article',
        on_delete=models.CASCADE,
        related_name='comments',
        null=True,
        blank=True,
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        related_name='replies',
        null=True,
        blank=True,
    )
    body = models.TextField()
    is_rich = models.BooleanField(
        default=False,
        help_text='Markdown-формат (Pro-фича). Free сохраняет plain-text.',
    )
    edited_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    moderation_status = models.CharField(
        max_length=20,
        choices=MODERATION_STATUS_CHOICES,
        default='visible',
        db_index=True,
    )
    moderation_reason = models.TextField(blank=True)
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    moderated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['project', 'created_at']),
            models.Index(fields=['article', 'created_at']),
        ]

    def __str__(self):
        target = self.project_id or f'article:{self.article_id}'
        return f'#{self.id} by {self.user.username} on {target}'

    def render_html(self) -> str:
        """Возвращает HTML-представление body.
        Free (is_rich=False): plain-text с escape + автоссылки + переносы.
        Pro (is_rich=True): Markdown через markdown2 → bleach-sanitize.
        """
        from . import comments_render

        return comments_render.render(self.body, rich=self.is_rich)


class SchematicProject(models.Model):
    CATEGORY_CHOICES = [
        ('led', 'LED проект'),
        ('audio', 'Аудио'),
        ('power', 'Блок питания'),
        ('sensor', 'Сенсор'),
        ('arduino', 'Arduino'),
        ('other', 'Другое'),
    ]
    STATUS_CHOICES = [
        ('draft', 'Черновик'),
        ('inprogress', 'В работе'),
        ('completed', 'Завершено'),
    ]
    DIFFICULTY_CHOICES = [
        ('basic', 'Начальный'),
        ('medium', 'Средний'),
        ('advanced', 'Продвинутый'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='schematic_projects',
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='basic')
    # Демо-проекты видны всем авторизованным пользователям (read-only).
    # Заливаются командой populate_demo_projects и принадлежат админу.
    is_demo = models.BooleanField(default=False)
    scheme_data = models.JSONField(default=dict, blank=True)
    # Публичный токен для read-only sharing /s/<token>/. Пустая строка =
    # шаринг выключен. db_index чтобы lookup-ы по токену были быстрые.
    share_token = models.CharField(max_length=22, blank=True, default='', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Soft-delete: при удалении ставим timestamp вместо стирания записи.
    # Корзина живёт 30 дней, потом purge_deleted_projects-command удалит физически.
    # Manager objects ИСКЛЮЧАЕТ soft-deleted; для доступа ко всем — all_objects.
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # Team-workspace: проект может принадлежать org (видимый всем members)
    # вместо личного юзера. user остаётся как «создатель», organization —
    # как владелец workspace. Если null → личный проект.
    organization = models.ForeignKey(
        'Dolg_APP.Organization',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='projects',
        db_index=True,
    )
    VISIBILITY_CHOICES = [
        ('private', 'Только владелец'),
        ('team', 'Видна команде'),
        ('public', 'Публичный marketplace'),
    ]
    visibility = models.CharField(
        max_length=10,
        choices=VISIBILITY_CHOICES,
        default='private',
    )
    # Approval workflow (для BOM/order, для Enterprise отделения duties):
    APPROVAL_STATES = [
        ('draft', 'Черновик'),
        ('pending_review', 'На ревью'),
        ('approved', 'Одобрено'),
        ('rejected', 'Отклонено'),
    ]
    approval_state = models.CharField(
        max_length=20,
        choices=APPROVAL_STATES,
        default='draft',
    )

    # objects присвоится ниже (ActiveProjectManager определяется после класса).
    all_objects = models.Manager()  # Включает soft-deleted

    class Meta:
        ordering = ['-updated_at']
        base_manager_name = 'all_objects'  # related-lookups берут из all_objects

    def __str__(self):
        return f'{self.user.username} — {self.name}'

    def soft_delete(self):
        from django.utils import timezone

        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])

    def restore(self):
        self.deleted_at = None
        self.save(update_fields=['deleted_at'])

    @property
    def is_in_trash(self):
        return self.deleted_at is not None


class ActiveProjectManager(models.Manager):
    """Default manager — скрывает soft-deleted. Чтобы получить включая —
    использовать SchematicProject.all_objects."""

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


# Назначаем objects ПОСЛЕ all_objects (порядок важен — `objects` остаётся
# default manager для прямых запросов SchematicProject.objects.*).
SchematicProject.objects = ActiveProjectManager()
SchematicProject.objects.model = SchematicProject
SchematicProject.objects.contribute_to_class(SchematicProject, 'objects')


class ProjectVersion(models.Model):
    project = models.ForeignKey(
        SchematicProject,
        on_delete=models.CASCADE,
        related_name='versions',
    )
    version_number = models.PositiveIntegerField()
    scheme_data = models.JSONField(default=dict, blank=True)
    change_note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version_number']
        unique_together = ('project', 'version_number')
        verbose_name = 'Версия схемы'
        verbose_name_plural = 'Версии схем'

    def __str__(self):
        return f'{self.project.name} v{self.version_number}'


class SimulationRun(models.Model):
    ANALYSIS_CHOICES = [
        ('dc', 'DC / рабочая точка'),
        ('op', 'Рабочая точка'),
        ('ac', 'АЧХ/ФЧХ'),
        ('tran', 'Переходный процесс'),
        ('pulse', 'Импульсный режим'),
        ('unknown', 'Неизвестно'),
    ]

    project = models.ForeignKey(
        SchematicProject,
        on_delete=models.CASCADE,
        related_name='simulation_runs',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='simulation_runs',
    )
    analysis_type = models.CharField(max_length=20, choices=ANALYSIS_CHOICES, default='unknown')
    engine = models.CharField(max_length=80, blank=True)
    elapsed_ms = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, default='success')
    progress_percent = models.PositiveSmallIntegerField(default=100)
    message = models.CharField(max_length=240, blank=True, default='')
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    netlist = models.TextField(blank=True)
    result_summary = models.JSONField(default=dict, blank=True)
    result_data = models.JSONField(default=dict, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Запуск симуляции'
        verbose_name_plural = 'Запуски симуляций'

    def __str__(self):
        return f'{self.project.name} — {self.analysis_type} — {self.created_at:%Y-%m-%d %H:%M}'


class ProjectMeasurement(models.Model):
    project = models.ForeignKey(
        SchematicProject,
        on_delete=models.CASCADE,
        related_name='measurements',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='project_measurements',
    )
    simulation_run = models.ForeignKey(
        SimulationRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='measurements',
    )
    metric = models.CharField(max_length=80)
    label = models.CharField(max_length=160, blank=True)
    value = models.FloatField()
    unit = models.CharField(max_length=24, blank=True)
    expected_value = models.FloatField(null=True, blank=True)
    tolerance_abs = models.FloatField(null=True, blank=True)
    tolerance_percent = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=24, default='unchecked')
    source = models.CharField(max_length=40, default='manual')
    result = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['project', '-created_at'])]

    def __str__(self):
        return f'{self.project_id}: {self.metric}={self.value:g}{self.unit}'


class ProjectReview(models.Model):
    STATUS_CHOICES = [
        ('ready', 'ready'),
        ('needs_review', 'needs review'),
        ('risk', 'risk'),
        ('critical', 'critical'),
    ]

    project = models.ForeignKey(
        SchematicProject,
        on_delete=models.CASCADE,
        related_name='reviews',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='project_reviews',
    )
    score = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='needs_review')
    summary = models.TextField(blank=True)
    errors = models.JSONField(default=list, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    recommendations = models.JSONField(default=list, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    sections = models.JSONField(default=dict, blank=True)
    faults = models.JSONField(default=list, blank=True)
    scheme_data = models.JSONField(default=dict, blank=True)
    import_summary = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['project', '-created_at'])]

    def __str__(self):
        return f'{self.project.name}: {self.score}/100 {self.status}'


class ProjectEvent(models.Model):
    """Журнал web-ориентированного сеанса проектирования."""

    EVENT_CHOICES = [
        ('project_created', 'Проект создан'),
        ('project_updated', 'Проект обновлен'),
        ('scheme_saved', 'Схема сохранена'),
        ('simulation_run', 'Запуск симуляции'),
        ('measurement_added', 'Измерение добавлено'),
        ('review_created', 'Review создан'),
        ('bom_exported', 'BOM экспортирован'),
        ('import_finished', 'Импорт завершен'),
        ('comment_added', 'Комментарий добавлен'),
    ]

    project = models.ForeignKey(
        SchematicProject,
        on_delete=models.CASCADE,
        related_name='events',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='project_events',
    )
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', '-created_at'], name='pe_project_created_idx'),
            models.Index(fields=['event_type', '-created_at'], name='pe_type_created_idx'),
        ]
        verbose_name = 'Событие проекта'
        verbose_name_plural = 'События проектов'

    def __str__(self):
        return f'{self.project_id}: {self.event_type} @ {self.created_at:%Y-%m-%d %H:%M}'

    @classmethod
    def log(cls, *, project, user=None, event_type='', payload=None):
        if project is None or not getattr(project, 'pk', None):
            return None
        return cls.objects.create(
            project=project,
            user=user if getattr(user, 'is_authenticated', False) else None,
            event_type=event_type,
            payload=payload or {},
        )


# ============================================================
# Чат — обсуждения технических вопросов
# Public Q&A (ChatTopic + ChatReply + ChatReaction) — доступно всем
# Enterprise беседы (OrgConversation + OrgConversationMessage) — приватные каналы org
# ============================================================


class EngineeringArtifact(models.Model):
    """Normalized engineering file or report used by review, learning and AI."""

    ARTIFACT_TYPES = [
        ('document', 'Document'),
        ('cad_drawing', 'CAD drawing'),
        ('cad_netlist', 'CAD netlist'),
        ('check_report', 'Check report'),
        ('bom', 'BOM'),
        ('simulation', 'Simulation'),
        ('unknown', 'Unknown'),
    ]
    STATUS_CHOICES = [
        ('parsed', 'parsed'),
        ('partial', 'partial'),
        ('unsupported', 'unsupported'),
        ('error', 'error'),
    ]

    project = models.ForeignKey(
        SchematicProject,
        on_delete=models.CASCADE,
        related_name='engineering_artifacts',
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='engineering_artifacts',
    )
    source_name = models.CharField(max_length=240)
    source_path = models.TextField(blank=True)
    artifact_type = models.CharField(max_length=32, choices=ARTIFACT_TYPES, default='unknown')
    parser = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='parsed')
    checksum = models.CharField(max_length=64, db_index=True)
    size_bytes = models.PositiveIntegerField(default=0)
    summary = models.TextField(blank=True)
    facts = models.JSONField(default=dict, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', '-created_at'], name='artifact_project_created_idx'),
            models.Index(fields=['artifact_type', '-created_at'], name='artifact_type_created_idx'),
            models.Index(fields=['checksum'], name='artifact_checksum_idx'),
        ]
        unique_together = ('project', 'checksum', 'source_name')

    def __str__(self):
        return f'{self.source_name} ({self.artifact_type})'


class AITrainingExample(models.Model):
    """Curated example for safe periodic AI retraining, never live self-mutation."""

    KIND_CHOICES = [
        ('artifact_summary', 'Artifact summary'),
        ('drc_finding', 'DRC finding'),
        ('fault_case', 'Fault case'),
        ('review_hint', 'Review hint'),
        ('user_correction', 'User correction'),
    ]

    artifact = models.ForeignKey(
        EngineeringArtifact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='training_examples',
    )
    project = models.ForeignKey(
        SchematicProject,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='ai_training_examples',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ai_training_examples',
    )
    kind = models.CharField(max_length=40, choices=KIND_CHOICES)
    prompt = models.TextField()
    target = models.TextField()
    features = models.JSONField(default=dict, blank=True)
    is_validated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['kind', '-created_at'], name='aitrain_kind_created_idx'),
            models.Index(fields=['is_validated', '-created_at'], name='aitrain_valid_created_idx'),
        ]

    def __str__(self):
        return f'{self.kind}: {self.prompt[:60]}'


class MLJob(models.Model):
    """Persistent operational record for ML import, validation and training jobs."""

    JOB_TYPE_CHOICES = [
        ('dataset_import', 'Dataset import'),
        ('training', 'Training'),
        ('validation', 'Validation'),
        ('export', 'Export'),
        ('promotion', 'Promotion'),
    ]
    STATUS_CHOICES = [
        ('queued', 'queued'),
        ('running', 'running'),
        ('success', 'success'),
        ('error', 'error'),
        ('cancelled', 'cancelled'),
        ('stale', 'stale'),
    ]

    job_type = models.CharField(max_length=32, choices=JOB_TYPE_CHOICES, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued', db_index=True)
    progress_percent = models.PositiveSmallIntegerField(default=0)
    source = models.CharField(max_length=160, blank=True)
    message = models.CharField(max_length=260, blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    stdout_tail = models.TextField(blank=True)
    error = models.TextField(blank=True)
    processed = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ml_jobs',
    )
    started_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['job_type', 'status', '-created_at'], name='mljob_type_status_created_idx'),
            models.Index(fields=['status', '-heartbeat_at'], name='mljob_status_heartbeat_idx'),
        ]

    def __str__(self):
        return f'{self.job_type} #{self.pk} [{self.status}]'

    def mark_running(self, *, message: str = ''):
        now = timezone.now()
        if self.started_at is None:
            self.started_at = now
        self.status = 'running'
        self.heartbeat_at = now
        if message:
            self.message = message[:260]
        self.save(update_fields=['status', 'started_at', 'heartbeat_at', 'message', 'updated_at'])

    def update_progress(
        self,
        *,
        progress_percent=None,
        processed=None,
        created_count=None,
        updated_count=None,
        skipped_count=None,
        message: str = '',
        result=None,
        stdout_tail: str = '',
    ):
        now = timezone.now()
        self.status = 'running' if self.status in {'queued', 'running'} else self.status
        self.heartbeat_at = now
        if progress_percent is not None:
            self.progress_percent = max(0, min(100, int(progress_percent)))
        if processed is not None:
            self.processed = max(0, int(processed))
        if created_count is not None:
            self.created_count = max(0, int(created_count))
        if updated_count is not None:
            self.updated_count = max(0, int(updated_count))
        if skipped_count is not None:
            self.skipped_count = max(0, int(skipped_count))
        if message:
            self.message = message[:260]
        if result is not None:
            self.result = result
        if stdout_tail:
            self.stdout_tail = stdout_tail[-4000:]
        self.save()

    def mark_success(self, *, message: str = '', result=None, stdout_tail: str = ''):
        now = timezone.now()
        self.status = 'success'
        self.progress_percent = 100
        self.heartbeat_at = now
        self.finished_at = now
        if message:
            self.message = message[:260]
        if result is not None:
            self.result = result
        if stdout_tail:
            self.stdout_tail = stdout_tail[-4000:]
        self.save()

    def mark_error(self, *, error: str = '', message: str = '', stdout_tail: str = ''):
        now = timezone.now()
        self.status = 'error'
        self.heartbeat_at = now
        self.finished_at = now
        if message:
            self.message = message[:260]
        if error:
            self.error = error
        if stdout_tail:
            self.stdout_tail = stdout_tail[-4000:]
        self.save()

    def mark_cancelled(self, *, message: str = ''):
        now = timezone.now()
        self.status = 'cancelled'
        self.heartbeat_at = now
        self.finished_at = now
        if message:
            self.message = message[:260]
        self.save(update_fields=['status', 'heartbeat_at', 'finished_at', 'message', 'updated_at'])


class ChatTopic(models.Model):
    """Публичный технический топик (Q&A-стиль)."""

    CATEGORY_CHOICES = [
        ('general', 'Общее'),
        ('schematics', 'Схемы'),
        ('simulation', 'Симуляция'),
        ('cad', 'CAD'),
        ('components', 'Компоненты РЭБ'),
        ('ai', 'AI-ассистент'),
    ]

    title = models.CharField(max_length=200)
    body = models.TextField()
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chat_topics',
    )
    category = models.CharField(max_length=24, choices=CATEGORY_CHOICES, default='general', db_index=True)
    tags = models.JSONField(default=list, blank=True)
    is_pinned = models.BooleanField(default=False)
    is_resolved = models.BooleanField(default=False)
    views_count = models.PositiveIntegerField(default=0)
    attached_project = models.ForeignKey(
        SchematicProject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chat_topics',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity_at = models.DateTimeField(default=timezone.now, db_index=True)
    moderation_status = models.CharField(
        max_length=20,
        choices=MODERATION_STATUS_CHOICES,
        default='visible',
        db_index=True,
    )
    moderation_reason = models.TextField(blank=True)
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    moderated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-is_pinned', '-last_activity_at']
        indexes = [
            models.Index(fields=['category', '-last_activity_at']),
            models.Index(fields=['-is_pinned', '-last_activity_at']),
        ]

    def __str__(self):
        return self.title[:80]

    def reply_count(self):
        return self.replies.count()


class ChatReply(models.Model):
    """Ответ в топике. Поддерживает nested-threading через parent."""

    topic = models.ForeignKey(ChatTopic, on_delete=models.CASCADE, related_name='replies')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chat_replies',
    )
    body = models.TextField()
    is_accepted_answer = models.BooleanField(default=False)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    moderation_status = models.CharField(
        max_length=20,
        choices=MODERATION_STATUS_CHOICES,
        default='visible',
        db_index=True,
    )
    moderation_reason = models.TextField(blank=True)
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    moderated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['topic', 'created_at'])]

    def __str__(self):
        return f'reply by {self.author_id} in topic {self.topic_id}'


class ChatReaction(models.Model):
    """Эмодзи-реакция на топик или ответ. Free: только 👍. Pro/Enterprise: любая.

    Ровно один из target_topic / target_reply должен быть заполнен — это
    enforced через partial unique constraints + clean() в save-path.
    """

    target_topic = models.ForeignKey(
        ChatTopic,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='reactions',
    )
    target_reply = models.ForeignKey(
        ChatReply,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='reactions',
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    emoji = models.CharField(max_length=16, default='👍')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['target_topic', 'user', 'emoji'],
                condition=models.Q(target_topic__isnull=False),
                name='unique_topic_reaction',
            ),
            models.UniqueConstraint(
                fields=['target_reply', 'user', 'emoji'],
                condition=models.Q(target_reply__isnull=False),
                name='unique_reply_reaction',
            ),
        ]

    def __str__(self):
        target = f'topic={self.target_topic_id}' if self.target_topic_id else f'reply={self.target_reply_id}'
        return f'{self.emoji} by {self.user_id} on {target}'


class OrgConversation(models.Model):
    """Приватный канал команды в organization (Enterprise).

    Видим только members этой org. Создаётся owner/admin'ами.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='conversations',
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_conversations',
    )
    is_archived = models.BooleanField(default=False)
    attached_project = models.ForeignKey(
        SchematicProject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='org_conversations',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['is_archived', '-last_activity_at']
        indexes = [models.Index(fields=['organization', '-last_activity_at'])]

    def __str__(self):
        return f'{self.organization.slug}/{self.title[:60]}'

    def message_count(self):
        return self.messages.count()


class OrgConversationMessage(models.Model):
    """Сообщение в org-канале. Поддерживает Markdown (все Enterprise = Pro)."""

    conversation = models.ForeignKey(OrgConversation, on_delete=models.CASCADE, related_name='messages')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='org_messages',
    )
    body = models.TextField()
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies',
    )
    mentions = models.JSONField(default=list, blank=True)
    is_edited = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    moderation_status = models.CharField(
        max_length=20,
        choices=MODERATION_STATUS_CHOICES,
        default='visible',
        db_index=True,
    )
    moderation_reason = models.TextField(blank=True)
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    moderated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['conversation', 'created_at'])]

    def __str__(self):
        return f'msg {self.id} by {self.author_id} in conv {self.conversation_id}'


class Announcement(models.Model):
    """Официальные объявления админов — показываются в правом сайдбаре чата.

    Только staff может публиковать. Read-only для всех остальных.
    Не путать с ChatTopic — пользователь не может отвечать или реагировать.
    Используется для: релизы, плановые работы, новости проекта.
    """

    LEVEL_CHOICES = [
        ('info', 'ℹ Информация'),
        ('warning', '⚠ Предупреждение'),
        ('critical', '🔴 Критично'),
    ]

    title = models.CharField(max_length=200)
    body = models.TextField()
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='announcements',
    )
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='info')
    is_published = models.BooleanField(default=True, db_index=True)
    is_pinned = models.BooleanField(default=False)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text='Если задано — после этой даты объявление скрывается из сайдбара',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']
        indexes = [models.Index(fields=['is_published', '-created_at'])]

    def __str__(self):
        return f'[{self.level}] {self.title[:60]}'

    def is_active(self):
        if not self.is_published:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True


# ─── 2026-06-02 Lithium ECAD killer-фича: Functional Blocks ─────────────────
# Юзер выделяет группу компонентов на схеме (Ctrl+A или drag-select), сохраняет
# как «функциональный блок» — JSON со списком компонентов и соединений + preview.
# Потом drag-n-drop из палитры «📦 Мои блоки» → подсхема разворачивается на канвасе
# со смещением до позиции курсора. Аналог Lithium ECAD «Functional blocks».
class FunctionalBlock(models.Model):
    CATEGORY_CHOICES = [
        ('power', '⚡ Питание'),
        ('analog', '🔊 Аналог'),
        ('digital', '💾 Цифра'),
        ('rf', '📡 РЧ'),
        ('filter', '🌊 Фильтры'),
        ('sensor', '🌡 Датчики'),
        ('other', '📦 Прочее'),
    ]
    name = models.CharField(max_length=80, help_text='Название блока (напр. "DC-DC 5В→3.3В")')
    description = models.CharField(max_length=200, blank=True, help_text='Краткое описание для тултипа')
    category = models.CharField(max_length=16, choices=CATEGORY_CHOICES, default='other')
    schema_json = models.JSONField(
        help_text='{"components":[...],"connections":[...]} формата applySchemeData'
    )
    preview_svg = models.TextField(blank=True, help_text='Опциональная мини-SVG-отрисовка')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='functional_blocks',
        help_text='Владелец блока',
    )
    is_public = models.BooleanField(default=False, db_index=True, help_text='Виден ли другим юзерам')
    use_count = models.PositiveIntegerField(default=0, help_text='Счётчик использований (drag в схему)')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', '-updated_at']),
            models.Index(fields=['is_public', 'category']),
        ]

    def __str__(self):
        return f'{self.name} ({self.user.username})'

    @property
    def component_count(self):
        try:
            return len((self.schema_json or {}).get('components', []))
        except TypeError, AttributeError:
            return 0

    @property
    def connection_count(self):
        try:
            return len((self.schema_json or {}).get('connections', []))
        except TypeError, AttributeError:
            return 0
