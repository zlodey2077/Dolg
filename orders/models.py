import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from shop.models import Product

# Шеренный валидатор для всех DecimalField(10, 2) — защита от 1e+28 input'а,
# который ломает чтение всей страницы (см. shop/models.py:Product.save).
PRICE_VALIDATORS = [
    MinValueValidator(Decimal('0.00')),
    MaxValueValidator(Decimal('99999999.99')),
]


class OrderStatus(models.Model):
    PENDING = 'pending'
    CONFIRMED = 'confirmed'
    PROCESSING = 'processing'
    SHIPPED = 'shipped'
    DELIVERED = 'delivered'
    CANCELLED = 'cancelled'

    CHOICES = [
        (PENDING, 'В ожидании'),
        (CONFIRMED, 'Подтвержден'),
        (PROCESSING, 'На обработке'),
        (SHIPPED, 'Отправлен'),
        (DELIVERED, 'Доставлен'),
        (CANCELLED, 'Отменен'),
    ]

    name = models.CharField(max_length=50, unique=True, choices=CHOICES)

    @classmethod
    def get(cls, name):
        return cls.objects.get_or_create(name=name)[0]
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Статус заказа'
        verbose_name_plural = 'Статусы заказов'
        ordering = ['name']

    def __str__(self):
        return self.get_name_display()


class Order(models.Model):
    PAYMENT_METHODS = [
        ('card', 'Кредитная карта'),
        ('bank_transfer', 'Банковский перевод'),
        ('cash', 'Наличные при доставке'),
        ('wallet', 'Электронный кошелек'),
    ]

    order_number = models.CharField(max_length=20, unique=True, editable=False)
    # user=NULL — заказ оформлен гостем (без регистрации). Контактные данные
    # хранятся в guest_* полях ниже. Гость может потом отследить заказ по
    # guest_token-у (UUID в URL /orders/track/<token>/).
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='orders',
        null=True, blank=True,
    )
    status = models.ForeignKey(OrderStatus, on_delete=models.SET_NULL, null=True)

    # === Guest-чек-аут (без регистрации) ===
    # Заполняются ТОЛЬКО если user is null. Email обязателен — на него уйдёт
    # подтверждение и фискальный чек по 54-ФЗ.
    guest_email = models.EmailField(blank=True, default='')
    guest_name  = models.CharField(max_length=120, blank=True, default='')
    guest_phone = models.CharField(max_length=30,  blank=True, default='')
    # Токен для отслеживания заказа гостем — UUID, передаётся в URL и в email.
    # 32 символа hex без дефисов — безопасно для URL и read-only-доступа.
    guest_token = models.CharField(max_length=32,  blank=True, default='', db_index=True)

    # Shipping info
    shipping_address = models.CharField(max_length=300)
    shipping_city = models.CharField(max_length=100)
    shipping_postal_code = models.CharField(max_length=20)
    shipping_country = models.CharField(max_length=100, default='Россия')

    # Payment info
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='card')
    is_paid = models.BooleanField(default=False)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                       validators=PRICE_VALIDATORS)

    # Notes
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'
        ordering = ['-created_at']

    def __str__(self):
        return f"Заказ {self.order_number}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        # Guest-токен генерим только для гостевых заказов и только при создании.
        if self.user_id is None and not self.guest_token:
            self.guest_token = uuid.uuid4().hex
        super().save(*args, **kwargs)

    @property
    def is_guest(self):
        return self.user_id is None

    @property
    def contact_email(self):
        """Унифицированный email-получатель — для писем/чека работает с любым типом."""
        return self.guest_email if self.is_guest else (self.user.email if self.user else '')

    @property
    def contact_name(self):
        return self.guest_name if self.is_guest else (self.user.get_full_name() or self.user.username if self.user else '')

    def calculate_total(self):
        return sum(item.get_total_price() for item in self.items.all())


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    quantity = models.IntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=PRICE_VALIDATORS)

    class Meta:
        verbose_name = 'Товар в заказе'
        verbose_name_plural = 'Товары в заказах'

    def __str__(self):
        product_name = self.product.name if self.product else 'Удалённый товар'
        return f"{product_name} x {self.quantity}"

    def get_total_price(self):
        return self.price * self.quantity


class Shipment(models.Model):
    SHIPMENT_STATUS = [
        ('pending', 'В ожидании'),
        ('shipped', 'Отправлен'),
        ('in_transit', 'В пути'),
        ('delivered', 'Доставлен'),
        ('failed', 'Ошибка доставки'),
    ]

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='shipment')
    tracking_number = models.CharField(max_length=100, unique=True)
    carrier = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=SHIPMENT_STATUS, default='pending')

    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Отправка'
        verbose_name_plural = 'Отправки'
        ordering = ['-created_at']

    def __str__(self):
        return f"Отправка {self.tracking_number}"


class PaymentTransaction(models.Model):
    PAYMENT_STATUS = [
        ('pending', 'В ожидании'),
        ('processing', 'Обработка'),
        ('succeeded', 'Успешно'),
        ('failed', 'Ошибка'),
        ('cancelled', 'Отменено'),
        ('refunded', 'Возвращено'),
    ]

    PAYMENT_PROVIDER = [
        ('stripe', 'Stripe'),
        ('yandex', 'Yandex.Kassa'),
        ('sberbank', 'Sberbank'),
    ]

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment_transaction')
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    provider = models.CharField(max_length=50, choices=PAYMENT_PROVIDER, default='stripe')

    # Payment details
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='RUB')

    # Transaction IDs
    transaction_id = models.CharField(max_length=255, unique=True, editable=False)  # Stripe payment intent ID
    charge_id = models.CharField(max_length=255, blank=True)  # Stripe charge ID

    # Description for payment gateway
    description = models.TextField(blank=True)

    # Error tracking
    error_message = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Платежная транзакция'
        verbose_name_plural = 'Платежные транзакции'
        ordering = ['-created_at']

    def __str__(self):
        return f"Платеж {self.transaction_id} - {self.get_status_display()}"

    def mark_as_succeeded(self, charge_id=None):
        """Mark transaction as successfully paid"""
        from django.utils import timezone
        self.status = 'succeeded'
        self.paid_at = timezone.now()
        if charge_id:
            self.charge_id = charge_id
        self.save()

        # Mark order as paid
        self.order.is_paid = True
        self.order.status = OrderStatus.get(OrderStatus.CONFIRMED)
        self.order.save()

    def mark_as_failed(self, error_message=''):
        """Mark transaction as failed"""
        self.status = 'failed'
        if error_message:
            self.error_message = error_message
        self.save()
