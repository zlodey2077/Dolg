import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.models import Address
from shop.models import CartItem

from .models import Order, OrderItem, OrderStatus

_logger = logging.getLogger(__name__)


def _send_order_confirmation(order, request=None):
    """Confirmation email. Для гостя — с tracking-ссылкой /orders/track/<token>/.
    Для auth — со ссылкой на /orders/."""
    to_email = order.contact_email
    if not to_email:
        return

    subject = f'DOLG: заказ {order.order_number} создан'
    name = order.contact_name or 'покупатель'
    body_lines = [
        f'Здравствуйте, {name}!',
        '',
        f'Ваш заказ {order.order_number} на сумму {order.total_amount} ₽ создан.',
    ]
    if order.is_guest and request is not None:
        track_path = f'/orders/track/{order.guest_token}/'
        track_url = request.build_absolute_uri(track_path) if request else track_path
        body_lines += [
            '',
            f'Отследить статус заказа: {track_url}',
            'Эта ссылка работает без регистрации — сохраните её.',
        ]
    else:
        body_lines += ['Статус заказа можно посмотреть в личном кабинете.']
    body_lines += ['', 'Это автоматическое уведомление проекта DOLG.']
    body = '\n'.join(body_lines)

    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [to_email],
            fail_silently=False,
        )
    except Exception as exc:
        _logger.warning(
            'Не удалось отправить confirmation-email для заказа %s (%s): %s',
            order.order_number,
            to_email,
            exc,
        )


def _ensure_session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def checkout(request):
    """Чек-аут. Поддерживает два режима:
    - Auth: пользователь выбирает один из сохранённых адресов
    - Guest: вводит email/name/phone + адрес вручную, заказ привязывается к
      session_id. После создания — tracking-ссылка по guest_token.
    Email-verify gate работает ТОЛЬКО для auth (у guest нет profile.email_verified).
    """
    is_auth = request.user.is_authenticated

    # Email-verify gate — только для auth-юзеров
    if is_auth and not getattr(getattr(request.user, 'profile', None), 'email_verified', False):
        messages.warning(
            request,
            'Подтвердите email перед оформлением заказа. '
            'Письмо отправлено при регистрации — проверьте «Входящие» и «Спам». '
            'Можно отправить ещё раз кнопкой в профиле.',
        )
        return redirect('accounts:profile')

    # Корзина: для auth по user, для guest по session_id
    if is_auth:
        cart_items = CartItem.objects.select_related('product').filter(user=request.user)
    else:
        session_id = _ensure_session_key(request)
        cart_items = CartItem.objects.select_related('product').filter(
            session_id=session_id,
            user__isnull=True,
        )

    if not cart_items.exists():
        messages.error(request, 'Ваша корзина пуста')
        return redirect('shop:cart')

    addresses = request.user.addresses.all() if is_auth else []
    default_address = addresses.filter(is_default=True).first() if is_auth else None
    total_amount = sum(item.get_total_price() for item in cart_items)
    ctx = {
        'cart_items': cart_items,
        'addresses': addresses,
        'default_address': default_address,
        'total_amount': total_amount,
        'is_guest': not is_auth,
    }

    if request.method == 'POST':
        payment_method = request.POST.get('payment_method', 'card')
        notes = request.POST.get('notes', '')

        # === Сбор адреса доставки + контактов ===
        if is_auth:
            address_id = request.POST.get('address')
            if not address_id:
                messages.error(request, 'Выберите адрес доставки')
                return render(request, 'orders/checkout.html', ctx)
            address = get_object_or_404(Address, id=address_id, user=request.user)
            ship = {
                'shipping_address': address.address,
                'shipping_city': address.city,
                'shipping_postal_code': address.postal_code,
                'shipping_country': address.country,
            }
            guest_fields = {}
        else:
            # Гость: всё руками + валидация обязательных контактов
            guest_email = (request.POST.get('guest_email') or '').strip()
            guest_name = (request.POST.get('guest_name') or '').strip()
            guest_phone = (request.POST.get('guest_phone') or '').strip()
            ship_address = (request.POST.get('shipping_address') or '').strip()
            ship_city = (request.POST.get('shipping_city') or '').strip()
            ship_postal = (request.POST.get('shipping_postal_code') or '').strip()
            ship_country = (request.POST.get('shipping_country') or 'Россия').strip()

            errors = []
            if '@' not in guest_email or len(guest_email) < 5:
                errors.append('Укажите корректный email — на него придёт подтверждение заказа')
            if not guest_name:
                errors.append('Укажите имя')
            if not guest_phone:
                errors.append('Укажите телефон')
            if not ship_address:
                errors.append('Укажите адрес доставки')
            if not ship_city:
                errors.append('Укажите город')
            if errors:
                for e in errors:
                    messages.error(request, e)
                ctx['guest_form'] = {
                    'email': guest_email,
                    'name': guest_name,
                    'phone': guest_phone,
                    'address': ship_address,
                    'city': ship_city,
                    'postal_code': ship_postal,
                    'country': ship_country,
                }
                return render(request, 'orders/checkout.html', ctx)

            ship = {
                'shipping_address': ship_address,
                'shipping_city': ship_city,
                'shipping_postal_code': ship_postal,
                'shipping_country': ship_country,
            }
            guest_fields = {
                'guest_email': guest_email,
                'guest_name': guest_name,
                'guest_phone': guest_phone,
            }

        # === Транзакция: stock-lock + создание Order + декремент stock ===
        from shop.models import Product

        with transaction.atomic():
            product_ids = [ci.product_id for ci in cart_items]
            locked_products = {
                p.id: p for p in Product.objects.select_for_update().filter(id__in=product_ids)
            }
            for cart_item in cart_items:
                p = locked_products.get(cart_item.product_id)
                if p is None or p.stock < cart_item.quantity:
                    available = p.stock if p else 0
                    messages.error(
                        request,
                        f'Недостаточно товара "{cart_item.product.name}" на складе (доступно: {available})',
                    )
                    return render(request, 'orders/checkout.html', ctx)

            order = Order.objects.create(
                user=request.user if is_auth else None,
                status=OrderStatus.get(OrderStatus.PENDING),
                payment_method=payment_method,
                total_amount=total_amount,
                notes=notes,
                is_paid=False,
                **ship,
                **guest_fields,
            )

            for cart_item in cart_items:
                p = locked_products[cart_item.product_id]
                OrderItem.objects.create(
                    order=order,
                    product=p,
                    quantity=cart_item.quantity,
                    price=p.price,
                )
                p.stock -= cart_item.quantity
                p.save(update_fields=['stock'])

            cart_items.delete()

        _send_order_confirmation(order, request=request)

        if is_auth:
            messages.success(request, f'Заказ {order.order_number} создан. Перейдите к оплате.')
            return redirect('orders:create_payment', order_id=order.id)
        else:
            # Гость: показываем tracking-страницу + ссылку запомнить
            messages.success(
                request,
                f'Заказ {order.order_number} создан! Ссылка для отслеживания отправлена на {order.guest_email}.',
            )
            return redirect('orders:guest_track', token=order.guest_token)

    return render(request, 'orders/checkout.html', ctx)


def guest_track(request, token):
    """Read-only страница заказа по guest_token. Доступна без аутентификации."""
    if len(token) != 32 or any(ch not in '0123456789abcdef' for ch in token):
        raise Http404('Invalid guest tracking token')

    order = get_object_or_404(
        Order.objects.select_related('status').prefetch_related('items__product'),
        guest_token=token,
        user__isnull=True,
    )
    return render(request, 'orders/guest_track.html', {'order': order})


@login_required(login_url='accounts:login')
def order_list(request):
    # Аннотируем items_count и select_related('status') — иначе шаблон вызывал
    # {{ order.items.count }} в loop (N+1 SQL) и order.status.* (отдельный SELECT
    # на каждый заказ для FK→Status). На 50 заказах было 50+ лишних запросов.
    from django.db.models import Count

    orders = request.user.orders.select_related('status').annotate(items_count=Count('items')).all()
    context = {'orders': orders}
    return render(request, 'orders/order_list.html', context)


@login_required(login_url='accounts:login')
def order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    items = order.items.select_related('product').all()

    context = {
        'order': order,
        'items': items,
    }
    return render(request, 'orders/order_detail.html', context)


@login_required(login_url='accounts:login')
@require_http_methods(['POST'])
def cancel_order(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    # Only allow cancelling pending or confirmed orders
    if order.status.name not in [OrderStatus.PENDING, OrderStatus.CONFIRMED]:
        messages.error(request, 'Этот заказ нельзя отменить')
        return redirect('orders:order_detail', order_id=order.id)

    with transaction.atomic():
        order.status = OrderStatus.get(OrderStatus.CANCELLED)
        order.save(update_fields=['status'])

        for item in order.items.select_related('product'):
            if item.product:
                item.product.stock += item.quantity
                item.product.save(update_fields=['stock'])

    messages.success(request, 'Заказ отменен')
    return redirect('orders:order_detail', order_id=order.id)


@login_required(login_url='accounts:login')
@require_http_methods(['POST'])
def repeat_order(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    added_positions = 0
    skipped_positions = 0
    limited_positions = 0

    for item in order.items.select_related('product'):
        product = item.product
        if not product or product.stock <= 0:
            skipped_positions += 1
            continue

        quantity_to_add = min(item.quantity, product.stock)
        if quantity_to_add < item.quantity:
            limited_positions += 1

        cart_item, created = CartItem.objects.get_or_create(
            product=product,
            user=request.user,
            defaults={'quantity': quantity_to_add, 'session_id': ''},
        )
        if not created:
            cart_item.quantity = min(cart_item.quantity + quantity_to_add, product.stock)
            cart_item.save(update_fields=['quantity'])

        added_positions += 1

    if added_positions:
        messages.success(request, f'Позиции из заказа {order.order_number} добавлены в корзину.')
    if limited_positions:
        messages.warning(request, 'Часть позиций добавлена в меньшем количестве из-за текущих остатков.')
    if skipped_positions:
        messages.warning(request, 'Некоторые позиции пропущены: товар удалён или отсутствует на складе.')
    if not added_positions:
        messages.error(request, 'Не удалось повторить заказ: доступных товаров нет.')

    return redirect('shop:cart')
