"""
Payment processing views for Stripe integration.
Handles payment creation, callback, and webhook verification.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Order, PaymentTransaction

try:
    import stripe
    stripe.api_key = settings.STRIPE_SECRET_KEY
except (ImportError, AttributeError):
    stripe = None  # Fallback if stripe not installed


@login_required(login_url='accounts:login')
def create_payment(request, order_id):
    """
    Create a Stripe payment intent for the order.
    Redirects user to payment page.
    """
    order = get_object_or_404(Order, id=order_id, user=request.user)

    # Prevent duplicate payments
    if order.is_paid:
        messages.info(request, 'Этот заказ уже оплачен')
        return redirect('orders:order_detail', order_id=order.id)

    # Check if Stripe is properly configured
    if not stripe or 'demo_mode' in settings.STRIPE_SECRET_KEY.lower():
        messages.warning(request, '⚠️ Платежная система находится в режиме тестирования. Заказ отмечен как оплаченный без реального платежа.')

        # Auto-mark as paid for demo purposes
        try:
            payment = order.payment_transaction
        except PaymentTransaction.DoesNotExist:
            payment = PaymentTransaction.objects.create(
                order=order,
                amount=order.total_amount,
                currency=settings.PAYMENT_CURRENCY,
                description=f"Order {order.order_number} (DEMO MODE)",
                transaction_id=f"demo_{order.id}_{timezone.now().timestamp()}",
                status='succeeded'
            )

        payment.mark_as_succeeded(charge_id='demo_charge')
        messages.success(request, '✓ Заказ подтвержден в режиме демонстрации!')
        return redirect('orders:order_detail', order_id=order.id)

    # Check if payment transaction already exists
    try:
        payment = order.payment_transaction
    except PaymentTransaction.DoesNotExist:
        payment = PaymentTransaction.objects.create(
            order=order,
            amount=order.total_amount,
            currency=settings.PAYMENT_CURRENCY,
            description=f"Order {order.order_number}",
            transaction_id=f"intent_{order.id}_{timezone.now().timestamp()}"
        )

    try:
        # Create Stripe Payment Intent
        intent = stripe.PaymentIntent.create(
            amount=int(order.total_amount * 100),  # Convert to kopecks (cents)
            currency=settings.PAYMENT_CURRENCY.lower(),
            metadata={
                'order_id': order.id,
                'order_number': order.order_number,
            },
            description=f"Order {order.order_number}",
        )

        # Update payment transaction with Stripe intent ID
        payment.transaction_id = intent.id
        payment.status = 'processing'
        payment.save()

        context = {
            'order': order,
            'client_secret': intent.client_secret,
            'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
            'amount': order.total_amount,
        }
        return render(request, 'orders/payment.html', context)

    except Exception as e:
        payment.mark_as_failed(str(e))
        messages.error(request, f'Ошибка инициализации платежа: {e!s}')
        return redirect('orders:order_detail', order_id=order.id)


@login_required(login_url='accounts:login')
def payment_success(request, order_id):
    """
    Handle successful payment redirect from Stripe.
    User is redirected here after completing payment.
    """
    order = get_object_or_404(Order, id=order_id, user=request.user)

    try:
        payment = order.payment_transaction

        # If stripe is not available, check if already marked as succeeded
        if not stripe or 'demo_mode' in settings.STRIPE_SECRET_KEY.lower():
            if payment.status != 'succeeded':
                payment.mark_as_succeeded(charge_id='demo_mode')
            messages.success(request, '✓ Платеж успешно обработан (демо-режим)!')
            return redirect('orders:order_detail', order_id=order.id)

        # Verify payment status with Stripe
        intent = stripe.PaymentIntent.retrieve(payment.transaction_id)

        if intent.status == 'succeeded':
            # Mark payment as completed
            payment.mark_as_succeeded(charge_id=intent.latest_charge)
            messages.success(request, 'Платеж успешно принят! Ваш заказ подтвержден.')
            return redirect('orders:order_detail', order_id=order.id)
        else:
            messages.warning(request, f'Статус платежа: {intent.status}')
            return redirect('orders:order_detail', order_id=order.id)

    except PaymentTransaction.DoesNotExist:
        messages.error(request, 'Платежная информация не найдена')
        return redirect('orders:order_detail', order_id=order.id)
    except Exception as e:
        messages.error(request, f'Ошибка верификации платежа: {e!s}')
        return redirect('orders:order_detail', order_id=order.id)


@login_required(login_url='accounts:login')
def payment_cancel(request, order_id):
    """Handle payment cancellation or failure."""
    order = get_object_or_404(Order, id=order_id, user=request.user)

    try:
        payment = order.payment_transaction
        payment.mark_as_failed('User cancelled payment')
        messages.warning(request, 'Платеж отменен. Вы можете попробовать еще раз.')
    except PaymentTransaction.DoesNotExist:
        pass

    return redirect('orders:order_detail', order_id=order.id)


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """
    Handle Stripe webhook events (payment_intent.succeeded, payment_intent.payment_failed).
    Verifies webhook signature and updates payment status in database.
    """
    if not stripe or 'demo_mode' in settings.STRIPE_WEBHOOK_SECRET.lower():
        # In demo mode, just accept webhooks
        return JsonResponse({'status': 'success - demo mode'}, status=200)

    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

    # Defensive: missing signature header → reject immediately, до того как
    # construct_event кидает confusing ValueError. Без этого DDoS-вектор:
    # POST без Stripe-Signature заставит Django парсить весь request.body.
    if not sig_header:
        return JsonResponse({'error': 'missing_signature_header'}, status=400)

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        # Invalid payload (не-JSON или corrupted)
        return JsonResponse({'error': 'invalid_payload'}, status=400)
    except stripe.error.SignatureVerificationError:
        # Подпись не совпала — возможно атака, логируем
        import logging
        logging.getLogger('orders.security').warning(
            'Stripe webhook signature mismatch from %s',
            request.META.get('REMOTE_ADDR', 'unknown'),
        )
        return JsonResponse({'error': 'invalid_signature'}, status=400)
    except Exception as exc:
        # Любой другой непредвиденный сбой — логируем как ошибку (не security)
        import logging
        logging.getLogger('orders').exception(
            'Stripe webhook unexpected error: %s', exc,
        )
        return JsonResponse({'error': 'webhook_processing_error'}, status=500)

    # Handle payment_intent.succeeded
    if event['type'] == 'payment_intent.succeeded':
        intent = event['data']['object']
        order_id = intent['metadata'].get('order_id')

        if order_id:
            try:
                order = Order.objects.get(id=order_id)
                payment = PaymentTransaction.objects.get(order=order)

                if payment.status != 'succeeded':
                    payment.mark_as_succeeded(charge_id=intent['latest_charge'])

            except (Order.DoesNotExist, PaymentTransaction.DoesNotExist):
                pass

    # Handle payment_intent.payment_failed
    elif event['type'] == 'payment_intent.payment_failed':
        intent = event['data']['object']
        order_id = intent['metadata'].get('order_id')

        if order_id:
            try:
                order = Order.objects.get(id=order_id)
                payment = PaymentTransaction.objects.get(order=order)

                if payment.status != 'failed':
                    error_msg = intent.get('last_payment_error', {}).get('message', 'Unknown error')
                    payment.mark_as_failed(error_msg)

            except (Order.DoesNotExist, PaymentTransaction.DoesNotExist):
                pass

    return JsonResponse({'status': 'success'}, status=200)
