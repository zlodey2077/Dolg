"""Shared role helpers for the DOLG permission model."""

MANAGER_GROUP = 'Менеджер'
CUSTOMER_GROUP = 'Пользователь'


def is_manager(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user.groups.filter(name=MANAGER_GROUP).exists())
    )
