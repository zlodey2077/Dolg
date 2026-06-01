from django.contrib import admin
from django.db.models import Count, Sum
from django.utils.html import format_html

from Dolg_APP.models import AuditLog

from .models import Order, OrderItem, OrderStatus, PaymentTransaction, Shipment


@admin.register(OrderStatus)
class OrderStatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'price', 'line_total')
    fields = ('product', 'quantity', 'price', 'line_total')

    def line_total(self, obj):
        if obj.pk:
            return f"{obj.get_total_price()} ₽"
        return '—'
    line_total.short_description = 'Сумма'


@admin.action(description='Отметить как «Подтверждён»')
def mark_confirmed(modeladmin, request, queryset):
    _bulk_mark_orders(modeladmin, request, queryset, OrderStatus.CONFIRMED)


@admin.action(description='Отметить как «Отправлен»')
def mark_shipped(modeladmin, request, queryset):
    _bulk_mark_orders(modeladmin, request, queryset, OrderStatus.SHIPPED)


@admin.action(description='Отметить как «Доставлен»')
def mark_delivered(modeladmin, request, queryset):
    _bulk_mark_orders(modeladmin, request, queryset, OrderStatus.DELIVERED)


@admin.action(description='Отметить как «Отменён»')
def mark_cancelled(modeladmin, request, queryset):
    _bulk_mark_orders(modeladmin, request, queryset, OrderStatus.CANCELLED)


def _bulk_mark_orders(modeladmin, request, queryset, status_name):
    status = OrderStatus.get(status_name)
    order_ids = list(queryset.values_list('id', flat=True))
    updated = queryset.update(status=status)
    AuditLog.log(
        actor=request.user,
        action='admin.orders.bulk_status_update',
        object_type='order',
        object_id='bulk',
        payload={
            'status': status_name,
            'updated': updated,
            'sample_ids': order_ids[:50],
        },
        request=request,
    )
    modeladmin.message_user(request, f'{updated} orders moved to {status.get_name_display()}.')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'user', 'status', 'items_count', 'total_amount', 'is_paid', 'created_at')
    list_filter = ('status', 'is_paid', 'payment_method', 'created_at', 'shipping_city')
    search_fields = ('order_number', 'user__username', 'user__email', 'shipping_address')
    readonly_fields = ('order_number', 'total_amount', 'created_at', 'updated_at')
    inlines = [OrderItemInline]
    date_hierarchy = 'created_at'
    autocomplete_fields = ('user',)
    list_select_related = ('user', 'status')
    actions = [mark_confirmed, mark_shipped, mark_delivered, mark_cancelled]
    change_list_template = 'admin/orders/order/change_list.html'

    fieldsets = (
        ('Информация о заказе', {
            'fields': ('order_number', 'user', 'status', 'created_at', 'updated_at')
        }),
        ('Адрес доставки', {
            'fields': ('shipping_address', 'shipping_city', 'shipping_postal_code', 'shipping_country')
        }),
        ('Финансы', {
            'fields': ('total_amount', 'payment_method', 'is_paid')
        }),
        ('Комментарии', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_items_count=Count('items'))

    def items_count(self, obj):
        return getattr(obj, '_items_count', obj.items.count())
    items_count.short_description = 'Позиций'

    def changelist_view(self, request, extra_context=None):
        total_orders = Order.objects.count()
        paid_orders = Order.objects.filter(is_paid=True).count()
        pending_orders = Order.objects.filter(status__name=OrderStatus.PENDING).count()
        cancelled_orders = Order.objects.filter(status__name=OrderStatus.CANCELLED).count()
        revenue = Order.objects.filter(is_paid=True).aggregate(total=Sum('total_amount'))['total'] or 0

        extra_context = extra_context or {}
        extra_context['order_dashboard'] = {
            'total_orders': total_orders,
            'paid_orders': paid_orders,
            'pending_orders': pending_orders,
            'cancelled_orders': cancelled_orders,
            'revenue': revenue,
        }
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product', 'quantity', 'price', 'line_total')
    list_filter = ('order__created_at', 'order__status')
    search_fields = ('order__order_number', 'product__name')
    readonly_fields = ('order', 'product', 'price')
    autocomplete_fields = ('order', 'product')
    list_select_related = ('order', 'product')

    def line_total(self, obj):
        return f"{obj.get_total_price()} ₽"
    line_total.short_description = 'Сумма'


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ('order', 'tracking_number', 'carrier', 'status', 'shipped_at', 'delivered_at')
    list_filter = ('status', 'carrier', 'shipped_at')
    search_fields = ('order__order_number', 'tracking_number', 'carrier')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'
    autocomplete_fields = ('order',)
    list_select_related = ('order',)


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'order', 'status_badge', 'amount', 'currency', 'provider', 'created_at')
    list_filter = ('status', 'provider', 'currency', 'created_at')
    search_fields = ('transaction_id', 'order__order_number', 'charge_id')
    readonly_fields = ('transaction_id', 'created_at', 'updated_at', 'paid_at')
    date_hierarchy = 'created_at'
    autocomplete_fields = ('order',)
    list_select_related = ('order',)

    fieldsets = (
        ('Транзакция', {'fields': ('transaction_id', 'order', 'status', 'provider')}),
        ('Сумма и валюта', {'fields': ('amount', 'currency')}),
        ('Платёжные ID', {'fields': ('charge_id',)}),
        ('Информация', {'fields': ('description', 'error_message')}),
        ('Время', {'fields': ('created_at', 'updated_at', 'paid_at')}),
    )

    def status_badge(self, obj):
        colors = {
            'succeeded': '#28a745',
            'failed':    '#dc3545',
            'pending':   '#6c757d',
            'processing':'#17a2b8',
            'cancelled': '#999',
            'refunded':  '#ffc107',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="color:{}; font-weight:600;">●</span> {}',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Статус'
