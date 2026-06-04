from django.urls import path

from . import payment_views, views

app_name = 'orders'

urlpatterns = [
    # Order management
    path('checkout/', views.checkout, name='checkout'),
    path('list/', views.order_list, name='order_list'),
    path('track/<str:token>/', views.guest_track, name='guest_track'),  # guest tracking
    path('<int:order_id>/', views.order_detail, name='order_detail'),
    path('<int:order_id>/cancel/', views.cancel_order, name='cancel_order'),
    path('<int:order_id>/repeat/', views.repeat_order, name='repeat_order'),
    # Payment processing
    path('<int:order_id>/payment/', payment_views.create_payment, name='create_payment'),
    path('<int:order_id>/payment/success/', payment_views.payment_success, name='payment_success'),
    path('<int:order_id>/payment/cancel/', payment_views.payment_cancel, name='payment_cancel'),
    # Webhook
    path('webhook/stripe/', payment_views.stripe_webhook, name='stripe_webhook'),
]
