from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class KnowledgeCategory(models.Model):
    TOPIC_CHOICES = [
        ('physics',     'Физика и теория'),
        ('components',  'Компоненты'),
        ('packages',    'Корпуса и монтаж'),
        ('pcb',         'Печатные платы'),
        ('history',     'История электроники'),
        ('practice',    'Инженерная практика'),
    ]

    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=80, unique=True, blank=True)
    topic = models.CharField(max_length=20, choices=TOPIC_CHOICES, default='physics')
    icon = models.CharField(max_length=8, default='📘', help_text='Emoji-иконка для карточки')
    description = models.CharField(max_length=200, blank=True)
    order = models.PositiveSmallIntegerField(default=100)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Категория знаний'
        verbose_name_plural = 'Категории знаний'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Article(models.Model):
    category = models.ForeignKey(KnowledgeCategory, on_delete=models.PROTECT, related_name='articles')
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    summary = models.TextField(max_length=400, help_text='Короткая аннотация для карточки (1–2 предложения)')
    body = models.TextField(help_text='Основной текст. Поддерживает простую HTML-разметку (p, h3, ul, li, code, img).')
    related_components_note = models.CharField(
        max_length=200, blank=True,
        help_text='Опциональная подсказка: какие категории товаров связаны.',
    )
    reading_minutes = models.PositiveSmallIntegerField(default=3)
    is_published = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category__order', 'order', 'title']
        verbose_name = 'Статья'
        verbose_name_plural = 'Статьи'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title, allow_unicode=True)[:200]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class ArticleMaterial(models.Model):
    MATERIAL_TYPE_CHOICES = [
        ('datasheet', 'Datasheet / PDF'),
        ('calculator', 'Калькулятор'),
        ('example', 'Пример схемы'),
        ('checklist', 'Чек-лист'),
        ('image', 'Изображение'),
        ('animation', 'Анимация'),
        ('video', 'Видео'),
        ('external', 'Внешний материал'),
        ('file', 'Файл'),
    ]

    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='materials')
    material_type = models.CharField(max_length=20, choices=MATERIAL_TYPE_CHOICES, default='external')
    title = models.CharField(max_length=160)
    description = models.CharField(max_length=300, blank=True)
    url = models.CharField(
        max_length=300,
        blank=True,
        help_text='Внешняя ссылка или внутренний путь сайта, например /simulation/',
    )
    file = models.FileField(upload_to='knowledge_materials/', blank=True, null=True)
    order = models.PositiveSmallIntegerField(default=100)
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'title']
        verbose_name = 'Материал статьи'
        verbose_name_plural = 'Материалы статьи'
        constraints = [
            models.UniqueConstraint(fields=['article', 'title'], name='unique_article_material_title'),
        ]

    def __str__(self):
        return self.title

    @property
    def href(self):
        if self.file:
            return self.file.url
        if self.url:
            return self.url
        return ''

    @property
    def extension(self):
        source = self.href
        if not source:
            return ''
        return urlparse(source).path.rsplit('.', 1)[-1].lower() if '.' in urlparse(source).path else ''

    @property
    def is_inline_image(self):
        return self.material_type in {'image', 'animation'} or self.extension in {'jpg', 'jpeg', 'png', 'webp', 'gif', 'svg'}

    @property
    def is_video_file(self):
        return self.extension in {'mp4', 'webm', 'ogv', 'ogg'}

    @property
    def embed_url(self):
        if self.material_type != 'video' or not self.url:
            return ''

        parsed = urlparse(self.url)
        host = parsed.netloc.lower().replace('www.', '')
        if host in {'youtube.com', 'm.youtube.com'}:
            if parsed.path.startswith('/embed/'):
                return self.url
            video_id = parse_qs(parsed.query).get('v', [''])[0]
            return f'https://www.youtube.com/embed/{video_id}' if video_id else ''
        if host == 'youtu.be':
            video_id = parsed.path.strip('/')
            return f'https://www.youtube.com/embed/{video_id}' if video_id else ''
        if host == 'vimeo.com':
            video_id = parsed.path.strip('/').split('/')[0]
            return f'https://player.vimeo.com/video/{video_id}' if video_id else ''
        if host == 'player.vimeo.com':
            return self.url
        return ''

    @property
    def renders_inline(self):
        return self.is_inline_image or self.is_video_file or bool(self.embed_url)

    @property
    def is_internal_link(self):
        href = self.href
        return bool(href and href.startswith('/'))


class LearningTrack(models.Model):
    LEVEL_CHOICES = [
        ('basic', 'Начальный'),
        ('medium', 'Средний'),
        ('advanced', 'Продвинутый'),
    ]

    title = models.CharField(max_length=160, unique=True)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    summary = models.TextField(max_length=500)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='basic')
    order = models.PositiveSmallIntegerField(default=100)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'title']
        verbose_name = 'Учебный маршрут'
        verbose_name_plural = 'Учебные маршруты'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title, allow_unicode=True)[:180]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class LearningLesson(models.Model):
    track = models.ForeignKey(LearningTrack, on_delete=models.CASCADE, related_name='lessons')
    article = models.ForeignKey(
        Article, on_delete=models.SET_NULL, null=True, blank=True, related_name='learning_lessons'
    )
    demo_project = models.ForeignKey(
        'Dolg_APP.SchematicProject',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='learning_lessons',
    )
    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    summary = models.TextField(max_length=500)
    theory = models.TextField(help_text='Теория урока. Поддерживает простую HTML-разметку.')
    formula = models.CharField(max_length=220, blank=True)
    action_url = models.CharField(max_length=300, blank=True)
    action_label = models.CharField(max_length=120, blank=True)
    estimated_minutes = models.PositiveSmallIntegerField(default=8)
    order = models.PositiveSmallIntegerField(default=100)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['track__order', 'order', 'title']
        verbose_name = 'Учебный урок'
        verbose_name_plural = 'Учебные уроки'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title, allow_unicode=True)[:200]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class LearningTask(models.Model):
    TASK_TYPE_CHOICES = [
        ('math_numeric', 'Математическая задача'),
        ('circuit_build', 'Сборка схемы'),
        ('simulation_measure', 'Измерение симуляции'),
    ]

    lesson = models.ForeignKey(LearningLesson, on_delete=models.CASCADE, related_name='tasks')
    task_type = models.CharField(max_length=32, choices=TASK_TYPE_CHOICES)
    title = models.CharField(max_length=180)
    prompt = models.TextField()
    rubric = models.JSONField(default=dict, blank=True)
    order = models.PositiveSmallIntegerField(default=100)
    is_required = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['lesson__order', 'order', 'title']
        verbose_name = 'Учебное задание'
        verbose_name_plural = 'Учебные задания'

    def __str__(self):
        return f'{self.lesson.title}: {self.title}'


class LearningAttempt(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='learning_attempts',
    )
    task = models.ForeignKey(LearningTask, on_delete=models.CASCADE, related_name='attempts')
    answer = models.JSONField(default=dict, blank=True)
    is_correct = models.BooleanField(default=False)
    score = models.PositiveSmallIntegerField(default=0)
    feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', '-created_at'])]
        verbose_name = 'Попытка учебного задания'
        verbose_name_plural = 'Попытки учебных заданий'

    def __str__(self):
        return f'{self.user_id}: {self.task_id} ({self.score})'


class LearningProgress(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='learning_progress',
    )
    lesson = models.ForeignKey(LearningLesson, on_delete=models.CASCADE, related_name='progress')
    solved_task_ids = models.JSONField(default=list, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'lesson')
        ordering = ['-updated_at']
        indexes = [models.Index(fields=['user', '-updated_at'])]
        verbose_name = 'Прогресс обучения'
        verbose_name_plural = 'Прогресс обучения'

    @property
    def is_completed(self):
        return self.completed_at is not None

    def mark_task_solved(self, task_id):
        solved = set(self.solved_task_ids or [])
        solved.add(task_id)
        self.solved_task_ids = sorted(solved)
        required_ids = set(
            self.lesson.tasks.filter(is_required=True).values_list('id', flat=True)
        )
        if required_ids and required_ids.issubset(set(self.solved_task_ids)):
            self.completed_at = self.completed_at or timezone.now()
        self.save(update_fields=['solved_task_ids', 'completed_at', 'updated_at'])

    def __str__(self):
        return f'{self.user_id}: {self.lesson}'
