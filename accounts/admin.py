from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import Address, UserProfile
from .roles import MANAGER_GROUP


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Профиль пользователя'
    fields = (
        'display_name', 'headline', 'phone', 'address', 'city', 'postal_code',
        'country', 'avatar', 'bio', 'preferred_theme', 'accent_color',
        'default_unit_system', 'start_page', 'ai_tone',
        'show_profile_public', 'show_engineering_badges',
        'allow_ai_training',
    )


class AddressInline(admin.TabularInline):
    model = Address
    extra = 0
    fields = ('title', 'address', 'city', 'postal_code', 'country', 'is_default')


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline, AddressInline)
    list_display = ('username', 'email', 'first_name', 'last_name', 'role_label', 'is_staff', 'date_joined')
    list_select_related = ('profile',)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('groups')

    def role_label(self, obj):
        if obj.is_superuser:
            return 'Администратор'
        if any(group.name == MANAGER_GROUP for group in obj.groups.all()):
            return 'Менеджер'
        return 'Пользователь'
    role_label.short_description = 'Роль'


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'display_name', 'phone', 'city', 'country', 'preferred_theme', 'accent_color', 'created_at')
    list_filter = ('country', 'city', 'preferred_theme', 'accent_color', 'default_unit_system', 'ai_tone', 'created_at')
    search_fields = ('user__username', 'user__email', 'display_name', 'headline', 'phone')
    readonly_fields = ('created_at', 'updated_at')
    list_select_related = ('user',)
    autocomplete_fields = ('user',)
    date_hierarchy = 'created_at'
    fieldsets = (
        ('Пользователь', {'fields': ('user',)}),
        ('Контакты', {'fields': ('display_name', 'headline', 'phone', 'avatar', 'bio')}),
        ('Адрес по умолчанию', {'fields': ('address', 'city', 'postal_code', 'country')}),
        ('Персонализация', {
            'fields': (
                'preferred_theme', 'accent_color', 'default_unit_system',
                'start_page', 'ai_tone', 'show_profile_public',
                'show_engineering_badges', 'allow_ai_training',
            )
        }),
        ('Метаданные', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'address', 'city', 'country', 'is_default', 'created_at')
    list_filter = ('is_default', 'country', 'city', 'created_at')
    search_fields = ('title', 'address', 'city', 'user__username', 'user__email')
    readonly_fields = ('created_at',)
    list_editable = ('is_default',)
    autocomplete_fields = ('user',)
    list_select_related = ('user',)
    date_hierarchy = 'created_at'
