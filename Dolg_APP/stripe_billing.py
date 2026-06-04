"""Stripe-биллинг для Pro-подписок DOLG.

Архитектура:
- **Stripe Checkout Session** (hosted page) для recurring-подписки.
  Юзер уходит на stripe.com → возвращается на success_url с session_id.
  Это проще и безопаснее, чем PaymentElement: Stripe сам обрабатывает 3-DS,
  валидацию карты, retry, refunds — мы просто слушаем webhooks.

- **Webhook** `/billing/stripe-webhook/` обрабатывает:
  * `checkout.session.completed` — продлеваем Subscription, ставим Pro
  * `customer.subscription.updated` — синхронизируем period_end (renew)
  * `customer.subscription.deleted` — статус cancelled (или expired)
  * `invoice.payment_failed` — переключаем в grace-period

- **Demo-mode fallback**: при `STRIPE_SECRET_KEY='demo_mode'` (значение
  по умолчанию из .env.example) — все функции возвращают (False, ...).
  UI в `views.billing_activate_pro` сам переключится на mock-flow
  через `Dolg_APP.billing.activate_pro`.

ВАЖНО: для production:
  1. Зарегистрировать продукт+price в Stripe Dashboard, скопировать price_id
     в `STRIPE_PRO_PRICE_ID` env-var.
  2. `STRIPE_SECRET_KEY` (sk_test_... или sk_live_...) — настоящий ключ.
  3. `STRIPE_WEBHOOK_SECRET` (whsec_...) — из endpoint в dashboard.
  4. Прописать webhook-URL в Stripe Dashboard → Developers → Webhooks:
     `https://<domain>/billing/stripe-webhook/`
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from .billing import get_or_create_subscription
from .models import AuditLog, Subscription

try:
    import stripe

    if settings.STRIPE_SECRET_KEY and 'demo_mode' not in settings.STRIPE_SECRET_KEY.lower():
        stripe.api_key = settings.STRIPE_SECRET_KEY
except ImportError:
    stripe = None


def is_stripe_live() -> bool:
    """True если Stripe настоящий, не demo-mode."""
    return (
        stripe is not None
        and bool(settings.STRIPE_SECRET_KEY)
        and 'demo_mode' not in settings.STRIPE_SECRET_KEY.lower()
    )


def get_pro_price_id() -> str:
    """price_id Pro-тарифа из env. В demo-mode возвращает плейсхолдер."""
    return getattr(settings, 'STRIPE_PRO_PRICE_ID', '') or 'price_demo_placeholder'


# ────────────────────────────────────────────────────────────────────────
# Checkout Session — создаём при «Buy Pro» клике
# ────────────────────────────────────────────────────────────────────────


def create_checkout_session(user, request) -> tuple[bool, str, str]:
    """Создаёт Stripe Checkout Session для Pro-подписки.

    Returns: (success, url_or_message, session_id).
    Если demo-mode — (False, 'demo_mode', '') — caller должен фолбекнуться
    на `Dolg_APP.billing.activate_pro` напрямую.
    """
    if not is_stripe_live():
        return False, 'demo_mode', ''

    sub = get_or_create_subscription(user)

    success_url = (
        request.build_absolute_uri(reverse('hello:billing_checkout_success'))
        + '?session_id={CHECKOUT_SESSION_ID}'
    )
    cancel_url = request.build_absolute_uri(reverse('hello:billing_plans'))

    try:
        session_kwargs = {
            'mode': 'subscription',
            'line_items': [
                {
                    'price': get_pro_price_id(),
                    'quantity': 1,
                }
            ],
            'success_url': success_url,
            'cancel_url': cancel_url,
            'client_reference_id': str(user.id),
            'metadata': {
                'user_id': str(user.id),
                'username': user.username,
            },
        }
        # Если у юзера уже есть Stripe customer — переиспользуем
        if sub.stripe_customer_id:
            session_kwargs['customer'] = sub.stripe_customer_id
        else:
            session_kwargs['customer_email'] = user.email

        session = stripe.checkout.Session.create(**session_kwargs)
        return True, session.url, session.id
    except Exception as e:
        return False, f'stripe error: {e}', ''


# ────────────────────────────────────────────────────────────────────────
# Webhook handlers — вызываются из view'а после verify_signature
# ────────────────────────────────────────────────────────────────────────


def handle_checkout_completed(event_data: dict) -> bool:
    """Stripe прислал checkout.session.completed — пользователь оплатил.

    Связываем Subscription c stripe_customer_id + stripe_subscription_id,
    переключаем tier='pro', status='active', считаем period_end из subscription.
    """
    session = event_data
    user_id = session.get('client_reference_id') or (session.get('metadata') or {}).get('user_id')
    if not user_id:
        return False

    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        user = User.objects.get(pk=int(user_id))
    except User.DoesNotExist, ValueError, TypeError:
        return False

    customer_id = session.get('customer') or ''
    sub_id = session.get('subscription') or ''

    # Получаем актуальный period_end из Stripe Subscription
    period_end = None
    if sub_id and is_stripe_live():
        try:
            stripe_sub = stripe.Subscription.retrieve(sub_id)
            ts = stripe_sub.get('current_period_end')
            if ts:
                period_end = datetime.fromtimestamp(int(ts), tz=UTC)
        except Exception:
            pass
    if period_end is None:
        # Fallback: считаем 30 дней от now (стандартный monthly tier)
        period_end = timezone.now() + timedelta(days=30)

    sub = get_or_create_subscription(user)
    sub.tier = 'pro'
    sub.status = 'active'
    sub.provider = 'stripe'
    sub.stripe_customer_id = customer_id
    sub.stripe_subscription_id = sub_id
    sub.period_start = timezone.now()
    sub.period_end = period_end
    sub.auto_renew = True
    sub.save()

    AuditLog.log(
        actor=user,
        action='billing.stripe.checkout_completed',
        organization=None,
        object_type='Subscription',
        object_id=sub.id,
        payload={'session_id': session.get('id'), 'customer': customer_id, 'subscription': sub_id},
    )
    return True


def handle_subscription_updated(event_data: dict) -> bool:
    """customer.subscription.updated — продление / изменение."""
    sub_id = event_data.get('id')
    if not sub_id:
        return False
    try:
        sub = Subscription.objects.get(stripe_subscription_id=sub_id)
    except Subscription.DoesNotExist:
        return False

    status_map = {
        'active': 'active',
        'trialing': 'trial',
        'past_due': 'active',  # grace period — доступ остаётся, но Stripe пытается списать
        'canceled': 'cancelled',
        'unpaid': 'expired',
        'incomplete': 'expired',
        'incomplete_expired': 'expired',
    }
    stripe_status = event_data.get('status', 'active')
    sub.status = status_map.get(stripe_status, sub.status)

    ts = event_data.get('current_period_end')
    if ts:
        sub.period_end = datetime.fromtimestamp(int(ts), tz=UTC)

    sub.auto_renew = not event_data.get('cancel_at_period_end', False)
    sub.save(update_fields=['status', 'period_end', 'auto_renew', 'updated_at'])
    return True


def handle_subscription_deleted(event_data: dict) -> bool:
    """customer.subscription.deleted — подписка окончательно завершена."""
    sub_id = event_data.get('id')
    if not sub_id:
        return False
    try:
        sub = Subscription.objects.get(stripe_subscription_id=sub_id)
    except Subscription.DoesNotExist:
        return False
    sub.status = 'expired'
    sub.auto_renew = False
    # period_end оставляем как был — если у юзера ещё есть оплаченные дни,
    # доступ работает до конца. is_pro_active() проверит сам.
    sub.save(update_fields=['status', 'auto_renew', 'updated_at'])
    return True


def handle_invoice_payment_failed(event_data: dict) -> bool:
    """invoice.payment_failed — карта отклонила платёж. Grace-период."""
    sub_id = event_data.get('subscription')
    if not sub_id:
        return False
    try:
        sub = Subscription.objects.get(stripe_subscription_id=sub_id)
    except Subscription.DoesNotExist:
        return False
    # Не отключаем сразу — Stripe пытается списать ещё несколько раз.
    # Когда окончательно сорвётся, прилетит customer.subscription.deleted.
    sub.status = 'active'  # оставляем «active», ожидаем retry или deleted
    sub.save(update_fields=['status', 'updated_at'])
    return True


# ────────────────────────────────────────────────────────────────────────
# Cancel — отмена на стороне Stripe (отменит auto-renew, доступ до периода)
# ────────────────────────────────────────────────────────────────────────


def cancel_at_period_end(sub: Subscription) -> tuple[bool, str]:
    """Просим Stripe не продлевать подписку. Доступ до текущего period_end сохраняется."""
    if not is_stripe_live() or not sub.stripe_subscription_id:
        return False, 'demo_mode_or_no_stripe_id'
    try:
        stripe.Subscription.modify(sub.stripe_subscription_id, cancel_at_period_end=True)
        sub.auto_renew = False
        sub.status = 'cancelled'
        sub.save(update_fields=['auto_renew', 'status', 'updated_at'])
        return True, 'Подписка отменена. Доступ останется до конца оплаченного периода.'
    except Exception as e:
        return False, f'stripe error: {e}'
