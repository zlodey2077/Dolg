import json
import logging
import shutil
import subprocess
import tempfile
import time
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Max, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from shop.models import Product

from .models import (
    Announcement,
    EngineJob,
    ProjectEvent,
    ProjectMeasurement,
    ProjectReview,
    ProjectVersion,
    SchematicProject,
    SimulationRun,
)
from .quotas import (
    check_active_share_links,
    enforce_daily_quota,
    enforce_project_limit,
    get_limit,
    usage_summary,
)
from .schematic_validation import COMPONENT_TO_CATEGORY, validate_scheme_data
from .services.cad_import import import_preview
from .services.engine_ai import plan_engine_action
from .services.engine_jobs import retry_engine_job
from .services.entitlements import (
    feature_denied_response,
    feature_summary,
    get_effective_plan,
    has_feature,
)
from .services.learning_by_review import learning_suggestions_from_review
from .services.lithium_import import (
    LithiumImportError,
    detect_lithium_file,
    parse_lithium_project,
)
from .services.project_review import build_design_review, compare_measurement
from .services.review_i18n import (
    build_measurement_rows,
    build_metric_rows,
    localize_review_report,
    status_label_ru,
)
from .services.schematic_operations import apply_schematic_operations
from .services.server_engines import get_server_engine, recommend_server_engines, server_engine_payload
from .simulation_quota import quota_dict

logger = logging.getLogger(__name__)


def _simulation_analysis():
    """Import numerical Pro helpers only when a simulation endpoint needs them."""
    from .services import simulation_analysis

    return simulation_analysis


def _reportlab_pdf():
    """Import PDF stack only for endpoints that really render PDFs."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    return A4, pdfmetrics, TTFont, canvas


def _pdf_font_name(pdfmetrics, TTFont):
    for pdf_font_name, pdf_font_path in (
        ('TimesNewRoman', r'C:\Windows\Fonts\times.ttf'),
        ('DejaVuSans', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
    ):
        try:
            pdfmetrics.registerFont(TTFont(pdf_font_name, pdf_font_path))
        except Exception:
            continue
    registered_fonts = pdfmetrics.getRegisteredFontNames()
    return (
        'TimesNewRoman'
        if 'TimesNewRoman' in registered_fonts
        else ('DejaVuSans' if 'DejaVuSans' in registered_fonts else 'Helvetica')
    )


def _clean_protocol_pdf_text(text):
    text = str(text or '').strip()
    for marker in ('**', '`'):
        text = text.replace(marker, '')
    if text.startswith('_') and text.endswith('_') and len(text) > 1:
        text = text[1:-1]
    return text.replace('\t', '    ')


def _wrap_pdf_text(text, max_width, font_name, font_size, pdfmetrics):
    words = _clean_protocol_pdf_text(text).split(' ')
    lines = []
    current = ''
    for word in words:
        if not word:
            continue
        candidate = f'{current} {word}'.strip()
        if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        if pdfmetrics.stringWidth(word, font_name, font_size) <= max_width:
            current = word
            continue
        chunk = ''
        for char in word:
            candidate = f'{chunk}{char}'
            if chunk and pdfmetrics.stringWidth(candidate, font_name, font_size) > max_width:
                lines.append(chunk)
                chunk = char
            else:
                chunk = candidate
        current = chunk
    if current:
        lines.append(current)
    return lines or ['']


def _iter_protocol_pdf_blocks(markdown):
    for raw_line in str(markdown or '').splitlines():
        line = raw_line.strip()
        if not line:
            yield 'blank', ''
            continue
        if line.startswith('# '):
            yield 'h1', line[2:].strip()
            continue
        if line.startswith('## '):
            yield 'h2', line[3:].strip()
            continue
        if line.startswith('|') and line.endswith('|'):
            cells = [cell.strip() for cell in line.strip('|').split('|')]
            if cells and all(set(cell) <= {'-', ':'} for cell in cells):
                continue
            yield 'table', '  |  '.join(cells)
            continue
        if line.startswith('- '):
            yield 'list', f'- {line[2:].strip()}'
            continue
        yield 'body', line


def _render_protocol_pdf(markdown):
    A4, pdfmetrics, TTFont, canvas = _reportlab_pdf()
    buffer = BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    font_name = _pdf_font_name(pdfmetrics, TTFont)
    margin_x = 42
    bottom_y = 42
    y = height - 48
    page.setTitle('DOLG engineering protocol')

    def new_page():
        nonlocal y
        page.showPage()
        y = height - 48

    def draw_text(text, font_size=10, leading=14, extra_after=2, left_pad=0):
        nonlocal y
        max_width = width - margin_x * 2 - left_pad
        page.setFont(font_name, font_size)
        for wrapped in _wrap_pdf_text(text, max_width, font_name, font_size, pdfmetrics):
            if y < bottom_y:
                new_page()
                page.setFont(font_name, font_size)
            page.drawString(margin_x + left_pad, y, wrapped)
            y -= leading
        y -= extra_after

    for kind, text in _iter_protocol_pdf_blocks(markdown):
        if kind == 'blank':
            y -= 6
            if y < bottom_y:
                new_page()
        elif kind == 'h1':
            draw_text(text, font_size=15, leading=19, extra_after=8)
        elif kind == 'h2':
            y -= 3
            draw_text(text, font_size=12, leading=16, extra_after=5)
        elif kind == 'table':
            draw_text(text, font_size=8, leading=11, extra_after=1)
        elif kind == 'list':
            draw_text(text, font_size=9, leading=12, extra_after=1, left_pad=10)
        else:
            draw_text(text, font_size=10, leading=14, extra_after=2)

    page.save()
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Page views
# ---------------------------------------------------------------------------


def pcb_editor(request, project_id=None):
    """2026-06-02 Phase 2.1: 2D PCB editor (top/bottom view).

    URL вариант:
    - /pcb-editor/ — без параметра, юзер выбирает проект из dropdown'а
    - /pcb-editor/<id>/ — открывает конкретный проект сразу

    Минимальный MVP: canvas с top/bottom view, layer toggle, рендер компонентов
    из schema как footprints, рендер traces из connections. Manual routing,
    polygon pours — следующие итерации.
    """
    project = None
    scheme_data = None
    if project_id and request.user.is_authenticated:
        try:
            project = SchematicProject.objects.get(pk=project_id, user=request.user)
            scheme_data = project.scheme_json or {}
        except SchematicProject.DoesNotExist:
            pass

    user_projects = []
    if request.user.is_authenticated:
        user_projects = list(
            SchematicProject.objects.filter(user=request.user)
            .order_by('-updated_at')
            .values('id', 'name', 'updated_at')[:30]
        )

    return render(
        request,
        'tools/pcb_editor.html',
        {
            'project': project,
            'scheme_data_json': json.dumps(scheme_data) if scheme_data else 'null',
            'user_projects': user_projects,
            'page_title': 'PCB Editor — 2D',
            'page_description': 'Двумерный редактор печатной платы (top/bottom view, layer toggle).',
        },
    )


def news(request):
    """2026-06-02 фикс: реальный раздел Новостей вместо редиректа на Энциклопедию.

    Показывает все опубликованные Announcement, сначала закреплённые, затем по дате.
    Истёкшие (expires_at < now) скрываются. Pagination 20/страница.
    """
    from django.core.paginator import Paginator

    now = timezone.now()
    qs = (
        Announcement.objects.filter(is_published=True)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=now))
        .select_related('author')
    )
    paginator = Paginator(qs, 20)
    page_num = request.GET.get('page') or 1
    page = paginator.get_page(page_num)
    return render(
        request,
        'news/list.html',
        {
            'announcements': page,
            'paginator': paginator,
            'page_obj': page,
            'page_title': 'Новости DOLG',
        },
    )


@never_cache
@ensure_csrf_cookie
def simulation(request):
    # 2026-06-01 v13: @never_cache гарантирует что HTML страница не кэшируется.
    # Каждый F5 пользователь получает свежий HTML с актуальным ?v=cache-bump'ом,
    # подтягивая обновлённые JS/CSS. Без этого "подтяжки" не работают.
    context = {
        'user': request.user,
        'is_guest_demo': not request.user.is_authenticated,
        'entitlements': feature_summary(request.user),
        'server_engine_catalog_json': json.dumps(server_engine_payload(), ensure_ascii=False),
        'page_title': 'Симуляция электроники',
        'page_description': 'Инструмент для симуляции поведения электронных компонентов',
    }
    return render(request, 'tools/simulation.html', context)


def ar_viewer(request):
    """AR-предпросмотр 3D-модели платы через Google <model-viewer>.

    Source 3D-модели передаётся через query-параметр `model` (обычно blob-URL
    из текущей вкладки симулятора — см. exportGlb/downloadGlb в scheme-3d.js).
    Страница рендерится в новом окне, генерирует QR-код для AR-просмотра на
    телефоне (Android SceneViewer / iOS QuickLook через model-viewer's встроенную
    AR-кнопку) и работает без login: модель остаётся на стороне клиента.
    """
    return render(
        request,
        'tools/ar_viewer.html',
        {
            'model_url': request.GET.get('model', ''),
            'title': request.GET.get('title', 'DOLG 3D-модель'),
        },
    )


@ensure_csrf_cookie
def cad(request):
    """CAD-редактор. Открыт для guest в read-only режиме: можно
    смотреть, изменять локально, экспортировать — но save/load/projects
    отключены через is_guest флаг в шаблоне."""
    reb_products = (
        Product.objects.select_related('category')
        .filter(
            category__slug__in=[
                'resistors',
                'capacitors',
                'transistors',
                'ics',
                'diodes',
                'inductors',
                'connectors',
                'relays',
            ]
        )
        .order_by('category__slug', 'price', 'name')[:48]
    )
    catalog = []
    for product in reb_products:
        catalog.append(
            {
                'id': product.id,
                'slug': product.slug,
                'name': product.name,
                'part_number': product.part_number,
                'category': product.category.name,
                'category_slug': product.category.slug,
                'manufacturer': product.get_manufacturer_display(),
                'package_type': product.package_type,
                'price': float(product.price),
                'stock': product.stock,
                'lifecycle_status': product.lifecycle_status,
                'lifecycle_display': product.get_lifecycle_status_display(),
                'datasheet_url': product.datasheet_url,
                'parameters': product.parameters or {},
                'url': f'/product/{product.slug}/',
                'image_url': product.image.url if product.image else '',
            }
        )

    knowledge = []
    try:
        from knowledge.models import Article

        for article in (
            Article.objects.select_related('category')
            .filter(is_published=True)
            .order_by('category__order', 'order', 'title')[:36]
        ):
            knowledge.append(
                {
                    'title': article.title,
                    'summary': article.summary,
                    'category': article.category.name,
                    'topic': article.category.topic,
                    'slug': article.slug,
                    'url': f'/knowledge/article/{article.slug}/',
                    'related': article.related_components_note,
                }
            )
    except Exception:
        knowledge = []

    context = {
        'user': request.user,
        'page_title': '2D САПР',
        'page_description': 'Двумерный инструмент автоматизированного проектирования (САПР)',
        # Guest-флаг: шаблон отключает кнопки save/load/projects + показывает
        # CTA-баннер «Войдите чтобы сохранить». Изменения локальные не
        # блокируются — пользователь может рисовать, экспорт работает.
        'is_guest': not request.user.is_authenticated,
    }
    context['cad_catalog'] = catalog
    context['cad_knowledge'] = knowledge
    return render(request, 'tools/cad.html', context)


@ensure_csrf_cookie
@login_required(login_url='accounts:login')
def projects(request):
    context = {
        'user': request.user,
        'page_title': 'Мои проекты',
        'page_description': 'Управление вашими электронными проектами',
    }
    return render(request, 'tools/projects.html', context)


def terms(request):
    return render(request, 'tools/terms.html')


def privacy(request):
    return render(request, 'tools/privacy.html')


def cookies(request):
    """Cookie-policy — раскрывает категории cookies (necessary/analytics/marketing),
    цели сбора, сроки хранения, как изменить consent. Обязательна по GDPR/152-ФЗ
    при использовании cookie-banner с granular consent."""
    return render(request, 'tools/cookies.html')


def billing_plans(request):
    """Страница «Тарифы» — сравнение Free vs Pro + кнопки активации.
    Доступна всем (чтобы guest видел ценность регистрации + Pro).
    """
    from . import billing as billing_mod
    from .quotas import FREE_TIER, PRO_TIER

    user_sub = None
    if request.user.is_authenticated:
        user_sub = billing_mod.get_or_create_subscription(request.user)

    context = {
        'free_tier': FREE_TIER,
        'pro_tier': PRO_TIER,
        'subscription': user_sub,
        'trial_days': billing_mod.TRIAL_DAYS,
        'is_pro_active': user_sub.is_pro_active() if user_sub else False,
        'entitlements': feature_summary(request.user),
    }
    return render(request, 'billing/plans.html', context)


@login_required(login_url='accounts:login')
@require_POST
def billing_activate_trial(request):
    """Активация 14-дневного Pro-trial. Один раз на аккаунт."""
    from django.contrib import messages

    from . import billing as billing_mod

    success, msg = billing_mod.activate_trial(request.user)
    (messages.success if success else messages.warning)(request, msg)
    return redirect('hello:billing_plans')


@login_required(login_url='accounts:login')
@require_POST
def billing_activate_pro(request):
    """Покупка Pro: если Stripe live → redirect на Stripe Checkout,
    иначе fallback на mock-activate (как было)."""
    from django.contrib import messages

    from . import billing as billing_mod
    from . import stripe_billing

    try:
        months = max(1, min(12, int(request.POST.get('months', 1))))
    except TypeError, ValueError:
        months = 1

    if stripe_billing.is_stripe_live():
        ok, url_or_msg, _session_id = stripe_billing.create_checkout_session(request.user, request)
        if ok:
            return redirect(url_or_msg)
        # Stripe API дёрнулся → возвращаем pretty error
        messages.error(request, f'Не удалось создать оплату Stripe: {url_or_msg}')
        return redirect('hello:billing_plans')

    # Demo-mode: моментальная активация без реального платежа
    success, msg = billing_mod.activate_pro(request.user, months=months, provider='manual')
    (messages.success if success else messages.warning)(request, msg)
    return redirect('hello:billing_plans')


@login_required(login_url='accounts:login')
def billing_checkout_success(request):
    """Stripe вернул юзера сюда после успешной оплаты.

    Note: на этот момент webhook checkout.session.completed МОЖЕТ ещё не успеть
    долететь (latency). Поэтому если is_pro_active() == False — показываем
    «Платёж принят, активация через минуту» и юзер обновит страницу.
    """
    from django.contrib import messages

    from . import billing as billing_mod

    sub = billing_mod.get_or_create_subscription(request.user)

    session_id = request.GET.get('session_id', '')
    if sub.is_pro_active():
        messages.success(request, f'🎉 Pro-подписка активирована! Действует до {sub.period_end.date()}.')
    elif session_id:
        messages.info(
            request,
            '✓ Платёж принят. Активация обычно занимает несколько секунд — обновите страницу через минуту.',
        )
    else:
        messages.warning(request, 'Нет данных о checkout-сессии. Если оплата прошла — обновите страницу.')
    return redirect('hello:billing_plans')


@login_required(login_url='accounts:login')
@require_POST
def billing_cancel(request):
    """Отменить auto-renew. Если есть stripe_subscription_id — через Stripe API,
    иначе локальный mock-cancel."""
    from django.contrib import messages

    from . import billing as billing_mod
    from . import stripe_billing

    sub = billing_mod.get_or_create_subscription(request.user)
    if sub.stripe_subscription_id and stripe_billing.is_stripe_live():
        success, msg = stripe_billing.cancel_at_period_end(sub)
    else:
        success, msg = billing_mod.cancel(request.user)
    (messages.success if success else messages.warning)(request, msg)
    return redirect('hello:billing_plans')


@csrf_exempt
@require_POST
def billing_stripe_webhook(request):
    """Stripe POSTs subscription events here.

    Эндпойнт обрабатывает события Pro-подписки. Для одноразовых Order
    платежей есть отдельный orders.payment_views.stripe_webhook.
    Stripe-URL в Dashboard:
      https://<domain>/billing/stripe-webhook/
      Events: checkout.session.completed, customer.subscription.updated,
              customer.subscription.deleted, invoice.payment_failed
    """
    from . import stripe_billing

    if not stripe_billing.is_stripe_live():
        # В demo-mode принимаем всё как 200, чтобы локальное тестирование не падало.
        return JsonResponse({'status': 'demo_mode'}, status=200)

    import stripe

    payload = request.body
    sig = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig,
            settings.STRIPE_WEBHOOK_SECRET,
        )
    except ValueError:
        return JsonResponse({'error': 'invalid_payload'}, status=400)
    except stripe.error.SignatureVerificationError:
        return JsonResponse({'error': 'invalid_signature'}, status=400)

    et = event.get('type', '')
    data = (event.get('data') or {}).get('object') or {}

    handlers = {
        'checkout.session.completed': stripe_billing.handle_checkout_completed,
        'customer.subscription.updated': stripe_billing.handle_subscription_updated,
        'customer.subscription.deleted': stripe_billing.handle_subscription_deleted,
        'invoice.payment_failed': stripe_billing.handle_invoice_payment_failed,
    }
    handler = handlers.get(et)
    if handler is None:
        # Неизвестное событие — отвечаем 200 чтобы Stripe не retry'ил бесконечно
        return JsonResponse({'status': 'ignored', 'type': et}, status=200)

    ok = handler(data)
    return JsonResponse({'status': 'ok' if ok else 'handled', 'type': et}, status=200)


# ============================================================
# AI Pipeline endpoints
# ============================================================
# 4 endpoint'а соответствуют 4 методам DolgAIPipeline.
# Free доступ:  find_analogs, detect_anomalies (2 базовых)
# Pro доступ:   + explain_scheme, recommend_next_component (4 всего)
# Все endpoint'ы — POST с JSON-body.
# Декоратор @enforce_daily_quota('ai_requests') считает в общую AI-квоту.

AI_ACTION_FEATURES = {
    'find_analogs': 'ai_find_analogs',
    'detect_anomalies': 'ai_detect_anomalies',
    'explain_scheme': 'ai_explain_scheme',
    'recommend_next_component': 'ai_recommend_next',
}


def _ai_check_access(user, action: str) -> tuple[bool, str]:
    """Backwards-compatible bool helper for tests and older callers."""
    feature = AI_ACTION_FEATURES.get(action)
    if not feature:
        return True, ''
    if has_feature(user, feature):
        return True, ''
    return False, f'Действие «{action}» требует тариф Pro или Enterprise.'


@login_required(login_url='accounts:login')
@require_POST
@enforce_daily_quota('ai_requests')
def api_ai_find_analogs(request):
    """POST {product_id: int, top_k: int, query?: str} → list[{product, score, why}]

    Phase 2 (2026-05-19): если fastembed+faiss установлены и индекс построен,
    используем семантический поиск (ml.semantic_search). Иначе — rule-based
    fallback через pipeline.find_analogs.

    query опционален: если задан, используется как поисковая строка вместо
    `Product.name + part_number` (по умолчанию).
    """
    from shop.models import Product

    from .ml import pipeline
    from .ml.semantic_search import is_semantic_available, semantic_top_k

    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError, ValueError:
        return _json_error('Invalid JSON')
    pid = data.get('product_id')
    query = (data.get('query') or '').strip()
    if not pid and not query:
        return _json_error('product_id or query is required')
    top_k = max(1, min(20, int(data.get('top_k', 5))))

    source_product = None
    if pid:
        try:
            source_product = Product.objects.get(pk=pid)
        except Product.DoesNotExist:
            return _json_error('Product not found', status=404)

    # Phase 2: семантика, если доступно
    backend = 'rule-based'
    if is_semantic_available():
        if not query and source_product:
            query = f'{source_product.name} {source_product.part_number or ""}'.strip()
        if query:
            sem_results = semantic_top_k(query, k=top_k + 1)
            # Исключаем сам product из аналогов, если pid задан
            if pid:
                sem_results = [(p, s) for p, s in sem_results if p != pid]
            sem_results = sem_results[:top_k]
            if sem_results:
                backend = 'semantic'
                products_map = {p.id: p for p in Product.objects.filter(id__in=[r[0] for r in sem_results])}
                results = []
                for p_id, score in sem_results:
                    p = products_map.get(p_id)
                    if p:
                        results.append(
                            {
                                'product': p,
                                'score': round(score, 4),
                                'why': f'Semantic similarity {score:.3f}',
                            }
                        )
                return _serialize_analogs(results, backend=backend)

    # Fallback: rule-based feature-vectors
    if source_product is None:
        return _json_error(
            'Semantic поиск недоступен (нет индекса), нужен product_id для rule-based fallback'
        )
    results = pipeline.find_analogs(source_product, top_k=top_k)
    return _serialize_analogs(results, backend=backend)


def _serialize_analogs(results, *, backend: str):
    return JsonResponse(
        {
            'ok': True,
            'action': 'find_analogs',
            'backend': backend,
            'results': [
                {
                    'product_id': r['product'].id,
                    'slug': r['product'].slug,
                    'name': r['product'].name,
                    'part_number': r['product'].part_number,
                    'price': float(r['product'].price),
                    'url': f'/product/{r["product"].slug}/',
                    'score': r['score'],
                    'why': r['why'],
                }
                for r in results
            ],
        }
    )


@login_required(login_url='accounts:login')
@require_POST
@enforce_daily_quota('ai_requests')
def api_ai_detect_anomalies(request):
    """POST {scheme_data: {...}} → list[anomaly]"""
    from .ml import pipeline

    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError, ValueError:
        return _json_error('Invalid JSON')
    scheme_data = data.get('scheme_data') or {}
    anomalies = pipeline.detect_anomalies(scheme_data)
    return JsonResponse(
        {
            'ok': True,
            'action': 'detect_anomalies',
            'anomalies': anomalies,
            'total': len(anomalies),
        }
    )


@login_required(login_url='accounts:login')
@require_POST
@enforce_daily_quota('ai_requests')
def api_ai_explain_scheme(request):
    """POST {scheme_data: {...}} → {title, summary, topology, ...}
    Pro-only."""
    denied = feature_denied_response(request.user, 'ai_explain_scheme')
    if denied:
        return denied
    from .ml import pipeline

    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError, ValueError:
        return _json_error('Invalid JSON')
    scheme_data = data.get('scheme_data') or {}
    result = pipeline.explain_scheme(scheme_data)
    return JsonResponse({'ok': True, 'action': 'explain_scheme', **result})


@login_required(login_url='accounts:login')
@require_POST
@enforce_daily_quota('ai_requests')
def api_ai_recommend_next(request):
    """POST {scheme_data: {...}} → list[recommendation]
    Pro-only."""
    denied = feature_denied_response(request.user, 'ai_recommend_next')
    if denied:
        return denied
    from .ml import pipeline

    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError, ValueError:
        return _json_error('Invalid JSON')
    scheme_data = data.get('scheme_data') or {}
    recs = pipeline.recommend_next_component(scheme_data)
    return JsonResponse(
        {
            'ok': True,
            'action': 'recommend_next_component',
            'recommendations': recs,
        }
    )


def api_ai_pipeline_info(request):
    """GET → {backend, model_version, capabilities}. Без auth, открыт всем
    (метаданные о pipeline, без секретов)."""
    from .ml import pipeline

    return JsonResponse({'ok': True, **pipeline.info()})


# ============================================================
# Comments API
# ============================================================
# 3 endpoint'а: list / create / delete.
# Free может оставлять plain-text до 500 симв.
# Pro может оставлять Markdown до 5000 симв с code-highlight.
# is_rich определяется автоматически по tier юзера на момент создания.

FREE_COMMENT_MAX_LEN = 500
PRO_COMMENT_MAX_LEN = 5000


def _comment_to_dict(c, request_user=None):
    from moderation.services import display_body, is_content_visible_to

    body = display_body(c, request_user)
    is_visible = is_content_visible_to(c, request_user)
    return {
        'id': c.id,
        'user': {
            'username': c.user.username,
            'avatar_url': (
                c.user.profile.avatar.url if hasattr(c.user, 'profile') and c.user.profile.avatar else ''
            ),
            'is_pro': c.is_rich,  # rich-comment ≡ автор был Pro в момент написания
        },
        'body': body,
        'body_html': c.render_html() if is_visible else body,
        'is_rich': c.is_rich,
        'moderation_status': c.moderation_status,
        'created_at': c.created_at.isoformat(),
        'edited_at': c.edited_at.isoformat() if c.edited_at else None,
        'parent_id': c.parent_id,
    }


@require_GET
def api_comments_list(request):
    """GET ?project=N или ?article=N → list[comment]"""
    from moderation.services import visible_queryset

    from .models import Comment

    project_id = request.GET.get('project')
    article_id = request.GET.get('article')
    qs = Comment.objects.select_related('user', 'user__profile').order_by('created_at')
    if project_id:
        _project_for_read(request.user, project_id)
        qs = qs.filter(project_id=project_id)
    elif article_id:
        qs = qs.filter(article_id=article_id)
    else:
        return _json_error('project or article query param required')
    qs = visible_queryset(qs, request.user)
    return JsonResponse({'ok': True, 'comments': [_comment_to_dict(c, request.user) for c in qs[:200]]})


@login_required(login_url='accounts:login')
@require_POST
def api_comments_create(request):
    """POST {body, project|article, parent_id?} → comment"""
    from moderation.services import user_is_restricted

    from .models import Comment
    from .quotas import get_user_tier

    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError, ValueError:
        return _json_error('Invalid JSON')

    if user_is_restricted(request.user, 'write'):
        return _json_error('Ваш аккаунт временно ограничен модератором.', status=403)

    body = (data.get('body') or '').strip()
    if not body:
        return _json_error('body is required')

    tier = get_user_tier(request.user)
    is_pro = tier in ('pro', 'unlimited')
    max_len = PRO_COMMENT_MAX_LEN if is_pro else FREE_COMMENT_MAX_LEN
    if len(body) > max_len:
        return JsonResponse(
            {
                'ok': False,
                'error': 'too_long',
                'message': f'Превышен лимит {max_len} символов для tier «{tier}». У вас {len(body)}.',
            },
            status=400,
        )

    project_id = data.get('project')
    article_id = data.get('article')
    parent_id = data.get('parent_id')
    if not project_id and not article_id:
        return _json_error('project or article required')

    kwargs = {
        'user': request.user,
        'body': body,
        'is_rich': is_pro,
        'parent_id': parent_id,
    }
    if project_id:
        # Проверим, что проект существует и видим юзеру (свой / shared / public)
        project = _project_for_read(request.user, project_id)
        if project.organization_id and user_is_restricted(
            request.user, 'write', organization=project.organization
        ):
            return _json_error('Ваш аккаунт временно ограничен модератором в этой команде.', status=403)
        kwargs['project'] = project
    else:
        from knowledge.models import Article

        try:
            Article.objects.get(pk=article_id)
        except Article.DoesNotExist:
            return _json_error('Article not found', status=404)
        kwargs['article_id'] = article_id

    comment = Comment.objects.create(**kwargs)
    if project_id:
        _log_project_event(
            comment.project,
            request.user,
            'comment_added',
            {
                'comment_id': comment.id,
                'parent_id': comment.parent_id,
                'is_rich': comment.is_rich,
            },
        )
    return JsonResponse({'ok': True, 'comment': _comment_to_dict(comment, request.user)})


@login_required(login_url='accounts:login')
@require_POST
def api_comments_delete(request, pk):
    """POST → soft-delete (физ.удаление) собственного комментария.
    Только автор или staff."""
    from .models import Comment

    comment = get_object_or_404(Comment, pk=pk)
    if comment.user_id != request.user.id and not request.user.is_staff:
        return _json_error('forbidden', status=403)
    if request.user.is_superuser and request.POST.get('purge') == '1':
        comment.delete()
        return JsonResponse({'ok': True, 'purged': True})
    comment.moderation_status = 'removed'
    comment.moderation_reason = (
        'Удалено пользователем' if comment.user_id == request.user.id else 'Удалено модератором'
    )
    comment.moderated_by = request.user
    comment.moderated_at = timezone.now()
    comment.save(update_fields=['moderation_status', 'moderation_reason', 'moderated_by', 'moderated_at'])
    return JsonResponse({'ok': True})


@login_required(login_url='accounts:login')
@require_GET
def api_usage_today(request):
    """Возвращает live-сводку лимитов для текущего юзера. UI-баннеры
    опрашивают этот endpoint раз в минуту, чтобы показывать актуальные
    «15/20 today» без перезагрузки страницы."""
    return JsonResponse({'ok': True, **usage_summary(request.user)})


def learn(request):
    """Старый URL оставлен как совместимый вход в новый практикум."""
    return redirect('knowledge:learning_index')


@login_required(login_url='accounts:login')
def pcb_view(request, project_id):
    """Просмотр PCB-разводки проекта. Авто-расстановка из scheme_data,
    отрисовка в SVG (для печати/сохранения), кнопка скачать Gerber+drill."""
    from . import pcb_layout

    project = _project_for_read(request.user, project_id)
    layout = pcb_layout.compute_pcb_layout(project.scheme_data)
    drc = pcb_layout.analyze_pcb_drc(layout, project.scheme_data)
    context = {
        'project': project,
        'layout': layout,
        'drc': drc,
        'page_title': f'PCB: {project.name}',
    }
    return render(request, 'tools/pcb.html', context)


@login_required(login_url='accounts:login')
def pcb_gerber_download(request, project_id):
    """Возвращает ZIP с двумя Gerber-файлами: top-copper (.GTL) + drill (.DRL).
    Минимальный набор для PCB-производства; реальная плата требует ещё
    silkscreen, mask, paste и через-platы — это вне MVP."""
    import zipfile
    from io import BytesIO

    from . import pcb_layout

    project = _project_for_read(request.user, project_id)
    layout = pcb_layout.compute_pcb_layout(project.scheme_data)

    # Pro-юзер: добавим его custom logo в ZIP + branded README.
    pro_logo_path = None
    is_pro_branding = False
    try:
        from .quotas import get_user_tier

        if get_user_tier(request.user) in ('pro', 'unlimited'):
            if hasattr(request.user, 'profile') and request.user.profile.pro_logo:
                pro_logo_path = request.user.profile.pro_logo.path
                is_pro_branding = True
    except Exception:
        pass

    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f'{project.id}_top_copper.GTL', pcb_layout.to_gerber_top_copper(layout))
        zf.writestr(f'{project.id}_drill.DRL', pcb_layout.to_gerber_drill(layout))

        # README: branded для Pro, generic для Free
        if is_pro_branding:
            readme = (
                f'PCB Export — {request.user.username}\n'
                f'Project: {project.name}\n\n'
                f'Файлы:\n'
                f'  - {project.id}_top_copper.GTL — верхний слой меди (RS-274X)\n'
                f'  - {project.id}_drill.DRL — отверстия (Excellon NC drill)\n'
                f'  - logo.{request.user.profile.pro_logo.name.rsplit(".", 1)[-1]} — ваш custom logo\n\n'
                f'Перед отправкой на производство откройте в gerbview/KiCad и проведите DRC.\n'
            )
        else:
            readme = (
                'DOLG PCB export (MVP)\n\n'
                'Файлы:\n'
                f'  - {project.id}_top_copper.GTL — верхний слой меди (RS-274X)\n'
                f'  - {project.id}_drill.DRL — отверстия (Excellon NC drill)\n\n'
                'Это MVP-экспорт: нет silkscreen, mask, через-плат. Перед\n'
                'отправкой на производство откройте в gerbview/KiCad/Altium\n'
                'и проведите DRC.\n\n'
                '💎 Pro-tier позволяет добавить ваш custom logo в ZIP — /billing/\n'
            )
        zf.writestr('README.txt', readme)

        # Включаем logo-файл если Pro
        if pro_logo_path:
            try:
                with open(pro_logo_path, 'rb') as f:
                    ext = pro_logo_path.rsplit('.', 1)[-1]
                    zf.writestr(f'logo.{ext}', f.read())
            except Exception:
                pass  # не валим экспорт если файл недоступен

    response = HttpResponse(buf.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="dolg_pcb_{project.id}.zip"'
    return response


@require_POST
def api_pcb_autoroute(request, project_id):
    """Block C1: A* autorouter поверх существующего pcb_layout.

    POST → пересчитывает traces через A* (grid 0.5мм + штраф за поворот,
    обход компонентов). Возвращает обновлённый layout + stats.
    """
    from . import pcb_layout
    from .services.autorouter import autoroute_layout

    project = _project_for_read(request.user, project_id)
    base_layout = pcb_layout.compute_pcb_layout(project.scheme_data)
    connections = (project.scheme_data or {}).get('connections', []) or []
    new_layout = autoroute_layout(base_layout, connections)
    drc = pcb_layout.analyze_pcb_drc(new_layout, project.scheme_data)
    return JsonResponse(
        {
            'ok': True,
            'stats': new_layout.get('autoroute_stats', {}),
            'traces': new_layout.get('traces', []),
            'drc': drc,
            'pcb_w_mm': new_layout.get('pcb_w_mm'),
            'pcb_h_mm': new_layout.get('pcb_h_mm'),
        }
    )


def shared_scheme(request, token):
    """Read-only просмотр схемы по публичному токену /s/<token>/.

    Не требует логина и квот. Открывается с любого устройства по ссылке.
    Если токен неверен или владелец отключил шаринг — 404.
    """
    share_alphabet = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_'
    if not token or len(token) < 8 or len(token) > 22 or any(ch not in share_alphabet for ch in token):
        raise Http404('Invalid share token')

    project = get_object_or_404(
        SchematicProject.objects.select_related('user'),
        share_token=token,
    )
    context = {
        'user': request.user,
        'is_guest_demo': not request.user.is_authenticated,
        'is_shared_view': True,
        'entitlements': feature_summary(request.user),
        'shared_project': project,
        'server_engine_catalog_json': json.dumps(server_engine_payload(), ensure_ascii=False),
        'page_title': f'{project.name} — общий просмотр',
        'page_description': f'Read-only схема пользователя {project.user.username}',
    }
    return render(request, 'tools/simulation.html', context)


@login_required(login_url='accounts:login')
@require_POST
def api_project_share_toggle(request, pk):
    """Включает / выключает sharing проекта. Возвращает токен (или пустую
    строку если выключен). Только владелец может управлять шарингом."""
    import secrets

    project = _project_for_write(request.user, pk)
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError, ValueError:
        data = {}
    enable = bool(data.get('enable', True))
    if enable and not project.share_token:
        # Лимит активных share-link'ов tier'а (Free: 5)
        allowed, reason = check_active_share_links(request.user)
        if not allowed:
            return JsonResponse(
                {
                    'ok': False,
                    'error': 'quota_exceeded',
                    'message': reason,
                    'limit': get_limit(request.user, 'max_active_share_links'),
                },
                status=400,
            )
        # Генерация: 16 байт URL-safe = 22 символа base64 без padding.
        project.share_token = secrets.token_urlsafe(16)
    elif not enable:
        project.share_token = ''
    project.save(update_fields=['share_token', 'updated_at'])
    return JsonResponse(
        {
            'ok': True,
            'token': project.share_token,
            'url': request.build_absolute_uri('/s/' + project.share_token + '/')
            if project.share_token
            else '',
        }
    )


# ---------------------------------------------------------------------------
# JSON API helpers
# ---------------------------------------------------------------------------


def _project_to_dict(p):
    return {
        'id': p.id,
        'name': p.name,
        'description': p.description,
        'category': p.category,
        'status': p.status,
        'difficulty': p.difficulty,
        'is_demo': p.is_demo,
        'owner': p.user.username,
        'created': p.created_at.isoformat(),
        'modified': p.updated_at.isoformat(),
        'has_scheme': bool(p.scheme_data),
        'versions_count': p.versions.count() if p.pk else 0,
        'runs_count': p.simulation_runs.count() if p.pk else 0,
        'measurements_count': p.measurements.count() if p.pk else 0,
        'reviews_count': p.reviews.count() if p.pk else 0,
        'events_count': p.events.count() if p.pk else 0,
        # Sharing — пустая строка если не share-нут. Для UI: рисуем бейдж 🔗
        # и даём ссылку на /s/<token>/.
        'is_shared': bool(p.share_token),
        'share_token': p.share_token or '',
        # Enterprise: team-context, visibility, approval-state
        'organization': p.organization.slug if p.organization_id else None,
        'organization_name': p.organization.name if p.organization_id else None,
        'visibility': p.visibility,
        'approval_state': p.approval_state,
    }


def _json_error(msg, status=400):
    return JsonResponse({'ok': False, 'error': msg}, status=status)


def _find_dwg_converter():
    """Return (kind, executable) for optional DWG->DXF conversion.

    DWG is a proprietary binary format, so DOLG delegates actual decoding to an
    installed converter. ODA File Converter is the preferred path; LibreDWG's
    dwg2dxf is also supported when present in PATH.
    """
    for name in (
        'ODAFileConverter',
        'ODAFileConverter.exe',
        'TeighaFileConverter',
        'TeighaFileConverter.exe',
    ):
        exe = shutil.which(name)
        if exe:
            return 'oda', exe
    for name in ('dwg2dxf', 'dwg2dxf.exe'):
        exe = shutil.which(name)
        if exe:
            return 'libredwg', exe
    return None, None


def _convert_dwg_to_dxf_bytes(uploaded_file):
    kind, exe = _find_dwg_converter()
    if not exe:
        raise RuntimeError(
            'DWG — бинарный формат AutoCAD. Для автоматического импорта установите '
            'ODA File Converter или LibreDWG/dwg2dxf на сервер, либо сохраните файл как DXF.'
        )

    with tempfile.TemporaryDirectory(prefix='dolg_dwg_') as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / 'input.dwg'
        with src.open('wb') as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)

        out_dir = tmp_path / 'out'
        out_dir.mkdir(exist_ok=True)

        if kind == 'oda':
            cmd = [exe, str(tmp_path), str(out_dir), 'ACAD2018', 'DXF', '0', '1']
        else:
            dst = out_dir / 'input.dxf'
            cmd = [exe, str(src), '-o', str(dst)]

        proc = subprocess.run(cmd, cwd=str(tmp_path), capture_output=True, text=True, timeout=45)
        if proc.returncode != 0:
            details = (proc.stderr or proc.stdout or '').strip()[:1000]
            raise RuntimeError(f'DWG-конвертер вернул ошибку: {details or proc.returncode}')

        candidates = list(out_dir.rglob('*.dxf')) + list(tmp_path.rglob('*.dxf'))
        if not candidates:
            raise RuntimeError('DWG-конвертер завершился, но DXF-файл не найден')
        return candidates[0].read_bytes()


@require_POST
@login_required(login_url='accounts:login')
def api_cad_convert_dwg(request):
    uploaded = request.FILES.get('file')
    if not uploaded:
        return _json_error('Файл не передан')
    if not uploaded.name.lower().endswith('.dwg'):
        return _json_error('Ожидается файл .dwg')
    if uploaded.size > 25 * 1024 * 1024:
        return _json_error('DWG слишком большой для демо-импорта (лимит 25 МБ)', status=413)
    try:
        dxf_bytes = _convert_dwg_to_dxf_bytes(uploaded)
        dxf = dxf_bytes.decode('utf-8', errors='replace')
    except RuntimeError as exc:
        return _json_error(str(exc), status=501)
    return JsonResponse({'ok': True, 'format': 'dxf', 'dxf': dxf})


def _project_for_read(user, pk):
    """Read-access: владелец / demo / public / team-member.

    Расширено для Enterprise:
    - private + не свой → 404
    - team → доступен любому active-member организации
    - public → доступен всем auth-юзерам
    """
    qs = SchematicProject.objects.select_related('user', 'organization')
    # Базовая выборка по pk + видимость
    candidate = get_object_or_404(qs, pk=pk)

    # 1) Свой / demo / public
    if candidate.is_demo or candidate.user_id == user.id or candidate.visibility == 'public':
        return candidate
    # 2) team-проект и user — member организации
    if candidate.visibility == 'team' and candidate.organization_id:
        if candidate.organization.has_member(user):
            return candidate
    # Иначе нет доступа
    from django.http import Http404

    raise Http404('No read access')


def _project_for_write(user, pk):
    """Write-access: владелец ИЛИ team-member с ролью engineer+ в org проекта.

    Demo-проекты read-only для всех кроме staff.
    """
    qs = SchematicProject.objects.select_related('user', 'organization')
    candidate = get_object_or_404(qs, pk=pk, is_demo=False)
    # 1) Свой
    if candidate.user_id == user.id:
        return candidate
    # 2) team-проект + user имеет project.edit_team в org
    if candidate.organization_id:
        from .org_permissions import user_can

        if user_can(user, candidate.organization, 'project.edit_team'):
            return candidate
    from django.http import Http404

    raise Http404('No write access')


def _validate_scheme_data(scheme_data):
    return validate_scheme_data(scheme_data)


def _next_project_version(project):
    last = project.versions.aggregate(value=Max('version_number'))['value'] or 0
    return last + 1


def _simulation_summary(result):
    if not isinstance(result, dict):
        return {}
    points = result.get('points')
    return {
        'type': result.get('type', 'unknown'),
        'points_count': len(points) if isinstance(points, list) else 0,
        'node_count': len(result.get('nodeVoltages', {}) or {}),
        'has_warnings': bool(result.get('warnings')),
    }


def _read_json_payload(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body)
    except json.JSONDecodeError, ValueError:
        return {}


def _require_pro_feature(user, feature_key, feature_label=None):
    return feature_denied_response(user, feature_key)


def _measurement_to_dict(item):
    return {
        'id': item.id,
        'metric': item.metric,
        'label': item.label,
        'value': item.value,
        'unit': item.unit,
        'expected_value': item.expected_value,
        'tolerance_abs': item.tolerance_abs,
        'tolerance_percent': item.tolerance_percent,
        'status': item.status,
        'source': item.source,
        'result': item.result,
        'created': item.created_at.isoformat(),
    }


def _review_to_dict(review):
    payload = {
        'id': review.id,
        'project_id': review.project_id,
        'score': review.score,
        'status': review.status,
        'status_label': status_label_ru(review.status),
        'summary': review.summary,
        'errors': review.errors,
        'warnings': review.warnings,
        'recommendations': review.recommendations,
        'metrics': review.metrics,
        'sections': review.sections,
        'faults': review.faults,
        'import_summary': review.import_summary,
        'learning_suggestions': learning_suggestions_from_review(review),
        'created': review.created_at.isoformat(),
        'url': reverse('hello:project_review_page', args=[review.id]),
        'pdf_url': reverse('hello:project_review_pdf', args=[review.id]),
    }
    localized = localize_review_report(payload)
    sections = localized.get('sections') or {}
    expert_section = sections.get('expert_system') if isinstance(sections, dict) else {}
    if isinstance(expert_section, dict) and not localized.get('expert_findings'):
        localized['expert_findings'] = expert_section.get('findings') or []
    localized['metric_rows'] = build_metric_rows(localized.get('metrics') or {})
    localized['measurement_rows'] = build_measurement_rows(sections)
    try:
        from .services.review_visualization import build_review_3d_payload

        localized['review_3d_payload'] = build_review_3d_payload(localized)
    except Exception:
        localized['review_3d_payload'] = {'enabled': False, 'columns': [], 'risk_points': [], 'legend': []}
    # Topology thumbnail: schemdraw SVG для типовых топологий (делитель/RC/LED).
    # Дешевле полноценного PCB-рендера и сразу делает HTML-отчёт «иллюстрированным».
    # PDF-вставка пока не делается (нужен SVG→PNG rasterize, M-задача в backlog).
    try:
        from knowledge.services.circuit_svg import thumbnail_for_topology

        connectivity = sections.get('connectivity') if isinstance(sections, dict) else None
        topology = (connectivity or {}).get('topology') if isinstance(connectivity, dict) else None
        localized['topology_thumbnail_svg'] = thumbnail_for_topology(topology) if topology else None
    except Exception:
        localized['topology_thumbnail_svg'] = None
    return localized


def _event_to_dict(event):
    return {
        'id': event.id,
        'project_id': event.project_id,
        'event_type': event.event_type,
        'event_label': event.get_event_type_display(),
        'payload': event.payload or {},
        'user': event.user.username if event.user_id else '',
        'created': event.created_at.isoformat(),
    }


def _broadcast_project_event(project_id, event_payload):
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is not None:
            async_to_sync(layer.group_send)(
                f'project-{project_id}',
                {'type': 'project.event', 'event': event_payload},
            )
    except Exception:
        # WebSocket push is a UI accelerator, not the source of truth.
        pass


def _log_project_event(project, user, event_type, payload=None, *, broadcast=True):
    event = ProjectEvent.log(project=project, user=user, event_type=event_type, payload=payload or {})
    if event and broadcast:
        _broadcast_project_event(project.id, _event_to_dict(event))
    return event


def _create_project_review(project, user, import_summary=None):
    report = build_design_review(
        project,
        simulation_runs=list(project.simulation_runs.all()[:10]),
        measurements=list(project.measurements.all()[:50]),
        import_summary=import_summary,
    )
    review = ProjectReview.objects.create(
        project=project,
        user=user,
        score=report['score'],
        status=report['status'],
        summary=report['summary'],
        errors=report['errors'],
        warnings=report['warnings'],
        recommendations=report['recommendations'],
        metrics=report['metrics'],
        sections=report['sections'],
        faults=report['faults'],
        scheme_data=project.scheme_data,
        import_summary=import_summary or {},
    )
    _log_project_event(
        project,
        user,
        'review_created',
        {
            'review_id': review.id,
            'score': review.score,
            'status': review.status,
            'errors': len(review.errors or []),
            'warnings': len(review.warnings or []),
            'url': reverse('hello:project_review_page', args=[review.id]),
        },
    )
    return review


def _review_for_read(user, review_id):
    review = get_object_or_404(
        ProjectReview.objects.select_related('project', 'project__user', 'project__organization', 'user'),
        pk=review_id,
    )
    _project_for_read(user, review.project_id)
    return review


# ---------------------------------------------------------------------------
# API endpoints — все требуют авторизации, все отдают JSON
# ---------------------------------------------------------------------------


@login_required(login_url='accounts:login')
@require_GET
def api_projects_list(request):
    """Возвращает: личные + demo + team-проекты org куда юзер входит.

    Опциональный фильтр ?org=<slug> — только проекты конкретной org.
    """
    org_slug = (request.GET.get('org') or '').strip()
    if org_slug == 'personal':
        # Только личные (не в org)
        qs = SchematicProject.objects.filter(user=request.user, organization__isnull=True)
    elif org_slug:
        # Конкретная org — проверим membership
        from .models import Organization

        try:
            org = Organization.objects.get(slug=org_slug)
        except Organization.DoesNotExist:
            return _json_error('Organization not found', status=404)
        if not org.has_member(request.user):
            return _json_error('Not a member', status=403)
        qs = SchematicProject.objects.filter(organization=org, visibility__in=['team', 'public'])
    else:
        # Default: личные + demo + все team-проекты org куда user входит
        from .models import OrganizationMember

        org_ids = list(
            OrganizationMember.objects.filter(user=request.user, deactivated_at__isnull=True).values_list(
                'organization_id', flat=True
            )
        )
        qs = SchematicProject.objects.filter(
            Q(user=request.user)
            | Q(is_demo=True)
            | Q(organization_id__in=org_ids, visibility__in=['team', 'public'])
        ).distinct()

    qs = qs.select_related('user', 'organization')
    return JsonResponse(
        {
            'ok': True,
            'projects': [_project_to_dict(p) for p in qs],
            'quota': quota_dict(request.user),
        }
    )


@login_required(login_url='accounts:login')
@require_POST
@enforce_project_limit
def api_project_create(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError, ValueError:
        return _json_error('Invalid JSON')

    name = data.get('name', '').strip()
    if not name:
        return _json_error('Name is required')

    # Org-context: если передан organization_slug, создаём team-проект.
    # Проверяем что user — member org И имеет project.create permission.
    organization = None
    visibility = data.get('visibility', 'private')
    org_slug = (data.get('organization_slug') or '').strip()
    if org_slug:
        from .models import Organization
        from .org_permissions import user_can

        try:
            organization = Organization.objects.get(slug=org_slug)
        except Organization.DoesNotExist:
            return _json_error('Organization not found', status=404)
        if not user_can(request.user, organization, 'project.create'):
            return JsonResponse(
                {
                    'ok': False,
                    'error': 'permission_denied',
                    'message': f'У вас нет прав создавать проекты в {organization.name}',
                },
                status=403,
            )
        # Team-проект — visibility=team по умолчанию (или public если запрошен)
        if visibility == 'private':
            visibility = 'team'

    project = SchematicProject.objects.create(
        user=request.user,
        name=name,
        description=data.get('description', ''),
        category=data.get('category', 'other'),
        status=data.get('status', 'draft'),
        scheme_data=data.get('scheme_data', {}),
        organization=organization,
        visibility=visibility,
    )
    _log_project_event(
        project,
        request.user,
        'project_created',
        {
            'name': project.name,
            'category': project.category,
            'visibility': project.visibility,
        },
    )

    # Audit log для team-проектов
    if organization:
        from .models import AuditLog

        AuditLog.log(
            actor=request.user,
            action='project.create',
            organization=organization,
            object_type='SchematicProject',
            object_id=project.id,
            payload={'name': project.name, 'visibility': project.visibility},
            request=request,
        )

    return JsonResponse({'ok': True, 'project': _project_to_dict(project)})


@login_required(login_url='accounts:login')
@require_POST
def api_project_update(request, pk):
    project = _project_for_write(request.user, pk)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError, ValueError:
        return _json_error('Invalid JSON')

    for field in ('name', 'description', 'category', 'status'):
        if field in data:
            setattr(project, field, data[field])
    project.save()
    _log_project_event(
        project,
        request.user,
        'project_updated',
        {
            'name': project.name,
            'status': project.status,
            'changed_fields': [
                field for field in ('name', 'description', 'category', 'status') if field in data
            ],
        },
    )
    return JsonResponse({'ok': True, 'project': _project_to_dict(project)})


@login_required(login_url='accounts:login')
@require_POST
def api_project_delete(request, pk):
    """Soft-delete: проект помечается deleted_at, физически живёт ещё 30 дней.
    Восстановить — POST /projects/api/<pk>/restore/. Жёсткое удаление —
    /projects/api/<pk>/purge/ (без возврата)."""
    project = _project_for_write(request.user, pk)
    project.soft_delete()
    return JsonResponse(
        {
            'ok': True,
            'soft_deleted': True,
            'message': f'Проект «{project.name}» в корзине. Восстановить можно в течение 30 дней.',
        }
    )


@login_required(login_url='accounts:login')
@require_POST
def api_project_restore(request, pk):
    """Возвращает проект из корзины (deleted_at=None)."""
    project = get_object_or_404(
        SchematicProject.all_objects,
        pk=pk,
        user=request.user,
        deleted_at__isnull=False,
    )
    project.restore()
    return JsonResponse(
        {
            'ok': True,
            'project': _project_to_dict(project),
            'message': f'Проект «{project.name}» восстановлен.',
        }
    )


@login_required(login_url='accounts:login')
@require_POST
def api_project_purge(request, pk):
    """Физическое удаление soft-deleted проекта. После этого восстановить нельзя."""
    project = get_object_or_404(
        SchematicProject.all_objects,
        pk=pk,
        user=request.user,
        deleted_at__isnull=False,
    )
    name = project.name
    project.delete()  # реальное удаление из БД
    return JsonResponse({'ok': True, 'message': f'Проект «{name}» удалён навсегда.'})


@login_required(login_url='accounts:login')
@require_GET
def api_project_trash_list(request):
    """Список soft-deleted проектов (для UI «Корзина»)."""
    qs = SchematicProject.all_objects.filter(
        user=request.user,
        deleted_at__isnull=False,
    ).order_by('-deleted_at')[:50]
    return JsonResponse(
        {
            'ok': True,
            'projects': [_project_to_dict(p) for p in qs],
        }
    )


@login_required(login_url='accounts:login')
@require_POST
def api_project_save_scheme(request, pk):
    project = _project_for_write(request.user, pk)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError, ValueError:
        return _json_error('Invalid JSON')

    scheme_data = data.get('scheme_data', {})
    if not isinstance(scheme_data, dict):
        return _json_error('scheme_data must be an object')
    if not isinstance(scheme_data.get('components', []), list):
        return _json_error('scheme_data.components must be an array')
    if not isinstance(scheme_data.get('connections', []), list):
        return _json_error('scheme_data.connections must be an array')
    drc = _validate_scheme_data(scheme_data)

    # Tier-лимиты: число компонентов и листов в схеме
    components = scheme_data.get('components', []) or []
    sheets = scheme_data.get('sheets', []) or []
    max_components = get_limit(request.user, 'max_components_per_scheme')
    max_sheets = get_limit(request.user, 'max_sheets_per_project')
    if max_components is not None and len(components) > max_components:
        return JsonResponse(
            {
                'ok': False,
                'error': 'quota_exceeded',
                'message': f'Free-tier: до {max_components} компонентов на схему. '
                f'У вас {len(components)}. Удалите лишние или upgrade.',
                'limit': max_components,
                'current': len(components),
            },
            status=400,
        )
    if max_sheets is not None and len(sheets) > max_sheets:
        return JsonResponse(
            {
                'ok': False,
                'error': 'quota_exceeded',
                'message': f'Free-tier: до {max_sheets} листов на проект. У вас {len(sheets)}.',
                'limit': max_sheets,
                'current': len(sheets),
            },
            status=400,
        )

    project.scheme_data = scheme_data
    project.save(update_fields=['scheme_data', 'updated_at'])
    version = ProjectVersion.objects.create(
        project=project,
        version_number=_next_project_version(project),
        scheme_data=scheme_data,
        change_note=data.get('change_note', 'Сохранение из редактора'),
    )
    _log_project_event(
        project,
        request.user,
        'scheme_saved',
        {
            'version_number': version.version_number,
            'components': len(components),
            'connections': len(scheme_data.get('connections') or []),
            'sheets': len(sheets),
            'drc_ok': drc.get('ok', False),
        },
    )

    # Trim истории до max_history_versions — Free: 10, Pro: 100
    max_versions = get_limit(request.user, 'max_history_versions')
    if max_versions is not None:
        excess_ids = list(
            project.versions.order_by('-version_number').values_list('id', flat=True)[max_versions:]
        )
        if excess_ids:
            ProjectVersion.objects.filter(id__in=excess_ids).delete()

    return JsonResponse({'ok': True, 'project': _project_to_dict(project), 'drc': drc})


@login_required(login_url='accounts:login')
@require_GET
def api_project_load_scheme(request, pk):
    project = _project_for_read(request.user, pk)
    return JsonResponse(
        {
            'ok': True,
            'scheme_data': project.scheme_data,
            'project': _project_to_dict(project),
        }
    )


@login_required(login_url='accounts:login')
@require_GET
def api_project_versions(request, pk):
    project = _project_for_read(request.user, pk)
    versions = project.versions.all()[:25]
    return JsonResponse(
        {
            'ok': True,
            'versions': [
                {
                    'id': version.id,
                    'version_number': version.version_number,
                    'change_note': version.change_note,
                    'created': version.created_at.isoformat(),
                }
                for version in versions
            ],
        }
    )


@login_required(login_url='accounts:login')
@require_GET
def api_project_dashboard(request, pk):
    project = _project_for_read(request.user, pk)
    latest_review = project.reviews.select_related('project', 'user').first()
    try:
        from .models import Comment

        comments_count = Comment.objects.filter(project=project).count()
    except Exception:
        comments_count = 0
    runs = project.simulation_runs.select_related('user')[:10]
    return JsonResponse(
        {
            'ok': True,
            'project': _project_to_dict(project),
            'scheme': {
                'components': len((project.scheme_data or {}).get('components') or []),
                'connections': len((project.scheme_data or {}).get('connections') or []),
                'has_scheme': bool(project.scheme_data),
            },
            'versions': [
                {
                    'id': version.id,
                    'version_number': version.version_number,
                    'change_note': version.change_note,
                    'created': version.created_at.isoformat(),
                }
                for version in project.versions.all()[:8]
            ],
            'simulation_runs': [
                {
                    'id': run.id,
                    'analysis_type': run.analysis_type,
                    'engine': run.engine,
                    'elapsed_ms': run.elapsed_ms,
                    'status': run.status,
                    'progress_percent': run.progress_percent,
                    'message': run.message,
                    'created': run.created_at.isoformat(),
                }
                for run in runs
            ],
            'measurements': [_measurement_to_dict(item) for item in project.measurements.all()[:12]],
            'latest_review': _review_to_dict(latest_review) if latest_review else None,
            'bom': ((latest_review.sections or {}).get('bom') if latest_review else {}) or {},
            'comments_count': comments_count,
            'events': [_event_to_dict(item) for item in project.events.select_related('user')[:20]],
        }
    )


@login_required(login_url='accounts:login')
@require_GET
def api_project_simulation_runs(request, pk):
    project = _project_for_read(request.user, pk)
    runs = project.simulation_runs.select_related('user')[:25]
    return JsonResponse(
        {
            'ok': True,
            'runs': [
                {
                    'id': run.id,
                    'analysis_type': run.analysis_type,
                    'engine': run.engine,
                    'elapsed_ms': run.elapsed_ms,
                    'status': run.status,
                    'progress_percent': run.progress_percent,
                    'message': run.message,
                    'summary': run.result_summary,
                    'warnings': run.warnings,
                    'started': run.started_at.isoformat() if run.started_at else None,
                    'finished': run.finished_at.isoformat() if run.finished_at else None,
                    'created': run.created_at.isoformat(),
                }
                for run in runs
            ],
        }
    )


@login_required(login_url='accounts:login')
@require_GET
def api_project_simulation_stats(request, pk):
    project = _project_for_read(request.user, pk)
    runs = list(project.simulation_runs.select_related('user')[:200])
    return JsonResponse(_simulation_analysis().simulation_run_stats(runs))


@login_required(login_url='accounts:login')
@require_POST
@enforce_daily_quota('simulations')
def api_project_save_simulation(request, pk):
    project = _project_for_write(request.user, pk)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError, ValueError:
        return _json_error('Invalid JSON')

    result = data.get('result', {})
    status = data.get('status', 'success')
    now = timezone.now()
    run = SimulationRun.objects.create(
        project=project,
        user=request.user,
        analysis_type=data.get('analysis_type') or result.get('type') or 'unknown',
        engine=data.get('engine', ''),
        elapsed_ms=max(0, int(data.get('elapsed_ms') or 0)),
        status=status,
        progress_percent=max(
            0, min(100, int(data.get('progress_percent') or (100 if status == 'success' else 0)))
        ),
        message=(data.get('message') or '')[:240],
        started_at=now,
        finished_at=now if status in {'success', 'error'} else None,
        netlist=data.get('netlist', ''),
        result_summary=data.get('result_summary') or _simulation_summary(result),
        result_data=result,
        warnings=data.get('warnings') or result.get('warnings') or [],
    )
    _log_project_event(
        project,
        request.user,
        'simulation_run',
        {
            'run_id': run.id,
            'analysis_type': run.analysis_type,
            'engine': run.engine,
            'status': run.status,
            'elapsed_ms': run.elapsed_ms,
            'progress_percent': run.progress_percent,
        },
    )
    return JsonResponse(
        {
            'ok': True,
            'run': {
                'id': run.id,
                'analysis_type': run.analysis_type,
                'engine': run.engine,
                'elapsed_ms': run.elapsed_ms,
                'status': run.status,
                'progress_percent': run.progress_percent,
                'created': run.created_at.isoformat(),
            },
        }
    )


@login_required(login_url='accounts:login')
@require_POST
@enforce_daily_quota('simulations')
def api_project_simulation_postprocess(request, pk):
    project = _project_for_write(request.user, pk)
    data = _read_json_payload(request)
    run = None
    run_id = data.get('simulation_run_id') or data.get('run_id')
    if run_id:
        run = project.simulation_runs.filter(id=run_id).first()
        if not run:
            return _json_error('simulation run not found', status=404)
        data = {**data, 'result': data.get('result') or run.result_data}

    result = _simulation_analysis().postprocess_simulation(data)
    if not result.get('ok'):
        return JsonResponse(result, status=400)

    saved = []
    for item in result.get('measurements') or []:
        measurement = ProjectMeasurement.objects.create(
            project=project,
            user=request.user,
            simulation_run=run,
            metric=(item.get('metric') or 'postprocess')[:80],
            label=(item.get('label') or item.get('metric') or 'Postprocess')[:160],
            value=float(item.get('value') or 0),
            unit=(item.get('unit') or '')[:24],
            status='computed',
            source='postprocess',
            result={
                'markers': result.get('markers') or [],
                'formulas': result.get('formulas') or [],
            },
        )
        saved.append(_measurement_to_dict(measurement))

    _log_project_event(
        project,
        request.user,
        'measurement_added',
        {
            'source': 'postprocess',
            'simulation_run_id': run.id if run else None,
            'measurements': len(saved),
            'metrics': list((result.get('metrics') or {}).keys()),
        },
    )
    return JsonResponse({'ok': True, 'postprocess': result, 'measurements': saved})


@login_required(login_url='accounts:login')
@require_GET
def api_project_simulation_export_csv(request, pk, run_id):
    project = _project_for_read(request.user, pk)
    run = get_object_or_404(project.simulation_runs, pk=run_id)
    csv_text = _simulation_analysis().simulation_result_to_csv(run.result_data or {})
    response = HttpResponse(csv_text, content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="dolg_simulation_{run.id}.csv"'
    _log_project_event(
        project,
        request.user,
        'simulation_run',
        {
            'run_id': run.id,
            'action': 'csv_export',
            'analysis_type': run.analysis_type,
        },
    )
    return response


@login_required(login_url='accounts:login')
@require_GET
def api_project_measurements(request, pk):
    project = _project_for_read(request.user, pk)
    return JsonResponse(
        {
            'ok': True,
            'measurements': [_measurement_to_dict(item) for item in project.measurements.all()[:50]],
        }
    )


@login_required(login_url='accounts:login')
@require_POST
def api_project_measurement_create(request, pk):
    project = _project_for_write(request.user, pk)
    data = _read_json_payload(request)
    metric = (data.get('metric') or '').strip()
    if not metric:
        return _json_error('metric is required')
    try:
        value = float(data.get('value'))
    except TypeError, ValueError:
        return _json_error('value must be numeric')

    expected = data.get('expected_value')
    tolerance_abs = data.get('tolerance_abs')
    tolerance_percent = data.get('tolerance_percent')
    expected_num = None
    tolerance_abs_num = None
    tolerance_percent_num = None
    try:
        expected_num = float(expected) if expected not in (None, '') else None
        tolerance_abs_num = float(tolerance_abs) if tolerance_abs not in (None, '') else None
        tolerance_percent_num = float(tolerance_percent) if tolerance_percent not in (None, '') else None
    except TypeError, ValueError:
        return _json_error('expected/tolerance fields must be numeric')

    result = data.get('result') if isinstance(data.get('result'), dict) else {}
    status = 'unchecked'
    if expected_num is not None:
        comparison = compare_measurement(
            metric,
            value,
            expected_value=expected_num,
            tolerance_abs=tolerance_abs_num,
            tolerance_percent=tolerance_percent_num,
            unit=data.get('unit', ''),
        )
        result = {**result, **comparison}
        status = comparison.get('status', 'unchecked')

    run = None
    run_id = data.get('simulation_run_id')
    if run_id:
        run = project.simulation_runs.filter(id=run_id).first()

    item = ProjectMeasurement.objects.create(
        project=project,
        user=request.user,
        simulation_run=run,
        metric=metric,
        label=(data.get('label') or metric)[:160],
        value=value,
        unit=(data.get('unit') or '')[:24],
        expected_value=expected_num,
        tolerance_abs=tolerance_abs_num,
        tolerance_percent=tolerance_percent_num,
        status=status,
        source=(data.get('source') or 'manual')[:40],
        result=result,
    )
    _log_project_event(
        project,
        request.user,
        'measurement_added',
        {
            'measurement_id': item.id,
            'metric': item.metric,
            'label': item.label,
            'value': item.value,
            'unit': item.unit,
            'status': item.status,
            'simulation_run_id': item.simulation_run_id,
        },
    )
    return JsonResponse({'ok': True, 'measurement': _measurement_to_dict(item)})


@login_required(login_url='accounts:login')
@require_POST
@enforce_daily_quota('simulations')
def api_simulation_fft(request):
    denied = _require_pro_feature(request.user, 'pro_fft')
    if denied:
        return denied
    data = _read_json_payload(request)
    result = _simulation_analysis().fft_spectrum(
        data.get('samples') or data.get('values') or [],
        data.get('sample_rate_hz') or data.get('sampleRateHz'),
        window=data.get('window', 'hann'),
    )
    return JsonResponse(result, status=200 if result.get('ok') else 400)


@login_required(login_url='accounts:login')
def api_simulation_voltage_field(request):
    """Поле для 3D-поверхности (DolgSurface3D). kind=wave (по умолч.) | grid.

    kind='wave': LC-лестница, переходный процесс → поле [время][узел] (бегущая волна + отражение
    от открытого конца). kind='grid': резисторная сетка N×N, DC → поле [позиция][позиция].
    Возвращает подписи осей/единицы/заголовок — для информативного графика.
    """
    from .services import large_circuits, monte_carlo

    kind = (request.GET.get('kind') or 'wave').strip()

    if kind == 'grid':
        try:
            n = int(request.GET.get('n', 25))
        except TypeError, ValueError:
            n = 25
        n = max(4, min(60, n))
        circuit = large_circuits.generate_resistor_grid_circuit(n, v=10.0, r=100.0)
        field = large_circuits.voltage_field(monte_carlo.solve_dc(circuit)['voltages'], n)
        return JsonResponse(
            {
                'ok': True,
                'kind': 'grid',
                'n': n,
                'n_nodes': circuit['n_nodes'],
                'elements': len(circuit['elements']),
                'field': field,
                'unit': 'В',
                'x_max': n,
                'z_max': n,
                'x_label': 'позиция X',
                'z_label': 'позиция Y',
                'y_label': 'напряжение, В',
                'title': 'Распределение напряжения по резисторной сетке',
            }
        )

    try:
        n = int(request.GET.get('n', 36))
    except TypeError, ValueError:
        n = 36
    n = max(8, min(48, n))
    circuit = large_circuits.generate_lc_ladder_circuit(n, v=5.0, ind=1e-3, c=1e-6, rs=15.0)
    field, meta = large_circuits.transient_wave_field(circuit, t_stop=3.5e-3, dt=1.5e-6, max_frames=140)
    return JsonResponse(
        {
            'ok': True,
            'kind': 'wave',
            'n': n,
            'n_nodes': circuit['n_nodes'],
            'elements': len(circuit['elements']),
            'field': field,
            'unit': 'В',
            'meta': meta,
            'x_max': circuit['n_line'],
            't_max': meta['t_max'],
            'x_label': 'узел (позиция вдоль линии)',
            'z_label': 'время, мс',
            'y_label': 'напряжение, В',
            'title': 'Бегущая волна по LC-линии (переходный процесс)',
        }
    )


@login_required(login_url='accounts:login')
@require_POST
@enforce_daily_quota('simulations')
def api_simulation_bode(request):
    denied = _require_pro_feature(request.user, 'pro_bode')
    if denied:
        return denied
    result = _simulation_analysis().bode_plot(_read_json_payload(request))
    return JsonResponse(result, status=200 if result.get('ok') else 400)


@login_required(login_url='accounts:login')
@require_POST
@enforce_daily_quota('simulations')
def api_simulation_monte_carlo(request):
    denied = _require_pro_feature(request.user, 'pro_monte_carlo')
    if denied:
        return denied
    result = _simulation_analysis().monte_carlo_tolerance(_read_json_payload(request))
    return JsonResponse(result, status=200 if result.get('ok') else 400)


@login_required(login_url='accounts:login')
@require_POST
@enforce_daily_quota('simulations')
def api_simulation_signal_quality(request):
    denied = _require_pro_feature(request.user, 'pro_signal_quality')
    if denied:
        return denied
    data = _read_json_payload(request)
    result = _simulation_analysis().signal_quality(
        data.get('samples') or data.get('values') or [],
        data.get('sample_rate_hz') or data.get('sampleRateHz'),
        fundamental_hz=data.get('fundamental_hz') or data.get('fundamentalHz'),
        max_harmonics=data.get('max_harmonics') or data.get('maxHarmonics') or 5,
        window=data.get('window', 'hann'),
    )
    return JsonResponse(result, status=200 if result.get('ok') else 400)


@login_required(login_url='accounts:login')
@require_POST
@enforce_daily_quota('simulations')
def api_simulation_parameter_sweep(request):
    denied = _require_pro_feature(request.user, 'pro_parameter_sweep')
    if denied:
        return denied
    result = _simulation_analysis().parameter_sweep(_read_json_payload(request))
    return JsonResponse(result, status=200 if result.get('ok') else 400)


@login_required(login_url='accounts:login')
@require_POST
@enforce_daily_quota('simulations')
def api_simulation_fallback_solve(request):
    denied = _require_pro_feature(request.user, 'server_side_solver')
    if denied:
        return denied
    data = _read_json_payload(request)
    result = _simulation_analysis().server_side_dc_fallback(
        data.get('scheme_data') or data.get('scheme') or {}
    )
    return JsonResponse(result, status=200 if result.get('ok') else 400)


@login_required(login_url='accounts:login')
@require_POST
@enforce_daily_quota('simulations')
def api_project_review_create(request, pk):
    project = _project_for_write(request.user, pk)
    review = _create_project_review(project, request.user)
    return JsonResponse({'ok': True, 'review': _review_to_dict(review)})


@login_required(login_url='accounts:login')
@require_GET
def api_project_review_latest(request, pk):
    project = _project_for_read(request.user, pk)
    review = project.reviews.select_related('project', 'user').first()
    if not review:
        try:
            writable_project = _project_for_write(request.user, pk)
        except Http404:
            return _json_error('Review has not been created yet', status=404)
        review = _create_project_review(writable_project, request.user)
    return JsonResponse({'ok': True, 'review': _review_to_dict(review)})


@login_required(login_url='accounts:login')
def project_review_page(request, review_id):
    review = _review_for_read(request.user, review_id)
    return render(
        request,
        'tools/project_review.html',
        {
            'review': review,
            'review_display': _review_to_dict(review),
            'project': review.project,
            'learning_suggestions': learning_suggestions_from_review(review),
            'page_title': f'Проверка схемы: {review.project.name}',
        },
    )


@login_required(login_url='accounts:login')
def project_review_pdf(request, review_id):
    A4, pdfmetrics, TTFont, canvas = _reportlab_pdf()
    review = _review_for_read(request.user, review_id)
    buffer = BytesIO()
    for pdf_font_name, pdf_font_path in (
        ('TimesNewRoman', r'C:\Windows\Fonts\times.ttf'),
        ('DejaVuSans', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
    ):
        try:
            pdfmetrics.registerFont(TTFont(pdf_font_name, pdf_font_path))
        except Exception:
            continue
    registered_fonts = pdfmetrics.getRegisteredFontNames()
    font_name = (
        'TimesNewRoman'
        if 'TimesNewRoman' in registered_fonts
        else ('DejaVuSans' if 'DejaVuSans' in registered_fonts else 'Helvetica')
    )
    page = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 48
    page.setFont(font_name, 14)
    review_display = _review_to_dict(review)
    page.drawString(40, y, f'DOLG: инженерная проверка схемы - {review.project.name}')
    y -= 24
    page.setFont(font_name, 10)
    page.drawString(
        40,
        y,
        f'Оценка: {review.score}/100; статус: {review_display.get("status_label")}; создано: {review.created_at:%Y-%m-%d %H:%M}',
    )
    y -= 24
    page.drawString(40, y, str(review_display.get('summary') or '')[:110])
    y -= 24

    def draw_list(title, items):
        nonlocal y
        if y < 80:
            page.showPage()
            page.setFont(font_name, 10)
            y = height - 48
        page.setFont(font_name, 11)
        page.drawString(40, y, title)
        y -= 16
        page.setFont(font_name, 9)
        if not items:
            page.drawString(54, y, '- none')
            y -= 14
            return
        for item in items[:12]:
            if y < 60:
                page.showPage()
                page.setFont(font_name, 9)
                y = height - 48
            page.drawString(54, y, f'- {str(item)[:120]}')
            y -= 14

    draw_list('Ошибки', review_display.get('errors') or [])
    draw_list('Предупреждения', review_display.get('warnings') or [])
    draw_list('Рекомендации', review_display.get('recommendations') or [])
    draw_list(
        'Экспертные правила',
        [
            f'{item.get("rule_id")} [{item.get("severity_label")}]: '
            f'{item.get("title")} - {item.get("recommendation")}'
            for item in review_display.get('expert_findings') or []
        ],
    )
    draw_list(
        'Источники проверки',
        [
            f'{item.get("rule_id")}: {source.get("title")} - {source.get("url")}'
            for item in review_display.get('expert_findings') or []
            for source in (item.get('source_references') or [])[:3]
        ],
    )
    draw_list(
        'Сценарии неисправностей',
        [f'{item.get("title")}: {item.get("recommendation")}' for item in review_display.get('faults') or []],
    )
    page.save()
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="dolg_review_{review.id}.pdf"'
    return response


@login_required(login_url='accounts:login')
def project_review_md(request, review_id):
    """Авто-протокол инженерной проверки в Markdown (для вставки в диплом/отчёты)."""
    from .services.protocol_report import render_review_markdown

    review = _review_for_read(request.user, review_id)
    markdown = render_review_markdown(_review_to_dict(review), review.project)
    response = HttpResponse(markdown, content_type='text/markdown; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="dolg_protocol_{review.id}.md"'
    return response


@login_required(login_url='accounts:login')
@require_POST
def api_cad_scheme_operations_preview(request):
    """Apply programmatic CAD/schematic operations without saving a project."""

    data = _read_json_payload(request)
    operations = data.get('operations', data.get('operation'))
    if operations is None:
        return _json_error('operations or operation is required')

    result = apply_schematic_operations(
        data.get('scheme_data') or data.get('scheme') or {},
        operations,
        atomic=bool(data.get('atomic')),
    )
    scheme_data = result.get('scheme_data') or {}
    layout_profile = (
        data.get('layout_profile')
        or data.get('standard_profile')
        or (
            (scheme_data.get('metadata') or {}).get('standard_profile')
            if isinstance(scheme_data, dict)
            else None
        )
    )
    drc = _validate_scheme_data(scheme_data)
    layout_quality = {}
    layout_quality_error = ''
    topology = {}
    topology_error = ''
    try:
        from .services.schematic_layout_quality import analyze_schematic_layout

        layout_quality = analyze_schematic_layout(scheme_data, profile=layout_profile)
    except Exception as exc:
        layout_quality_error = str(exc)
    try:
        from .services.schematic_graph import analyze_graph_topology

        topology = analyze_graph_topology(scheme_data)
    except Exception as exc:
        topology_error = str(exc)

    payload = {
        'ok': bool(result.get('ok')) and bool(drc.get('ok')) and bool(layout_quality.get('ok', True)),
        'operations_ok': bool(result.get('ok')),
        'scheme_data': scheme_data,
        'operation_report': result.get('report') or {},
        'drc': drc,
        'layout_quality': layout_quality,
        'layout_profile': layout_profile or 'generic',
        'topology': topology,
    }
    if layout_quality_error:
        payload['layout_quality_error'] = layout_quality_error
    if topology_error:
        payload['topology_error'] = topology_error
    status = 200 if payload['operations_ok'] else 400
    return JsonResponse(payload, status=status)


@login_required(login_url='accounts:login')
@require_POST
def api_cad_import_preview(request):
    data = _read_json_payload(request)
    result = import_preview(data.get('format'), data.get('source') or data.get('text') or '')

    class ImportedProject:
        scheme_data = result.get('scheme_data') or {}

    review = build_design_review(
        ImportedProject(), simulation_runs=[], measurements=[], import_summary=result.get('summary')
    )
    payload = {
        'ok': bool(result.get('ok')),
        'format': result.get('format'),
        'scheme_data': result.get('scheme_data'),
        'summary': result.get('summary'),
        'preview': result.get('preview'),
        'unsupported': result.get('unsupported'),
        'review': review,
        'learning_suggestions': learning_suggestions_from_review(review),
    }

    if result.get('ok') and data.get('save_project'):
        project = SchematicProject.objects.create(
            user=request.user,
            name=(data.get('name') or f'Imported {result.get("format")}')[:200],
            description='Imported CAD subset; run Engineering Review before production use.',
            category='other',
            status='draft',
            scheme_data=result.get('scheme_data') or {},
        )
        saved_review = _create_project_review(project, request.user, import_summary=result.get('summary'))
        _log_project_event(
            project,
            request.user,
            'import_finished',
            {
                'format': result.get('format'),
                'components': (result.get('summary') or {}).get('components_count'),
                'connections': (result.get('summary') or {}).get('connections_count'),
                'unsupported': len(result.get('unsupported') or []),
                'review_id': saved_review.id,
            },
        )
        payload['project'] = _project_to_dict(project)
        payload['saved_review'] = _review_to_dict(saved_review)

    return JsonResponse(payload, status=200 if result.get('ok') else 400)


@login_required(login_url='accounts:login')
@require_POST
def api_lithium_import_preview(request):
    """Импорт Lithium ECAD проекта (.lpr/.lsc/.lbo).

    Принимает multipart upload (1-3 файла) или JSON со строковым содержимым.
    Возвращает структурированный summary: компоненты, цепи, слои, ERC, порты.
    """
    files_text: dict[str, str] = {}

    if request.FILES:
        for upload in request.FILES.getlist('files'):
            try:
                raw = upload.read().decode('utf-8', errors='replace')
            except Exception as exc:
                return _json_error(f'Не удалось прочитать {upload.name}: {exc}')
            kind = detect_lithium_file(upload.name, raw)
            if kind:
                files_text[kind] = raw
    else:
        data = _read_json_payload(request)
        for kind in ('lpr', 'lsc', 'lbo'):
            text = data.get(f'{kind}_text')
            if text:
                files_text[kind] = text

    if not files_text:
        return _json_error('Загрузите хотя бы один файл .lpr / .lsc / .lbo')

    try:
        project = parse_lithium_project(
            lpr_text=files_text.get('lpr'),
            lsc_text=files_text.get('lsc'),
            lbo_text=files_text.get('lbo'),
        )
    except LithiumImportError as exc:
        return _json_error(str(exc), status=400)

    return JsonResponse(
        {
            'ok': True,
            'summary': project.to_dict(),
            'imported_files': sorted(files_text.keys()),
        },
        status=200,
    )


@login_required(login_url='accounts:login')
@require_POST
@enforce_daily_quota('simulations')
def api_export_scheme_pdf(request):
    A4, pdfmetrics, TTFont, canvas = _reportlab_pdf()
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError, ValueError:
        return _json_error('Invalid JSON')

    scheme_data = data.get('scheme_data', {})
    drc = _validate_scheme_data(scheme_data)
    components = scheme_data.get('components', []) if isinstance(scheme_data, dict) else []
    connections = scheme_data.get('connections', []) if isinstance(scheme_data, dict) else []

    buffer = BytesIO()
    try:
        pdfmetrics.registerFont(TTFont('TimesNewRoman', r'C:\Windows\Fonts\times.ttf'))
    except Exception:
        pass
    font_name = 'TimesNewRoman' if 'TimesNewRoman' in pdfmetrics.getRegisteredFontNames() else 'Helvetica'
    page = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    page.setFont(font_name, 14)
    page.drawString(40, height - 50, 'DOLG: экспорт принципиальной схемы')
    page.setFont(font_name, 10)
    page.drawString(40, height - 70, f'Компонентов: {len(components)}; соединений: {len(connections)}')

    y = height - 100
    page.setFont(font_name, 9)
    for item in components[:40]:
        label = item.get('label') or item.get('type') or 'component'
        catalog_ref = item.get('catalog_ref') or item.get('part_number') or ''
        page.drawString(
            40,
            y,
            f'#{item.get("id")} {label} ({item.get("type")}) x={item.get("x")} y={item.get("y")} {catalog_ref}',
        )
        y -= 14
        if y < 80:
            page.showPage()
            page.setFont(font_name, 9)
            y = height - 50

    if drc['errors'] or drc['warnings']:
        if y < 140:
            page.showPage()
            page.setFont(font_name, 9)
            y = height - 50
        page.drawString(40, y, 'DRC:')
        y -= 14
        for message in (drc['errors'] + drc['warnings'])[:20]:
            page.drawString(50, y, f'- {message}')
            y -= 14

    page.save()
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="dolg_scheme.pdf"'
    return response


# ---------------------------------------------------------------------------
# AI-ассистент DOLG: чат с тремя специализированными агентами
# ---------------------------------------------------------------------------

AI_MODES = {'recommend', 'explain', 'replace'}
AI_MAX_MESSAGE_LEN = 2000
AI_MAX_TARGET_PN_LEN = 200  # PN компонента не бывает длиннее
AI_FREE_HISTORY_TAIL = 6
AI_HISTORY_TAIL = 20  # сколько предыдущих реплик держит self-hosted AI
AI_LIVE_HISTORY_TAIL = 16  # live LLM получает меньше истории + session_summary

# Минимальный интервал между вызовами локального AI одним пользователем (в секундах).
# Защищает от случайных дабл-кликов и от спама в окно ввода. Хранится в session.
AI_MIN_INTERVAL_SEC = 2.0
# Per-minute tier-aware лимит AI-чата (анти-DoS на локальный runtime).
AI_PER_MINUTE_LIMITS = {'guest': 8, 'free': 12, 'pro': 40, 'enterprise': 80}


def _ai_rate_limit(request):
    """True если запрос отклонён по rate-limit. Состояние — в session.

    Два слоя: (1) per-call минимальный интервал (анти-burst) и (2) per-minute
    tier-aware счётчик (анти-DoS на локальный runtime) — у Pro/Enterprise лимит
    выше, staff (unlimited) без per-minute. Жёсткий дневной потолок — отдельно
    в enforce_daily_quota (БД, per-user). Здесь session-слой как доп. защита.

    Используем time.time() (wall clock), а не time.monotonic() — monotonic
    сбрасывается при рестарте процесса, и сохранённое значение становится
    больше «текущего», давая отрицательную дельту → ложный rate-limit.
    """
    now = time.time()
    last = request.session.get('_ai_last_call_at')
    if last is not None:
        delta = now - last
        if 0 <= delta < AI_MIN_INTERVAL_SEC:
            return True

    # Per-minute tier-aware (fixed-window). unlimited (staff) — без лимита.
    plan = get_effective_plan(request.user)
    if plan != 'unlimited':
        limit = AI_PER_MINUTE_LIMITS.get(plan, AI_PER_MINUTE_LIMITS['free'])
        window = int(now // 60)
        if request.session.get('_ai_minute_window') == window:
            count = request.session.get('_ai_minute_count', 0)
            if count >= limit:
                return True
            request.session['_ai_minute_count'] = count + 1
        else:
            request.session['_ai_minute_window'] = window
            request.session['_ai_minute_count'] = 1

    request.session['_ai_last_call_at'] = now
    return False


def _ai_history_from_payload(data, *, limit):
    history = data.get('history') or []
    messages = []
    if isinstance(history, list):
        for item in history[-limit:]:
            if not isinstance(item, dict):
                continue
            role = item.get('role')
            content = (item.get('content') or '').strip()
            if role in ('user', 'assistant') and content:
                messages.append({'role': role, 'content': content[:AI_MAX_MESSAGE_LEN]})
    return messages


def _scheme_from_ai_payload(data, mode):
    if mode == 'explain':
        return data.get('scheme') if isinstance(data.get('scheme'), dict) else None
    return data.get('scheme') if isinstance(data.get('scheme'), dict) else None


@login_required(login_url='accounts:login')
@require_POST
def api_ai_context(request):
    from .services.rule_ai import build_ai_scheme_context

    denied = feature_denied_response(request.user, 'ai_scheme_context')
    if denied:
        return denied

    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError, ValueError:
        return _json_error('Invalid JSON')

    project = None
    scheme = data.get('scheme') if isinstance(data.get('scheme'), dict) else None
    project_id = data.get('project_id')
    if project_id:
        try:
            project = _project_for_read(request.user, int(project_id))
            if not scheme:
                scheme = project.scheme_data
        except TypeError, ValueError:
            project = None

    context = build_ai_scheme_context(
        project=project,
        scheme=scheme,
        include_deep_hint=has_feature(request.user, 'ai_deep_hint'),
    )
    return JsonResponse({'ok': True, 'context': context})


@require_GET
def api_server_engines(request):
    """Catalog for the future Docker/Kubernetes simulation engine router."""
    category = request.GET.get('category') or None
    return JsonResponse(server_engine_payload(category=category), json_dumps_params={'ensure_ascii': False})


@require_POST
def api_server_engine_recommend(request):
    """Recommend server-side engines for the current in-memory scheme."""
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError, ValueError:
        return _json_error('Invalid JSON')
    scheme_data = data.get('scheme_data') or data.get('scheme') or {}
    if not isinstance(scheme_data, dict):
        return _json_error('scheme_data must be an object')
    try:
        limit = int(data.get('limit') or 5)
    except TypeError, ValueError:
        limit = 5
    engines = recommend_server_engines(scheme_data, limit=max(1, min(limit, 10)))
    command_text = str(data.get('message') or data.get('prompt') or data.get('command_text') or '').strip()
    action_plan = None
    if command_text:
        action_plan = plan_engine_action(
            command_text,
            scheme_data=scheme_data,
            preferred_engine=str(data.get('preferred_engine') or data.get('engine_id') or '').strip() or None,
            limit=max(1, min(limit, 10)),
        )
    return JsonResponse(
        {
            'ok': True,
            'engines': engines,
            'action_plan': action_plan,
            'router_profile': server_engine_payload()['router_profile'],
        },
        json_dumps_params={'ensure_ascii': False},
    )


def _engine_job_to_dict(job, *, include_input=False, include_result=False):
    data = {
        'id': job.id,
        'engine_id': job.engine_id,
        'engine_name': job.engine_name,
        'analysis_type': job.analysis_type,
        'status': job.status,
        'progress_percent': job.progress_percent,
        'message': job.message,
        'reason': job.reason,
        'retry_count': job.retry_count,
        'max_retries': job.max_retries,
        'result_contract_version': job.result_contract_version,
        'external_id': job.external_id,
        'worker': job.worker,
        'project_id': job.project_id,
        'created_at': job.created_at.isoformat() if job.created_at else None,
        'updated_at': job.updated_at.isoformat() if job.updated_at else None,
        'started_at': job.started_at.isoformat() if job.started_at else None,
        'heartbeat_at': job.heartbeat_at.isoformat() if job.heartbeat_at else None,
        'finished_at': job.finished_at.isoformat() if job.finished_at else None,
        'warnings': job.warnings or [],
        'artifacts': job.artifacts or [],
        'error': job.error,
        'audit_log': job.audit_log or [],
        'links': {
            'status': reverse('hello:api_engine_job_detail', args=[job.id]),
            'result': reverse('hello:api_engine_job_result', args=[job.id]),
            'retry': reverse('hello:api_engine_job_retry', args=[job.id]),
        },
    }
    if include_input:
        data.update(
            {
                'netlist': job.netlist,
                'scheme_data': job.scheme_data or {},
                'options': job.options or {},
                'input_payload': job.input_payload or {},
            }
        )
    if include_result:
        data['result'] = job.result or {}
    return data


def _engine_jobs_for_user(user):
    qs = EngineJob.objects.select_related('project', 'user')
    if user.is_staff or user.is_superuser:
        return qs
    return qs.filter(user=user)


@login_required(login_url='accounts:login')
@require_http_methods(['GET', 'POST'])
def api_engine_jobs(request):
    """Submit or list async jobs for the future external engine gateway."""
    if request.method == 'GET':
        jobs = _engine_jobs_for_user(request.user)
        engine_id = (request.GET.get('engine_id') or '').strip()
        status = (request.GET.get('status') or '').strip()
        project_id = (request.GET.get('project_id') or '').strip()
        if engine_id:
            jobs = jobs.filter(engine_id=engine_id)
        if status:
            jobs = jobs.filter(status=status)
        if project_id:
            try:
                project = _project_for_read(request.user, int(project_id))
            except TypeError, ValueError, Http404:
                return _json_error('Project not found', status=404)
            jobs = jobs.filter(project=project)
        return JsonResponse(
            {'ok': True, 'jobs': [_engine_job_to_dict(job) for job in jobs[:50]]},
            json_dumps_params={'ensure_ascii': False},
        )

    data = _read_json_payload(request)
    project = None
    project_id = data.get('project_id')
    if project_id not in (None, ''):
        try:
            project = _project_for_read(request.user, int(project_id))
        except TypeError, ValueError, Http404:
            return _json_error('Project not found', status=404)

    scheme_data = data.get('scheme_data') or data.get('scheme') or {}
    if not scheme_data and project is not None:
        scheme_data = project.scheme_data or {}
    if scheme_data and not isinstance(scheme_data, dict):
        return _json_error('scheme_data must be an object')

    options = data.get('options') or {}
    if options and not isinstance(options, dict):
        return _json_error('options must be an object')

    command_text = str(data.get('command_text') or data.get('message') or data.get('prompt') or '').strip()
    ai_command_plan = None
    engine_id = str(data.get('engine_id') or data.get('engine') or '').strip().lower()
    analysis_type = str(data.get('analysis_type') or data.get('analysis') or '').strip().lower()[:32]
    if command_text:
        ai_command_plan = plan_engine_action(
            command_text,
            scheme_data=scheme_data if isinstance(scheme_data, dict) else {},
            preferred_engine=engine_id or None,
            limit=5,
        )
        command = ai_command_plan.get('command') or {}
        engine_id = engine_id or str(command.get('engine_id') or '').strip().lower()
        analysis_type = analysis_type or str(command.get('analysis_type') or '').strip().lower()[:32]
        planned_options = command.get('options') if isinstance(command.get('options'), dict) else {}
        options = {**planned_options, **options}

    engine = get_server_engine(engine_id)
    if not engine:
        return _json_error('Unknown engine_id')

    analysis_type = analysis_type or 'unknown'
    netlist = str(data.get('netlist') or '')
    try:
        max_retries = max(0, min(int(data.get('max_retries', 2)), 10))
    except TypeError, ValueError:
        max_retries = 2
    job = EngineJob.objects.create(
        project=project,
        user=request.user,
        engine_id=engine['id'],
        engine_name=engine.get('name', ''),
        analysis_type=analysis_type or 'unknown',
        status='queued',
        progress_percent=0,
        message='Queued for external engine worker; no CLI process is started inside the web request.',
        reason='queued',
        max_retries=max_retries,
        netlist=netlist,
        scheme_data=scheme_data if isinstance(scheme_data, dict) else {},
        options=options if isinstance(options, dict) else {},
        input_payload={
            'engine_endpoint': engine.get('endpoint', ''),
            'expected_outputs': engine.get('outputs', []),
            'source': data.get('source') or 'api',
            'command_text': command_text,
            'ai_command_plan': ai_command_plan or {},
        },
        audit_log=[
            {
                'at': timezone.now().isoformat(),
                'action': 'queued',
                'actor': request.user.get_username() or 'user',
                'message': 'Queued from simulation API.',
                'meta': {
                    'engine_id': engine['id'],
                    'source': data.get('source') or 'api',
                    'ai_command': bool(ai_command_plan),
                },
            }
        ],
    )
    return JsonResponse(
        {
            'ok': True,
            'job': _engine_job_to_dict(job, include_input=True),
            'router_profile': server_engine_payload()['router_profile'],
        },
        status=202,
        json_dumps_params={'ensure_ascii': False},
    )


@login_required(login_url='accounts:login')
@require_GET
def api_engine_job_detail(request, job_id):
    job = get_object_or_404(_engine_jobs_for_user(request.user), pk=job_id)
    return JsonResponse(
        {'ok': True, 'job': _engine_job_to_dict(job, include_input=True, include_result=True)},
        json_dumps_params={'ensure_ascii': False},
    )


@login_required(login_url='accounts:login')
@require_GET
def api_engine_job_result(request, job_id):
    job = get_object_or_404(_engine_jobs_for_user(request.user), pk=job_id)
    if job.status == 'success':
        status = 200
    elif job.status in {'error', 'cancelled', 'stale'}:
        status = 409
    else:
        status = 202
    return JsonResponse(
        {
            'ok': job.status == 'success',
            'job': _engine_job_to_dict(job, include_result=True),
            'result': job.result or {},
            'pending': job.status in {'queued', 'running'},
            'terminal': job.status in {'success', 'error', 'cancelled', 'stale'},
        },
        status=status,
        json_dumps_params={'ensure_ascii': False},
    )


@login_required(login_url='accounts:login')
@require_POST
def api_engine_job_retry(request, job_id):
    job = get_object_or_404(_engine_jobs_for_user(request.user), pk=job_id)
    data = _read_json_payload(request)
    reason = str(data.get('reason') or 'Retry requested from simulation API.')[:180]
    ok, message = retry_engine_job(job, actor=request.user.get_username() or 'user', reason=reason)
    return JsonResponse(
        {'ok': ok, 'message': message, 'job': _engine_job_to_dict(job, include_input=True)},
        status=202 if ok else 409,
        json_dumps_params={'ensure_ascii': False},
    )


@login_required(login_url='accounts:login')
@require_POST
@enforce_daily_quota('simulations')
def api_monte_carlo(request):
    """Block D2: server-side Monte Carlo DC analysis + worst-case «шизо-тест».

    POST body: {scheme_data, iterations?, tolerance?, seed?,
                component_tolerances?: {comp_id: percent}, worst_case?: bool}
    Response: per-node statistics (mean/std/p05/p50/p95) + timing; при
    worst_case=true дополнительно угловая огибающая + paranoia-отчёт.
    """
    from .services.monte_carlo import _paranoia_report, run_monte_carlo, run_worst_case

    denied = _require_pro_feature(request.user, 'pro_monte_carlo')
    if denied:
        return denied
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError, ValueError:
        return _json_error('Invalid JSON')
    scheme_data = data.get('scheme_data') or {}
    if not isinstance(scheme_data, dict) or not scheme_data.get('components'):
        return _json_error('scheme_data with components required')

    # component_tolerances в payload — проценты ({comp_id: 5}); сервис ждёт доли.
    raw_tolerances = data.get('component_tolerances')
    component_tolerances = None
    if isinstance(raw_tolerances, dict):
        converted = {}
        for key, val in raw_tolerances.items():
            try:
                converted[str(key)] = float(val) / 100.0
            except TypeError, ValueError:
                continue
        component_tolerances = converted or None
    want_worst_case = bool(data.get('worst_case', True))
    try:
        result = run_monte_carlo(
            scheme_data,
            iterations=int(data.get('iterations') or 1000),
            tolerance=float(data.get('tolerance') or 0.05),
            seed=data.get('seed'),
            component_tolerances=component_tolerances,
        )
        if want_worst_case:
            worst = run_worst_case(
                scheme_data,
                tolerance=float(data.get('tolerance') or 0.05),
                component_tolerances=component_tolerances,
                seed=data.get('seed'),
            )
            result['worst_case'] = worst
            result['paranoia'] = _paranoia_report(worst)
    except Exception as exc:
        return _json_error(f'Monte Carlo failed: {exc}')
    return JsonResponse({'ok': True, **result})


@login_required(login_url='accounts:login')
@require_POST
@enforce_daily_quota('simulations')
def api_rf_analysis(request):
    """RF S-параметры 2-портового фильтра через scikit-rf.

    POST body: {kind: rc_lowpass|rc_highpass|lc_lowpass, r_ohm?, c_farad?,
                l_henry?, f_start?, f_stop?, points?}
    Response: S21/S11 (дБ) по частоте + частота среза −3 дБ + аналитический угол.
    """
    from .services.rf_analysis import analyze_filter

    denied = _require_pro_feature(request.user, 'pro_monte_carlo')
    if denied:
        return denied
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError, ValueError:
        return _json_error('Invalid JSON')

    def _num(key):
        val = data.get(key)
        try:
            return float(val) if val is not None else None
        except TypeError, ValueError:
            return None

    try:
        result = analyze_filter(
            (data.get('kind') or 'rc_lowpass').strip(),
            r_ohm=_num('r_ohm'),
            c_farad=_num('c_farad'),
            l_henry=_num('l_henry'),
            f_start=_num('f_start'),
            f_stop=_num('f_stop'),
            points=int(data.get('points') or 401),
        )
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(f'RF analysis failed: {exc}')
    return JsonResponse({'ok': True, **result})


@login_required(login_url='accounts:login')
@require_POST
@enforce_daily_quota('simulations')
def api_export_circuit_python(request):
    """Block B1: scheme_data → CircuitPython code.py.

    POST body: {"scheme_data": {...}, "target_board": "raspberry_pi_pico"}
    Response: text/plain с готовым code.py для скачивания.
    """
    from .services.circuit_python_export import generate_circuit_python

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError, ValueError:
        return _json_error('Invalid JSON')

    scheme_data = data.get('scheme_data') or {}
    target_board = data.get('target_board') or 'raspberry_pi_pico'
    if not isinstance(scheme_data, dict) or not scheme_data.get('components'):
        return _json_error('scheme_data with components required')

    try:
        code = generate_circuit_python(scheme_data, target_board=target_board)
    except Exception as exc:
        return _json_error(f'Generator failed: {exc}')

    from django.http import HttpResponse

    response = HttpResponse(code, content_type='text/x-python; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="code.py"'
    return response


@login_required(login_url='accounts:login')
@require_POST
@enforce_daily_quota('simulations')
def api_engineering_review(request):
    """Engineering Review V2: in-memory схема → JSON-отчёт без сохранения проекта.

    POST body: {"scheme_data": {...}}
    Response: {ok, score, status, score_breakdown, errors, warnings, faults, ...}

    Решает жалобу юзера «2 сообщения о фреймворках» — теперь это полноценный
    структурированный отчёт. Frontend показывает в модале с табами.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError, ValueError:
        return _json_error('Invalid JSON')

    scheme_data = data.get('scheme_data') or {}
    if not isinstance(scheme_data, dict) or not scheme_data.get('components'):
        return _json_error('scheme_data with components required')

    class InMemoryProject:
        def __init__(self, sd):
            self.scheme_data = sd

    project = InMemoryProject(scheme_data)
    try:
        review = build_design_review(
            project,
            simulation_runs=[],
            measurements=[],
            import_summary=None,
        )
    except Exception:
        logger.exception('In-memory engineering review failed')
        return _json_error('Review build failed. Details were written to the server log.', status=500)

    # Score breakdown — пересчёт компонентов score для drill-down UI.
    # Если scoring изменится в build_design_review, этот блок останется
    # consistent с реальной формулой через те же поля.
    score = review.get('score', 0) or 0
    breakdown = {
        'starting': 100,
        'errors_penalty': -len(review.get('errors') or []) * 20,
        'warnings_penalty': -len(review.get('warnings') or []) * 6,
        'critical_count': review.get('critical_count', 0),
        'risk_count': review.get('risk_count', 0),
        'final_score': score,
    }

    return JsonResponse(
        {
            'ok': True,
            'score': score,
            'status': review.get('status'),
            'summary': review.get('summary'),
            'score_breakdown': breakdown,
            'errors': review.get('errors') or [],
            'warnings': review.get('warnings') or [],
            'recommendations': review.get('recommendations') or [],
            'faults': review.get('faults') or [],
            'sections': review.get('sections') or {},
            'expert_findings': review.get('expert_findings') or [],
            'critical_count': review.get('critical_count', 0),
            'risk_count': review.get('risk_count', 0),
        }
    )


def _protocol_findings_from_review(review_report):
    findings = []
    for message in review_report.get('errors') or []:
        findings.append({'severity': 'error', 'message': str(message)})
    for message in review_report.get('warnings') or []:
        findings.append({'severity': 'warning', 'message': str(message)})
    for fault in review_report.get('faults') or []:
        if isinstance(fault, dict):
            findings.append(
                {
                    'rule_id': fault.get('code') or fault.get('rule_id') or '',
                    'severity': 'error',
                    'message': fault.get('title') or fault.get('message') or str(fault),
                    'recommendation': fault.get('recommendation') or '',
                }
            )
    for finding in review_report.get('expert_findings') or []:
        if not isinstance(finding, dict):
            continue
        severity = finding.get('severity') or finding.get('level') or 'info'
        if severity in {'critical', 'error'}:
            severity = 'error'
        elif severity in {'risk', 'warning'}:
            severity = 'warning'
        else:
            severity = 'info'
        findings.append(
            {
                'rule_id': finding.get('rule_id') or '',
                'severity': severity,
                'message': finding.get('title') or finding.get('message') or str(finding),
                'recommendation': finding.get('recommendation') or '',
                'source_references': finding.get('source_references') or [],
            }
        )
    return findings[:40]


@login_required(login_url='accounts:login')
@require_POST
def api_generate_protocol(request):
    """Авто-протокол (Markdown): инженерный отчёт проекта ИЛИ лабораторной работы.

    POST: {scheme_data?, measurements?, lab_calcs?, findings?, title?, author?,
           include_dc?, download?}. Один генератор для симулятора и инженерной
           лаборатории (см. services/protocol_generator). `download:true` отдаёт
           .md файлом, иначе JSON {ok, markdown, sections}.
    """
    from .services.protocol_generator import build_protocol

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError, ValueError:
        return _json_error('Invalid JSON')

    project = None
    project_id = data.get('project_id')
    if project_id not in (None, ''):
        try:
            project = _project_for_read(request.user, int(project_id))
        except Http404, TypeError, ValueError:
            return _json_error('Project not found', status=404)

    scheme_data = data.get('scheme_data') if isinstance(data.get('scheme_data'), dict) else None
    simulation_runs = data.get('simulation_runs') if isinstance(data.get('simulation_runs'), list) else None
    measurements = data.get('measurements') if isinstance(data.get('measurements'), list) else None
    findings = data.get('findings') if isinstance(data.get('findings'), list) else None
    notes = data.get('notes')
    title = str(data.get('title') or 'Протокол проектирования')[:200]

    if project is not None:
        saved_runs = list(project.simulation_runs.all()[:10])
        saved_measurements = list(project.measurements.all()[:50])
        scheme_data = scheme_data or project.scheme_data
        simulation_runs = simulation_runs or saved_runs
        measurements = measurements or [_measurement_to_dict(item) for item in saved_measurements]
        title = str(data.get('title') or f'Протокол проектирования: {project.name}')[:200]

        if data.get('include_review', True):
            try:
                review_report = build_design_review(
                    project,
                    simulation_runs=saved_runs,
                    measurements=saved_measurements,
                    import_summary=None,
                )
                findings = (findings or []) + _protocol_findings_from_review(review_report)
                if not notes and review_report.get('summary'):
                    score = review_report.get('score')
                    status = review_report.get('status_label') or review_report.get('status')
                    notes = f'Engineering review: {score}/100 - {status}. {review_report.get("summary")}'
            except Exception:
                logger.exception('Project protocol review build failed')
    result = build_protocol(
        title=title,
        scheme_data=scheme_data,
        include_dc=bool(data.get('include_dc', True)),
        simulation_runs=simulation_runs,
        measurements=measurements,
        lab_calcs=data.get('lab_calcs') if isinstance(data.get('lab_calcs'), list) else None,
        findings=findings,
        notes=notes,
        author=getattr(request.user, 'username', None),
    )

    output_format = str(data.get('format') or data.get('download_format') or '').lower()
    if output_format in {'pdf', 'application/pdf'}:
        response = HttpResponse(_render_protocol_pdf(result['markdown']), content_type='application/pdf')
        filename = f'dolg_protocol_project_{project.id}.pdf' if project else 'protocol.pdf'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    if data.get('download'):
        response = HttpResponse(result['markdown'], content_type='text/markdown; charset=utf-8')
        filename = f'dolg_protocol_project_{project.id}.md' if project else 'protocol.md'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    payload = {
        'ok': True,
        'markdown': result['markdown'],
        'sections': result['sections'],
        'meta': result['meta'],
    }
    if project is not None:
        payload['project'] = {'id': project.id, 'name': project.name}
    return JsonResponse(payload)


@login_required(login_url='accounts:login')
@require_POST
@enforce_daily_quota('ai_requests')
def api_ai_chat(request):
    from . import ai_assistant
    from .services.rule_ai import build_rule_based_reply

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError, ValueError:
        return _json_error('Invalid JSON')

    mode = (data.get('mode') or 'recommend').strip()
    if mode not in AI_MODES:
        return _json_error('Unknown mode')

    effective_plan = get_effective_plan(request.user)
    mode_feature = {
        'recommend': 'ai_chat_basic',
        'explain': 'ai_chat_extended',
        'replace': 'ai_chat_extended',
    }.get(mode, 'ai_chat_basic')
    denied = feature_denied_response(request.user, mode_feature)
    if denied:
        return denied

    raw_message = (data.get('message') or '').strip()
    if not raw_message:
        return _json_error('message is required')
    if len(raw_message) > AI_MAX_MESSAGE_LEN:
        return _json_error(f'message too long (макс. {AI_MAX_MESSAGE_LEN} символов)')
    # Prompt-injection guard: sanitize + wrap в делимитер.
    from .services.ai_prompt_guard import sanitize_user_input, wrap_user_message

    user_message_clean, _suspicious = sanitize_user_input(raw_message, max_len=AI_MAX_MESSAGE_LEN)
    if _suspicious:
        logger.warning('ai_chat: prompt-injection markers in message from user=%s', request.user.id)
    user_message = wrap_user_message(user_message_clean)

    if _ai_rate_limit(request):
        return JsonResponse(
            {'ok': False, 'error': 'Слишком часто. Подождите секунду перед следующим вопросом.'},
            status=429,
        )

    extended_ai = has_feature(request.user, 'ai_chat_extended')
    history_limit = AI_HISTORY_TAIL if extended_ai else AI_FREE_HISTORY_TAIL
    live_history_limit = AI_LIVE_HISTORY_TAIL if extended_ai else AI_FREE_HISTORY_TAIL

    scheme = _scheme_from_ai_payload(data, mode)
    history = _ai_history_from_payload(data, limit=history_limit)
    session_summary = (data.get('session_summary') or '').strip()[:1000]
    last_intent = (data.get('last_intent') or '').strip()[:80]
    project = None
    project_id = data.get('project_id')
    if project_id:
        try:
            project = _project_for_read(request.user, int(project_id))
            if not scheme:
                scheme = project.scheme_data
        except TypeError, ValueError:
            project = None

    if not ai_assistant.live_enabled():
        catalog = ai_assistant.build_catalog_snapshot(limit=20)
        result = build_rule_based_reply(
            user_message,
            mode=mode,
            project=project,
            scheme=scheme,
            catalog=catalog,
            history=history,
            session_summary=session_summary,
            last_intent=last_intent,
            include_deep_hint=has_feature(request.user, 'ai_deep_hint'),
        )
        return JsonResponse(
            {
                'ok': True,
                'demo': True,
                'self_hosted': True,
                'backend': 'rule_based',
                'reply': result['reply'],
                'mode': mode,
                'plan': effective_plan,
                'entitlements': feature_summary(request.user),
                'agent': result['agent'],
                'intent': result.get('intent'),
                'intent_label': result.get('intent_label'),
                'confidence': result.get('confidence'),
                'quick_actions': result.get('quick_actions') or [],
                'render': result.get('render') or [],
                'skills': result.get('skills') or [],
                'context_sources': result.get('context_sources') or [],
                'used_context': result.get('used_context') or {},
                'retrieval_context': result.get('retrieval_context') or {},
                'deep_hint': result.get('deep_hint') or {},
                'session_summary': result.get('session_summary') or '',
                'usage': result.get('usage') or {},
                'token_usage': result.get('usage') or {},
            }
        )

    scheme = scheme or (data.get('scheme') if mode == 'explain' else None)
    target_pn = None
    if mode == 'replace':
        target_pn = (data.get('target_pn') or '').strip()[:AI_MAX_TARGET_PN_LEN]

    if mode == 'replace':
        catalog = ai_assistant.build_catalog_snapshot(
            lifecycle_in=['active', 'nrnd'],
            exclude_pn=target_pn,
            limit=60,
        )
    elif mode == 'explain':
        cats = set()
        if isinstance(scheme, dict):
            for comp in scheme.get('components', []) or []:
                slug = COMPONENT_TO_CATEGORY.get((comp.get('type') or '').lower())
                if slug:
                    cats.add(slug)
        catalog = ai_assistant.build_catalog_snapshot(
            category_slugs=list(cats) or None,
            limit=20,
        )
    else:
        catalog = ai_assistant.build_catalog_snapshot(limit=30)

    messages = _ai_history_from_payload(data, limit=live_history_limit)
    if session_summary:
        messages.insert(
            0,
            {
                'role': 'assistant',
                'content': f'Краткая сводка предыдущего диалога: {session_summary}',
            },
        )
    messages.append({'role': 'user', 'content': user_message})

    # build_system_blocks — список блоков с cache_control на стабильном
    # префиксе; экономит ~5× токенов между turn-ами одной сессии.
    system_blocks = ai_assistant.build_system_blocks(
        mode,
        catalog,
        scheme=scheme,
        target_pn=target_pn,
    )

    # Retrieval-grounding: подмешиваем выверенные факты из базы DOLG (глоссарий,
    # статьи, практикумы, источники) отдельным НЕкешируемым блоком в конце —
    # чтобы на «что такое резистор» ассистент опирался на текст, а не выдумывал,
    # и мог сослаться на источник (expert-first). Cache breakpoint на блоке 0 не
    # ломается: добавляем после стабильного префикса.
    from .services.ai_retrieval import build_retrieval_context, retrieval_lines

    retrieval = build_retrieval_context(
        user_message_clean,
        intent=last_intent,
        project=project,
        scheme=scheme if isinstance(scheme, dict) else None,
    )
    context_lines = retrieval_lines(retrieval, limit=6)
    if context_lines:
        context_block = (
            '### CONTEXT (факты из базы DOLG — опирайся на них, при использовании '
            'ссылайся на источник; если данных нет, скажи об этом, не выдумывай) ###\n'
            + '\n'.join(f'- {line}' for line in context_lines)
        )
        system_blocks.append({'type': 'text', 'text': context_block})

    try:
        result = ai_assistant.call_live(messages, system_blocks, mode=mode)
    except ai_assistant.AIError as exc:
        logger.warning('ai_chat: live backend failed, using rule-based fallback: %s', exc)
        fallback = build_rule_based_reply(
            user_message,
            mode=mode,
            project=project,
            scheme=scheme,
            catalog=catalog,
            history=history,
            session_summary=session_summary,
            last_intent=last_intent,
            include_deep_hint=has_feature(request.user, 'ai_deep_hint'),
        )
        return JsonResponse(
            {
                'ok': True,
                'demo': True,
                'degraded': True,
                'backend': 'rule_based',
                'live_error': exc.user_message,
                'reply': fallback['reply'],
                'mode': mode,
                'plan': effective_plan,
                'entitlements': feature_summary(request.user),
                'agent': fallback.get('agent'),
                'intent': fallback.get('intent'),
                'intent_label': fallback.get('intent_label'),
                'confidence': fallback.get('confidence'),
                'quick_actions': fallback.get('quick_actions') or [],
                'render': fallback.get('render') or [],
                'skills': fallback.get('skills') or [],
                'context_sources': fallback.get('context_sources') or retrieval.get('sources') or [],
                'used_context': fallback.get('used_context') or retrieval.get('counts') or {},
                'retrieval_context': fallback.get('retrieval_context') or {},
                'deep_hint': fallback.get('deep_hint') or {},
                'session_summary': fallback.get('session_summary') or session_summary,
                'usage': fallback.get('usage') or {'backend': 'rule_based'},
                'token_usage': fallback.get('usage') or {'backend': 'rule_based'},
            }
        )

    return JsonResponse(
        {
            'ok': True,
            'reply': result['text'],
            'backend': result.get('backend') or (result.get('usage') or {}).get('backend'),
            'usage': result.get('usage') or {},
            'token_usage': result.get('usage') or {},
            'mode': mode,
            'plan': effective_plan,
            'entitlements': feature_summary(request.user),
            'agent': result.get('agent'),
            'model': result.get('model'),
            'session_summary': session_summary,
            'context_sources': retrieval.get('sources') or [],
            'used_context': retrieval.get('counts') or {},
            'quick_actions': [],
        }
    )
