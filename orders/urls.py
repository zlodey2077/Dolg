from django.urls import path

from Dolg_PR.url_utils import lazy_view

app_name = 'orders'

urlpatterns = [
    # Order management
    path('checkout/', lazy_view('orders.views.checkout'), name='checkout'),
    path('list/', lazy_view('orders.views.order_list'), name='order_list'),
    path('track/<str:token>/', lazy_view('orders.views.guest_track'), name='guest_track'),  # guest tracking
    path('<int:order_id>/', lazy_view('orders.views.order_detail'), name='order_detail'),
    path('<int:order_id>/cancel/', lazy_view('orders.views.cancel_order'), name='cancel_order'),
    path('<int:order_id>/repeat/', lazy_view('orders.views.repeat_order'), name='repeat_order'),
    # Payment processing
    path('<int:order_id>/payment/', lazy_view('orders.payment_views.create_payment'), name='create_payment'),
    path(
        '<int:order_id>/payment/success/',
        lazy_view('orders.payment_views.payment_success'),
        name='payment_success',
    ),
    path(
        '<int:order_id>/payment/cancel/',
        lazy_view('orders.payment_views.payment_cancel'),
        name='payment_cancel',
    ),
    # Webhook
    path(
        'webhook/stripe/',
        lazy_view('orders.payment_views.stripe_webhook', csrf_exempt=True),
        name='stripe_webhook',
    ),
]
