from django.contrib import admin
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from .models import CartItem, Category, Product


class DatasheetQualityFilter(admin.SimpleListFilter):
    title = 'datasheet quality'
    parameter_name = 'datasheet_quality'

    def lookups(self, request, model_admin):
        return (
            ('has_url', 'Has datasheet URL'),
            ('extracted', 'Datasheet extracted'),
            ('needs_review', 'Needs data review'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'has_url':
            return queryset.exclude(datasheet_url='')
        if value == 'extracted':
            return queryset.filter(parameters__has_key='datasheet_extracted')
        if value == 'needs_review':
            return queryset.filter(parameters__needs_moderation=True)
        return queryset


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'products_count', 'description')
    search_fields = ('name',)
    readonly_fields = ('created_at',)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_products_count=Count('products'))

    @admin.display(description='Товаров', ordering='_products_count')
    def products_count(self, obj):
        return obj._products_count

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'part_number', 'category', 'manufacturer', 'lifecycle_status',
        'price', 'stock', 'datasheet_status', 'model_status', 'image_status',
        'needs_review_flag', 'created_at',
    )
    list_filter = ('category', 'manufacturer', 'lifecycle_status', 'package_type', DatasheetQualityFilter, 'created_at')
    list_editable = ('lifecycle_status', 'price', 'stock')
    search_fields = ('name', 'description', 'part_number', 'package_type', 'datasheet_url')
    readonly_fields = ('created_at', 'updated_at', 'data_quality_summary')
    autocomplete_fields = ('category',)
    date_hierarchy = 'created_at'
    list_select_related = ('category',)
    save_on_top = True
    change_list_template = 'admin/shop/product/change_list.html'
    actions = (
        'enrich_datasheet_metadata',
        'mark_needs_data_review',
        'clear_needs_data_review',
        'mark_lifecycle_active',
    )
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'category', 'description', 'image')}),
        ('Цена и наличие', {'fields': ('price', 'stock')}),
        ('Технические данные', {'fields': ('part_number', 'manufacturer', 'lifecycle_status', 'package_type', 'datasheet_url', 'parameters')}),
        ('Контроль качества данных', {'fields': ('data_quality_summary',), 'classes': ('collapse',)}),
        ('Метаданные', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def changelist_view(self, request, extra_context=None):
        stats = {
            'total': Product.objects.count(),
            'reb': Product.objects.filter(category__slug__in=Category.REB_SLUGS).count(),
            'missing_datasheet': Product.objects.filter(
                category__slug__in=Category.REB_SLUGS,
                datasheet_url='',
            ).count(),
            'datasheet_extracted': Product.objects.filter(parameters__has_key='datasheet_extracted').count(),
            'missing_image': Product.objects.filter(Q(image__isnull=True) | Q(image='')).count(),
            'needs_review': Product.objects.filter(parameters__needs_moderation=True).count(),
            'out_of_stock': Product.objects.filter(stock__lte=0).count(),
            'low_stock': Product.objects.filter(stock__gt=0, stock__lte=3).count(),
        }
        extra_context = extra_context or {}
        extra_context['catalog_dashboard'] = stats
        return super().changelist_view(request, extra_context=extra_context)

    @admin.display(description='Datasheet')
    def datasheet_status(self, obj):
        if (obj.parameters or {}).get('datasheet_extracted'):
            return format_html('<span style="color:#168a3a;font-weight:600;">DI</span>')
        if obj.datasheet_url:
            return format_html('<span style="color:#b8860b;font-weight:600;">URL</span>')
        return format_html('<span style="color:#b3261e;">нет</span>')

    @admin.display(description='Модели')
    def model_status(self, obj):
        params = obj.parameters or {}
        flags = []
        if params.get('spice_model'):
            flags.append('SPICE')
        if params.get('cad_model_url') or params.get('cad_model'):
            flags.append('CAD')
        return ', '.join(flags) if flags else 'нет'

    @admin.display(description='Фото')
    def image_status(self, obj):
        if not obj.image:
            return format_html('<span style="color:#b3261e;">нет</span>')
        name = getattr(obj.image, 'name', '')
        if name.lower().endswith('.svg'):
            return 'SVG'
        return 'фото'

    @admin.display(description='Review')
    def needs_review_flag(self, obj):
        return 'да' if (obj.parameters or {}).get('needs_moderation') else ''

    @admin.display(description='Сводка качества данных')
    def data_quality_summary(self, obj):
        if not obj.pk:
            return 'Сохраните товар, чтобы увидеть сводку.'
        params = obj.parameters or {}
        rows = [
            ('Part number', obj.part_number or 'нет'),
            ('Datasheet URL', 'есть' if obj.datasheet_url else 'нет'),
            ('Datasheet Intelligence', 'есть' if params.get('datasheet_extracted') else 'нет'),
            ('SPICE model', 'есть' if params.get('spice_model') else 'нет'),
            ('CAD model', 'есть' if params.get('cad_model_url') or params.get('cad_model') else 'нет'),
            ('Нужна проверка', 'да' if params.get('needs_moderation') else 'нет'),
        ]
        return format_html(
            '<ul style="margin:0 0 0 1rem;">{}</ul>',
            format_html_join('', '<li><strong>{}:</strong> {}</li>', rows),
        )

    @admin.action(description='Обновить Datasheet Intelligence из карточки')
    def enrich_datasheet_metadata(self, request, queryset):
        from .services.datasheet_intelligence import build_product_datasheet_record

        updated = 0
        for product in queryset.select_related('category'):
            params = dict(product.parameters or {})
            params['datasheet_extracted'] = build_product_datasheet_record(product)
            params['datasheet_extracted']['admin_updated_at'] = timezone.now().isoformat()
            product.parameters = params
            product.save(update_fields=['parameters', 'updated_at'])
            updated += 1
        self.message_user(request, f'Datasheet Intelligence обновлен для {updated} товаров.')

    @admin.action(description='Пометить как требующие проверки данных')
    def mark_needs_data_review(self, request, queryset):
        updated = 0
        for product in queryset:
            params = dict(product.parameters or {})
            params['needs_moderation'] = True
            product.parameters = params
            product.save(update_fields=['parameters', 'updated_at'])
            updated += 1
        self.message_user(request, f'Помечено для проверки: {updated}.')

    @admin.action(description='Снять флаг проверки данных')
    def clear_needs_data_review(self, request, queryset):
        updated = 0
        for product in queryset:
            params = dict(product.parameters or {})
            params.pop('needs_moderation', None)
            product.parameters = params
            product.save(update_fields=['parameters', 'updated_at'])
            updated += 1
        self.message_user(request, f'Флаг проверки снят: {updated}.')

    @admin.action(description='Lifecycle: Active')
    def mark_lifecycle_active(self, request, queryset):
        updated = queryset.update(lifecycle_status='active')
        self.message_user(request, f'Lifecycle Active установлен для {updated} товаров.')

@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'quantity', 'line_total', 'session_id', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('product__name', 'product__part_number', 'user__username', 'session_id')
    list_select_related = ('product', 'user')
    readonly_fields = ('created_at',)

    @admin.display(description='Сумма')
    def line_total(self, obj):
        return obj.get_total_price()


admin.site.site_header = 'DOLG: инженерная админ-панель'
admin.site.site_title = 'DOLG admin'
admin.site.index_title = 'Управление каталогом, проектами и данными'
