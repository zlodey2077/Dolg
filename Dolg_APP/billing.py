"""Биллинг-хелперы для DOLG Pro-tier.

ВАЖНО: это MOCK для дипломного проекта. Реальный платёжный flow
требует merchant-account + webhook'ов + соответствия 54-ФЗ для РФ.
Здесь:
- activate_trial(user) — даёт 14 дней Pro, ставит trial_used=True
- activate_pro(user, months) — выдаёт Pro вручную (через UI «Купить»)
- cancel(user) — auto_renew=False, доступ до конца period_end
- restore(user) — восстановить auto_renew (если ещё не expired)
"""

from datetime import timedelta

from django.utils import timezone

from .models import Subscription

TRIAL_DAYS = 14
DEFAULT_PRO_MONTHS = 1


def get_or_create_subscription(user):
    sub, _ = Subscription.objects.get_or_create(
        user=user,
        defaults={'tier': 'free', 'status': 'active'},
    )
    return sub


def activate_trial(user) -> tuple[bool, str]:
    """Активирует 14-дневный trial. Один раз на пользователя.

    Returns (success, message).
    """
    sub = get_or_create_subscription(user)
    if sub.trial_used:
        return False, 'Trial уже был активирован ранее. Доступен только один раз на аккаунт.'
    if sub.is_pro_active():
        return False, 'У вас уже есть активная Pro-подписка.'

    sub.tier = 'pro'
    sub.status = 'trial'
    sub.provider = 'trial'
    sub.period_start = timezone.now()
    sub.period_end = timezone.now() + timedelta(days=TRIAL_DAYS)
    sub.trial_used = True
    sub.auto_renew = False
    sub.save()
    return True, f'Pro-trial активирован на {TRIAL_DAYS} дней.'


def activate_pro(user, months=DEFAULT_PRO_MONTHS, provider='manual') -> tuple[bool, str]:
    """Выдать Pro вручную / после mock-оплаты.

    Продлевает существующую подписку — если уже Pro, добавляет к period_end.
    """
    sub = get_or_create_subscription(user)
    now = timezone.now()
    base = sub.period_end if (sub.period_end and sub.period_end > now) else now
    sub.tier = 'pro'
    sub.status = 'active'
    sub.provider = provider
    if not sub.period_start or sub.period_start > now:
        sub.period_start = now
    sub.period_end = base + timedelta(days=30 * months)
    sub.auto_renew = True
    sub.save()
    return True, f'Pro активирован на {months} мес. Действует до {sub.period_end.date()}.'


def cancel(user) -> tuple[bool, str]:
    """Отменить auto-renew. Доступ остаётся до конца period_end."""
    sub = get_or_create_subscription(user)
    if not sub.is_pro_active():
        return False, 'Активной подписки нет.'
    sub.auto_renew = False
    sub.status = 'cancelled'
    sub.save(update_fields=['auto_renew', 'status', 'updated_at'])
    return True, f'Подписка отменена. Доступ останется до {sub.period_end.date()}.'


def restore_subscription(user) -> tuple[bool, str]:
    """Восстановить отменённую подписку (вернуть auto_renew)."""
    sub = get_or_create_subscription(user)
    if sub.status != 'cancelled' or not sub.is_pro_active():
        return False, 'Нечего восстанавливать.'
    sub.auto_renew = True
    sub.status = 'active'
    sub.save(update_fields=['auto_renew', 'status', 'updated_at'])
    return True, 'Подписка восстановлена.'
