from django.urls import path

from . import views

app_name = 'shop'

urlpatterns = [
    path('', views.index, name='index'),
    path('about/', views.about, name='about'),
    path('healthz/', views.healthz, name='healthz'),  # Docker liveness probe
    path('readyz/', views.readyz, name='readyz'),
    path('demo/', views.demo_route, name='demo_route'),
    path('search/', views.global_search, name='global_search'),
    path('category/<slug:slug>/', views.category_products, name='category'),
    path('product/<slug:slug>/', views.product_detail, name='product_detail'),
    path('add-to-cart/<slug:slug>/', views.add_to_cart, name='add_to_cart'),
    path('cart/', views.cart, name='cart'),
    path('cart/clear-project-context/', views.clear_project_cart_context, name='clear_project_cart_context'),
    path('remove-from-cart/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('update-cart/<int:item_id>/', views.update_cart_item, name='update_cart_item'),

    # BOM API (используется симулятором схем)
    path('component-search/', views.api_component_search, name='api_component_search'),
    path('bom/match/', views.api_bom_match, name='api_bom_match'),
    path('bom/export-xlsx/', views.api_bom_export_xlsx, name='api_bom_export_xlsx'),
    path('bom/add-all/', views.api_bom_add_all, name='api_bom_add_all'),

    # Сравнение товаров (по слугам, в сессии)
    path('compare/', views.compare_view, name='compare'),
    path('compare/toggle/<slug:slug>/', views.compare_toggle, name='compare_toggle'),
    path('compare/clear/', views.compare_clear, name='compare_clear'),

    # Автодополнение поиска (JSON).
    # ВАЖНО: URL без слов 'suggest'/'autocomplete' — на публичных доменах
    # (Cloudflare Tunnel) адблокеры режут такие пути как «ad suggestion».
    # На localhost проблема не воспроизводится — там adblock мягче.
    path('search/suggest/', views.search_suggest, name='search_suggest'),
    path('api/lookup/', views.global_search_suggest, name='global_search_suggest'),

    # PDF-документы на лету (гарантийный талон, сертификат качества)
    path('product/<slug:slug>/warranty.pdf', views.product_warranty_pdf, name='product_warranty'),
    path('product/<slug:slug>/certificate.pdf', views.product_certificate_pdf, name='product_certificate'),
]
