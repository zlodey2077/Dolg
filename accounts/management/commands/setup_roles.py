from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

from accounts.roles import CUSTOMER_GROUP, MANAGER_GROUP


class Command(BaseCommand):
    help = 'Создаёт базовые роли DOLG и назначает права менеджера на каталог и заказы.'

    MANAGER_PERMISSIONS = [
        ('shop', 'category', ['view', 'add', 'change']),
        ('shop', 'product', ['view', 'add', 'change']),
        ('shop', 'cartitem', ['view']),
        ('orders', 'order', ['view', 'change']),
        ('orders', 'orderitem', ['view']),
        ('orders', 'orderstatus', ['view', 'change']),
        ('orders', 'shipment', ['view', 'add', 'change']),
        ('orders', 'paymenttransaction', ['view']),
    ]

    def handle(self, *args, **options):
        manager_group, _ = Group.objects.get_or_create(name=MANAGER_GROUP)
        customer_group, _ = Group.objects.get_or_create(name=CUSTOMER_GROUP)

        permission_codes = []
        for app_label, model, actions in self.MANAGER_PERMISSIONS:
            for action in actions:
                permission_codes.append(f'{action}_{model}')

        permissions = Permission.objects.filter(
            content_type__app_label__in=['shop', 'orders'],
            codename__in=permission_codes,
        )
        manager_group.permissions.set(permissions)

        self.stdout.write(self.style.SUCCESS(
            f'Роли готовы: "{MANAGER_GROUP}" ({permissions.count()} прав), "{CUSTOMER_GROUP}".'
        ))
