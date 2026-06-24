"""
URL configuration for Dolg_PR project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

from Dolg_APP.health import healthz, readyz

urlpatterns = [
    # Liveness/readiness-проба (анонимная, без чувствительных данных) — раньше всего.
    path('healthz', healthz, name='healthz'),
    path('readyz', readyz, name='readyz'),
    path('admin/', admin.site.urls),
    path('', include('shop.urls', namespace='shop')),  # Shop is main page
    path('accounts/', include('accounts.urls', namespace='accounts')),
    # django-allauth: /accounts/google/login/, /accounts/microsoft/login/, /accounts/github/login/
    # ВАЖНО: include('allauth.urls') не должен перекрыть наши accounts.urls —
    # наш include('accounts.urls') стоит ВЫШЕ, allauth добавляет только новые
    # маршруты (social/, /accounts/google/, ...), которых у нас нет.
    path('accounts/', include('allauth.urls')),
    path('orders/', include('orders.urls', namespace='orders')),
    path('knowledge/', include('knowledge.urls', namespace='knowledge')),
    path('', include('moderation.urls', namespace='moderation')),
    path(
        '', include('Dolg_APP.urls', namespace='hello')
    ),  # Инструменты (/simulation/, /cad/, /projects/) на корне
]

# Prometheus: /metrics/ только если пакет реально подгрузился (см. settings).
# Иначе URL не регистрируется — не блокирует роутинг. Вместо открытого
# include('django_prometheus.urls') отдаём метрики через staff/token-guard
# (см. Dolg_APP/metrics_guard) — иначе внутренние счётчики публичны.
if getattr(settings, '_HAS_PROMETHEUS', False):
    from Dolg_APP.metrics_guard import protected_metrics

    urlpatterns.append(path('metrics', protected_metrics, name='prometheus-django-metrics'))
    urlpatterns.append(path('metrics/', protected_metrics))

# Silk profiler: /silk/ доступен только staff (см. SILKY_PERMISSIONS).
if getattr(settings, '_HAS_SILK', False):
    urlpatterns.append(path('silk/', include('silk.urls', namespace='silk')))

# Serve media files in development. In local diploma/demo mode this can also be
# enabled with SERVE_MEDIA=1 while DEBUG=False; nginx still serves /media/
# directly in docker/production.
if settings.DEBUG:
    # ВАЖНО: daphne в INSTALLED_APPS заменяет команду runserver на ASGI-вариант,
    # который НЕ раздаёт static/media automatically в DEBUG (известная gotcha
    # django-channels). Поэтому подключаем оба раздачи явно через re_path+serve.
    # `static()` хелпер тоже регистрируем — он не мешает и даёт fallback при WSGI.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns

    urlpatterns += staticfiles_urlpatterns()
elif getattr(settings, 'SERVE_MEDIA', False):
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
