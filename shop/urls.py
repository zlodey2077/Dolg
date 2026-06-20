from django.urls import path

from Dolg_PR.url_utils import lazy_view

app_name = 'shop'

urlpatterns = [
    path('', lazy_view('shop.views.index'), name='index'),
    path('about/', lazy_view('shop.views.about'), name='about'),
    path('healthz/', lazy_view('shop.views.healthz'), name='healthz'),  # Docker liveness probe
    path('readyz/', lazy_view('shop.views.readyz'), name='readyz'),
    path('demo/', lazy_view('shop.views.demo_route'), name='demo_route'),
    path('search/', lazy_view('shop.views.global_search'), name='global_search'),
    path('category/<slug:slug>/', lazy_view('shop.views.category_products'), name='category'),
    path('product/<slug:slug>/', lazy_view('shop.views.product_detail'), name='product_detail'),
    path('add-to-cart/<slug:slug>/', lazy_view('shop.views.add_to_cart'), name='add_to_cart'),
    path('cart/', lazy_view('shop.views.cart'), name='cart'),
    path(
        'cart/clear-project-context/',
        lazy_view('shop.views.clear_project_cart_context'),
        name='clear_project_cart_context',
    ),
    path(
        'remove-from-cart/<int:item_id>/', lazy_view('shop.views.remove_from_cart'), name='remove_from_cart'
    ),
    path('update-cart/<int:item_id>/', lazy_view('shop.views.update_cart_item'), name='update_cart_item'),
    # BOM API (используется симулятором схем)
    path('component-search/', lazy_view('shop.views.api_component_search'), name='api_component_search'),
    path('bom/match/', lazy_view('shop.views.api_bom_match'), name='api_bom_match'),
    path('bom/export-xlsx/', lazy_view('shop.views.api_bom_export_xlsx'), name='api_bom_export_xlsx'),
    path('bom/add-all/', lazy_view('shop.views.api_bom_add_all'), name='api_bom_add_all'),
    # Сравнение товаров (по слугам, в сессии)
    path('compare/', lazy_view('shop.views.compare_view'), name='compare'),
    path('compare/toggle/<slug:slug>/', lazy_view('shop.views.compare_toggle'), name='compare_toggle'),
    path('compare/clear/', lazy_view('shop.views.compare_clear'), name='compare_clear'),
    # Автодополнение поиска (JSON).
    # ВАЖНО: URL без слов 'suggest'/'autocomplete' — на публичных доменах
    # (Cloudflare Tunnel) адблокеры режут такие пути как «ad suggestion».
    # На localhost проблема не воспроизводится — там adblock мягче.
    path('search/suggest/', lazy_view('shop.views.search_suggest'), name='search_suggest'),
    path('api/lookup/', lazy_view('shop.views.global_search_suggest'), name='global_search_suggest'),
    # PDF-документы на лету (гарантийный талон, сертификат качества)
    path(
        'product/<slug:slug>/warranty.pdf',
        lazy_view('shop.views.product_warranty_pdf'),
        name='product_warranty',
    ),
    path(
        'product/<slug:slug>/certificate.pdf',
        lazy_view('shop.views.product_certificate_pdf'),
        name='product_certificate',
    ),
]
