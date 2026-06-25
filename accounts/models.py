from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.db import models


class UserProfile(models.Model):
    THEME_CHOICES = [
        ('dark', 'Темная'),
        ('light', 'Светлая'),
        ('system', 'Как в системе'),
        ('projector', 'Для проектора'),
    ]
    ACCENT_CHOICES = [
        ('cyan', 'Бирюзовый'),
        ('blue', 'Синий'),
        ('green', 'Зеленый'),
        ('orange', 'Оранжевый'),
        ('violet', 'Фиолетовый'),
    ]
    UNIT_SYSTEM_CHOICES = [
        ('engineering', 'Инженерные единицы'),
        ('metric', 'Метрические единицы'),
    ]
    START_PAGE_CHOICES = [
        ('catalog', 'Каталог'),
        ('projects', 'Проекты'),
        ('simulation', 'Симуляция'),
        ('lab', 'Лаборатория'),
        ('learning', 'Обучение'),
    ]
    AI_TONE_CHOICES = [
        ('concise', 'Кратко'),
        ('explained', 'С объяснением'),
        ('review', 'Инженерный review'),
        ('demo', 'Для защиты'),
    ]
    INTERFACE_DENSITY_CHOICES = [
        ('compact', 'Компактно'),
        ('comfortable', 'Комфортно'),
        ('spacious', 'Свободно'),
    ]
    WORKSPACE_LAYOUT_CHOICES = [
        ('balanced', 'Сбалансированно'),
        ('focus', 'Фокус на холсте'),
        ('lab', 'Лаборатория и приборы'),
        ('review', 'Инженерное ревью'),
    ]
    AI_BACKEND_CHOICES = [
        ('auto', 'Автоматически'),
        ('local', 'Локальный AI'),
        ('engine_ai', 'Локальный AI + движки'),
        ('disabled', 'Отключить AI'),
    ]
    SIM_ENGINE_CHOICES = [
        ('auto', 'Автоматически'),
        ('browser_ngspice', 'Browser NGSpice'),
        ('pyspice', 'PySpice'),
        ('xyce', 'Xyce'),
        ('gnucap', 'GnuCap'),
        ('openmodelica', 'OpenModelica'),
    ]
    RENDER_MODE_CHOICES = [
        ('auto', 'Автоматически'),
        ('canvas2d', 'Canvas 2D'),
        ('webgl', 'WebGL / Pixi'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(
        max_length=20,
        blank=True,
        validators=[RegexValidator(regex=r'^\+?1?\d{9,15}$', message='Введите корректный номер телефона')],
    )
    address = models.CharField(max_length=300, blank=True)
    city = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, blank=True, default='Россия')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    bio = models.TextField(blank=True)
    display_name = models.CharField(max_length=80, blank=True)
    headline = models.CharField(max_length=120, blank=True)
    preferred_theme = models.CharField(max_length=20, choices=THEME_CHOICES, default='dark')
    accent_color = models.CharField(max_length=20, choices=ACCENT_CHOICES, default='cyan')
    default_unit_system = models.CharField(max_length=20, choices=UNIT_SYSTEM_CHOICES, default='engineering')
    start_page = models.CharField(max_length=20, choices=START_PAGE_CHOICES, default='catalog')
    ai_tone = models.CharField(max_length=20, choices=AI_TONE_CHOICES, default='explained')
    interface_density = models.CharField(
        max_length=20, choices=INTERFACE_DENSITY_CHOICES, default='comfortable'
    )
    workspace_layout = models.CharField(max_length=20, choices=WORKSPACE_LAYOUT_CHOICES, default='balanced')
    ai_backend = models.CharField(max_length=20, choices=AI_BACKEND_CHOICES, default='auto')
    preferred_sim_engine = models.CharField(max_length=40, choices=SIM_ENGINE_CHOICES, default='auto')
    preferred_render_mode = models.CharField(max_length=20, choices=RENDER_MODE_CHOICES, default='auto')
    enable_workspace_animations = models.BooleanField(default=True)
    reduce_motion = models.BooleanField(default=False)
    show_advanced_tools = models.BooleanField(default=True)
    workspace_settings = models.JSONField(default=dict, blank=True)
    show_profile_public = models.BooleanField(default=False)
    show_engineering_badges = models.BooleanField(default=True)
    allow_ai_training = models.BooleanField(default=False)
    # Pro-only: custom logo на экспортах (PDF, Gerber-ZIP README, BOM).
    # Free-юзеры видят стандартный DOLG-watermark. Загрузка через
    # /accounts/profile/edit/ — проверка tier на upload-time.
    pro_logo = models.ImageField(upload_to='pro_logos/', null=True, blank=True)
    # Email-верификация: после регистрации флаг = False, после клика по
    # /accounts/verify-email/<token>/ — True. На login пока не блокируем
    # (для дев/демо), но в шаблонах показываем бейдж «✓ Email подтверждён».
    email_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Профиль пользователя'
        verbose_name_plural = 'Профили пользователей'

    def __str__(self):
        return f'Профиль {self.user.username}'

    @property
    def full_address(self):
        parts = [self.address, self.postal_code, self.city, self.country]
        return ', '.join(filter(None, parts))


class Address(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    title = models.CharField(max_length=100)
    address = models.CharField(max_length=300)
    city = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default='Россия')
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Адрес доставки'
        verbose_name_plural = 'Адреса доставки'
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return f'{self.title} - {self.address}'
