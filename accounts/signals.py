from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Автоматически создавать UserProfile при регистрации нового пользователя."""
    if created:
        UserProfile.objects.get_or_create(user=instance)


# Брутфорс-локаут django-axes → ops-алерт в отдельный канал (не в пользовательский чат).
try:
    from axes.signals import user_locked_out

    @receiver(user_locked_out)
    def alert_user_locked_out(sender, request=None, username=None, ip_address=None, **kwargs):
        from Dolg_APP.services.ops_alerts import notify_ops

        ip = ip_address or (getattr(request, 'META', {}).get('REMOTE_ADDR') if request else None)
        notify_ops(
            'Брутфорс-локаут (django-axes)',
            'Превышен лимит неудачных входов — аккаунт/IP временно заблокирован.',
            level='warning',
            kind='security',
            meta={
                'username': username or '—',
                'ip': ip or '—',
                'path': getattr(request, 'path', '—') if request else '—',
            },
        )
except Exception:  # axes не установлен/не активен — сигнал просто не подключаем
    pass
