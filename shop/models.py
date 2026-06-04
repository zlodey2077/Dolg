import re
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify


class Category(models.Model):
    CATEGORY_SLUGS = {
        # Потребительская электроника
        'Смартфоны': 'smartphones',
        'Ноутбуки': 'laptops',
        'Планшеты': 'tablets',
        'Аксессуары': 'accessories',
        'Процессоры (CPU)': 'cpu',
        'Видеокарты (GPU)': 'gpu',
        'ОЗУ (RAM)': 'ram',
        'SSD диски': 'ssd',
        'Блоки питания': 'psu',
        'Кулеры': 'cooling',
        'Мониторы': 'monitors',
        'Материнские платы': 'motherboards',
        # РЭБ-компоненты
        'Резисторы': 'resistors',
        'Конденсаторы': 'capacitors',
        'Транзисторы': 'transistors',
        'Микросхемы': 'ics',
        'Диоды': 'diodes',
        'Дроссели и катушки': 'inductors',
        'Разъёмы': 'connectors',
        'Реле': 'relays',
    }

    # Категории РЭБ для шаблонов/фильтров
    REB_SLUGS = {
        'resistors',
        'capacitors',
        'transistors',
        'ics',
        'diodes',
        'inductors',
        'connectors',
        'relays',
    }

    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    slug = models.SlugField(unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name

    def is_reb(self):
        return self.slug in self.REB_SLUGS

    def save(self, *args, **kwargs):
        if not self.slug:
            if self.name in self.CATEGORY_SLUGS:
                self.slug = self.CATEGORY_SLUGS[self.name]
            else:
                self.slug = slugify(self.name)
                if not self.slug:
                    slug_text = re.sub(r'[^\w\s-]', '', self.name.lower())
                    slug_text = re.sub(r'[-\s]+', '-', slug_text)
                    self.slug = slug_text[:50]
        super().save(*args, **kwargs)


class Product(models.Model):
    MANUFACTURER_CHOICES = [
        # Потребительская электроника
        ('apple', 'Apple'),
        ('samsung', 'Samsung'),
        ('sony', 'Sony'),
        ('lg', 'LG'),
        ('microsoft', 'Microsoft'),
        ('intel', 'Intel'),
        ('amd', 'AMD'),
        # РЭБ-производители
        ('yageo', 'Yageo'),
        ('vishay', 'Vishay'),
        ('murata', 'Murata'),
        ('tdk', 'TDK'),
        ('kemet', 'KEMET'),
        ('st', 'STMicroelectronics'),
        ('nxp', 'NXP'),
        ('ti', 'Texas Instruments'),
        ('infineon', 'Infineon'),
        ('onsemi', 'onsemi'),
        ('bourns', 'Bourns'),
        ('panasonic', 'Panasonic'),
        ('nichicon', 'Nichicon'),
        ('wurth', 'Würth Elektronik'),
        ('other', 'Other'),
    ]

    LIFECYCLE_CHOICES = [
        ('active', 'Active'),
        ('nrnd', 'NRND'),
        ('eol', 'EOL'),
        ('obsolete', 'Obsolete'),
    ]

    name = models.CharField(max_length=300)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    description = models.TextField()
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal('0.00')),
            MaxValueValidator(Decimal('99999999.99')),
        ],
    )
    image = models.ImageField(upload_to='products/', null=True, blank=True)
    stock = models.IntegerField(default=0)
    manufacturer = models.CharField(max_length=50, choices=MANUFACTURER_CHOICES, default='other')
    slug = models.SlugField(unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Технические поля (преимущественно для РЭБ)
    part_number = models.CharField(max_length=100, blank=True, verbose_name='Part Number / SKU')
    lifecycle_status = models.CharField(
        max_length=10, choices=LIFECYCLE_CHOICES, default='active', verbose_name='Lifecycle Status'
    )
    datasheet_url = models.URLField(blank=True, verbose_name='Datasheet URL')
    package_type = models.CharField(max_length=50, blank=True, verbose_name='Package / Корпус')
    parameters = models.JSONField(default=dict, blank=True, verbose_name='Технические параметры')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def is_available(self):
        return self.stock > 0

    def is_reb(self):
        return self.category.slug in Category.REB_SLUGS

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        # Sanity-clamp цены: DecimalField(10, 2) = max 99 999 999.99. Если кто-то
        # (форма, raw SQL, admin) попытается сохранить 1e28 или сравнимое — DB
        # хранит без проблем, но при следующем чтении decimal.InvalidOperation
        # ломает ВСЮ страницу каталога. Каппируем тут, чтобы такое не пролезло.
        if self.price is not None:
            try:
                p = Decimal(self.price)
                if p < 0 or p >= Decimal('100000000'):
                    raise ValueError(
                        f'Product.price вне диапазона DecimalField(10,2): {self.price!r}. '
                        f'Допустимо 0..99 999 999.99.'
                    )
                # Квантизация до 2 знаков — DB drift'а не будет
                self.price = p.quantize(Decimal('0.01'))
            except Exception as exc:
                raise ValueError(f'Невалидная цена: {self.price!r} ({exc})') from exc
        super().save(*args, **kwargs)


class CartItem(models.Model):
    """Корзина. Поддерживает два режима привязки:
    - session_id (для guest) — теряется при истечении сессии (24ч middleware)
    - user (для auth) — переживает logout/login, сохраняется навсегда.
    При login сессионные items мигрируют на user_id (signal в shop/signals.py).
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    session_id = models.CharField(max_length=40, blank=True, default='', db_index=True)
    user = models.ForeignKey(
        'auth.User',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name='cart_items',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.product.name} x {self.quantity}'

    def get_total_price(self):
        return self.product.price * self.quantity


class ViewedProduct(models.Model):
    """История просмотра товаров для auth-юзеров.
    Сессионная история (`recently_viewed_ids` в session) сохраняется отдельно
    для guest. Здесь — персональная история, переживает logout.
    Retention: 90 дней (purge_old_viewed_products command).
    """

    user = models.ForeignKey(
        'auth.User',
        on_delete=models.CASCADE,
        related_name='viewed_products',
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    viewed_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        unique_together = ('user', 'product')
        ordering = ['-viewed_at']
        indexes = [models.Index(fields=['user', '-viewed_at'])]
