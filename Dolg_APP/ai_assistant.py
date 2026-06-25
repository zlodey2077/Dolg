"""
Local AI assistant for DOLG.

Runtime is intentionally self-hosted: Ollama generates text, PyTorch tiny
models provide circuit hints, and rule/retrieval layers remain the fallback.
The public API keeps the old function names where useful, but cloud providers
are not part of the active runtime.
"""

import hashlib
import json
import logging
import os
import sys

import requests
from django.conf import settings
from django.core.cache import cache

from shop.models import Product

logger = logging.getLogger(__name__)

TIMEOUT_SEC = int(os.getenv('LOCAL_AI_TIMEOUT_SEC') or os.getenv('OLLAMA_TIMEOUT_SEC') or '75')

# Бюджет JSON-snapshot, передаваемого в system prompt: больше токенов = дороже,
# меньше = модель не видит достаточно вариантов. 6000 символов ≈ 1.5к токенов.
CATALOG_BYTES_BUDGET = 6000
SCHEME_BYTES_BUDGET = 4000

# Минимальный размер стабильного system-блока. Для Ollama cache_control не
# отправляется, но порог оставлен как совместимый ориентир для compact prompt.
PROMPT_CACHE_MIN_CHARS = 4500


# --- Доменные исключения для понятных HTTP-маппингов в view ----------------


class AIError(Exception):
    """Базовое исключение модуля. http_status — что вернуть пользователю."""

    http_status = 502
    user_message = 'AI временно недоступен.'


class AINotConfiguredError(AIError):
    http_status = 503
    user_message = 'Локальный AI не настроен: проверьте OLLAMA_BASE_URL.'


class AIAuthError(AIError):
    http_status = 502
    user_message = 'Локальный AI отклонил запрос. Проверьте настройки runtime.'


class AIRateLimitError(AIError):
    http_status = 429
    user_message = 'Локальный AI временно перегружен. Подождите 30 секунд.'


class AINetworkError(AIError):
    http_status = 504
    user_message = 'Локальный AI/Ollama не отвечает.'


class AIServerError(AIError):
    http_status = 502
    user_message = 'Локальный AI вернул ошибку. Попробуйте ещё раз.'


def is_enabled():
    return ollama_enabled()


def active_backend():
    if ollama_enabled():
        return 'ollama'
    return 'rule_based'


def live_enabled():
    return active_backend() == 'ollama'


def _product_to_dict(p):
    return {
        'name': p.name,
        'pn': p.part_number or p.slug,
        'cat': p.category.slug if p.category_id else None,
        'mfr': p.manufacturer,
        'price': float(p.price) if p.price is not None else None,
        'stock': p.stock,
        'lifecycle': p.lifecycle_status,
        'package': p.package_type or '',
        'params': p.parameters or {},
    }


CATALOG_CACHE_TTL_SEC = 60  # короткий TTL — каталог меняется редко, но
# не хочется кешировать stale-цены или новые товары на полчаса.


def _catalog_cache_key(category_slugs, lifecycle_in, exclude_pn, limit):
    payload = json.dumps(
        {
            'c': sorted(category_slugs) if category_slugs else None,
            'l': sorted(lifecycle_in) if lifecycle_in else None,
            'x': (exclude_pn or '').lower(),
            'n': int(limit),
        },
        ensure_ascii=False,
    )
    digest = hashlib.sha1(payload.encode('utf-8')).hexdigest()[:16]
    return f'dolg:catalog_snapshot:{digest}'


def build_catalog_snapshot(category_slugs=None, lifecycle_in=None, exclude_pn=None, limit=25):
    """Снимок каталога для AI-prompt-а с кешированием на CATALOG_CACHE_TTL_SEC.

    Кеш хранится в Django cache (по умолчанию LocMem); TTL короткий, потому что
    цены/lifecycle могут меняться. На multi-turn AI-сессии 5+ запросов экономия
    кратная — без кеша каждый turn делал бы SELECT по shop_product.
    """
    key = _catalog_cache_key(category_slugs, lifecycle_in, exclude_pn, limit)
    cached = cache.get(key)
    if cached is not None:
        return cached

    qs = Product.objects.select_related('category').all()
    if category_slugs:
        qs = qs.filter(category__slug__in=list(category_slugs))
    if lifecycle_in:
        qs = qs.filter(lifecycle_status__in=list(lifecycle_in))
    if exclude_pn:
        qs = qs.exclude(part_number__iexact=exclude_pn)
    qs = qs.filter(stock__gt=0).order_by('-stock', 'price')[:limit]
    snapshot = [_product_to_dict(p) for p in qs]
    cache.set(key, snapshot, CATALOG_CACHE_TTL_SEC)
    return snapshot


# --- Профили агентов ----------------------------------------------------
#
# Каждый профиль — самодостаточная конфигурация локального AI-агента:
#   model      — логическое имя профиля; фактическая модель берётся из OLLAMA_MODEL
#   temperature — креативность (низкая для технических задач)
#   max_tokens — размер ответа
#   persona    — кто отвечает (формирует тон)
#   guidelines — что и как делать
#   output_hint — структура ответа (модель чаще её соблюдает)

AGENT_PROFILES = {
    'recommend': {
        'title': 'Инженер-схемотехник',
        'model': 'local-ollama-recommend',
        'temperature': 0.3,
        'max_tokens': 1024,
        'persona': (
            'Ты — опытный инженер-схемотехник. Подбираешь компоненты из '
            'доступного каталога DOLG под конкретную задачу пользователя.'
        ),
        'guidelines': (
            '1) Выбирай компоненты ТОЛЬКО из CATALOG (не выдумывай part_number).\n'
            '2) Расчёт обязателен: закон Ома, формула делителя, RC-постоянная и т.п.\n'
            '3) Указывай номиналы по E12-ряду, если каталог даёт выбор.\n'
            '4) Учитывай лимит мощности: P=V²/R для R, проверяй TDP.\n'
            '5) Если задача неоднозначна — задай 1-2 уточняющих вопроса.'
        ),
        'output_hint': (
            'Структура ответа:\n'
            '**Расчёт:** короткая выкладка с формулой и числами.\n'
            '**Компоненты:**\n'
            '- R1 = 10 кОм (PN-12345, 0.25 Вт, 5%)\n'
            '- C1 = 100 нФ (PN-67890)\n'
            '**Что получится:** одна строка о результате.'
        ),
    },
    'explain': {
        'title': 'Schematic reviewer',
        'model': 'local-ollama-explain',
        'temperature': 0.2,
        'max_tokens': 1200,
        'persona': (
            'Ты — schematic-reviewer: разбираешь принципиальную схему и '
            'ищешь конкретные ошибки. Не философствуешь, а указываешь пальцем.'
        ),
        'guidelines': (
            '1) Сначала — ОДНА строка о назначении схемы (что она делает).\n'
            '2) Потом 2-3 ключевых узла с расчётом (V, I).\n'
            '3) Затем — список потенциальных ошибок с точным id компонента:\n'
            '   - отсутствует GND\n'
            '   - короткое замыкание (узел X)\n'
            '   - превышение TDP резистора Rn\n'
            '   - LED без токоограничителя\n'
            '   - плавающий вход транзистора\n'
            "4) Если ошибок нет — прямо скажи 'критичных проблем нет'."
        ),
        'output_hint': (
            'Структура:\n'
            '**Назначение:** одна строка.\n'
            '**Ключевые узлы:** N1 = ... В, ток через R1 = ... мА.\n'
            "**Проблемы:** список или 'критичных проблем нет'.\n"
            '**Что улучшить:** 1-2 пункта (опционально).'
        ),
    },
    'replace': {
        'title': 'Supply-chain-эксперт',
        'model': 'local-ollama-replace',
        'temperature': 0.2,
        'max_tokens': 900,
        'persona': (
            'Ты — supply-chain-эксперт по замене EOL/устаревших компонентов. '
            'Главное — совместимость по корпусу, pin-out и ключевым параметрам.'
        ),
        'guidelines': (
            '1) Подбирай 1-3 замены ТОЛЬКО из CATALOG (lifecycle=active/nrnd).\n'
            '2) Сравнение по: package_type, ключевым параметрам, температуре.\n'
            '3) Обязательно отметь РИСКИ замены: отличия pin-out, корпуса, рейтингов.\n'
            "4) Если pin-out отличается — пометь это как 'требует переразводки PCB'.\n"
            '5) Если в CATALOG нет адекватной замены — скажи прямо.'
        ),
        'output_hint': (
            'Структура:\n'
            '**Целевой компонент:** PN из запроса + что это.\n'
            '**Замены:**\n'
            '1. PN-1 — package, ключевые отличия, риск (низкий/средний/высокий).\n'
            '2. PN-2 — ...\n'
            '**Рекомендация:** какой выбрать и почему.'
        ),
    },
}


def get_agent_profile(mode):
    return AGENT_PROFILES.get(mode)


def build_system_blocks(mode, catalog, scheme=None, target_pn=None):
    """Возвращает system prompt в виде ДВУХ блоков:

    1. Stable — persona + guidelines + output_hint + CATALOG (помечается
       cache_control: ephemeral). Меняется только при бампе профиля или
       обновлении каталога — повторные turn-ы из той же сессии хитят кеш и
       платим только за дельту (msgs).
    2. Volatile — SCHEME (для explain) или target_pn (для replace) — то,
       что меняется per-call.

    Если стабильный блок длинный, cache_control сохраняется в структуре для
    совместимости старых тестов, но локальный Ollama-клиент его не отправляет.
    """
    profile = AGENT_PROFILES.get(mode) or AGENT_PROFILES['recommend']
    catalog_json = json.dumps(catalog, ensure_ascii=False, default=str)[:CATALOG_BYTES_BUDGET]
    # Prompt-injection hardening — добавляется в самое начало system prompt,
    # чтобы LLM прочитал правила безопасности раньше всего остального.
    from .services.ai_prompt_guard import SYSTEM_HARDENING_PREFIX

    stable_text = '\n'.join(
        [
            SYSTEM_HARDENING_PREFIX,
            profile['persona'],
            '\nОтвечай на русском, кратко (до трёх абзацев), по делу. '
            'Если данных мало — открыто скажи об этом, не выдумывай.',
            '\nПравила:\n' + profile['guidelines'],
            '\n' + profile['output_hint'],
            f'\nCATALOG ({len(catalog)} позиций, JSON):\n{catalog_json}',
        ]
    )
    blocks = [{'type': 'text', 'text': stable_text}]
    if len(stable_text) >= PROMPT_CACHE_MIN_CHARS:
        blocks[0]['cache_control'] = {'type': 'ephemeral'}

    volatile_parts = []
    if mode == 'explain' and scheme is not None:
        scheme_json = json.dumps(scheme, ensure_ascii=False, default=str)[:SCHEME_BYTES_BUDGET]
        volatile_parts.append(f'SCHEME (текущая схема пользователя):\n{scheme_json}')
    elif mode == 'replace':
        volatile_parts.append(f'Целевой компонент для замены: {target_pn or "(не указан)"}')
    if volatile_parts:
        blocks.append({'type': 'text', 'text': '\n'.join(volatile_parts)})

    return blocks


def build_system_prompt(mode, catalog, scheme=None, target_pn=None):
    """Backwards-compat: плоский текст system-prompt-а (для тестов и логов)."""
    blocks = build_system_blocks(mode, catalog, scheme=scheme, target_pn=target_pn)
    return '\n'.join(b['text'] for b in blocks)


# --- Локальная LLM через Ollama -------------------------------------------
#
# Ollama даёт локальный генеративный слой (Qwen3/Phi и т.п.) через HTTP на
# localhost:11434. Обучающие данные проекта подключаются как RAG/grounding:
# каталог, retrieval-факты и scheme context передаются в system prompt.
#
# Включение: OLLAMA_BASE_URL=http://localhost:11434 (+ опц. OLLAMA_MODEL=qwen3:0.6b).


def ollama_base_url():
    return (os.getenv('OLLAMA_BASE_URL') or getattr(settings, 'OLLAMA_BASE_URL', '') or '').rstrip('/')


def ollama_model():
    return os.getenv('OLLAMA_MODEL') or getattr(settings, 'OLLAMA_MODEL', '') or 'qwen3:0.6b'


def ollama_enabled():
    if _running_tests() and os.getenv('LIVE_LOCAL_AI_IN_TESTS') != '1':
        return False
    return bool(ollama_base_url())


def _running_tests():
    return any(arg == 'test' or arg.endswith('pytest') for arg in sys.argv)


def _flatten_system(system):
    """Flatten structured system blocks into one Ollama system text."""
    if isinstance(system, list):
        return '\n\n'.join(b.get('text', '') for b in system if isinstance(b, dict))
    return str(system or '')


def call_ollama(
    messages,
    system,
    *,
    mode=None,
    model=None,
    max_tokens=None,
    temperature=None,
    timeout=TIMEOUT_SEC,
    use_cache=True,
):
    """Call local Ollama /api/chat with DOLG grounding."""
    base = ollama_base_url()
    if not base:
        raise AINotConfiguredError('OLLAMA_BASE_URL не задан')

    profile = AGENT_PROFILES.get(mode) if mode else None
    sys_text = _flatten_system(system)
    chat_messages = ([{'role': 'system', 'content': sys_text}] if sys_text else []) + list(messages)
    payload = {
        'model': model or ollama_model(),
        'messages': chat_messages,
        'stream': False,
        'think': False,
        'options': {
            'temperature': temperature
            if temperature is not None
            else (profile['temperature'] if profile else 0.3),
            'num_predict': max_tokens or (profile['max_tokens'] if profile else 1024),
        },
    }
    try:
        r = requests.post(f'{base}/api/chat', json=payload, timeout=timeout)
    except requests.RequestException as exc:
        logger.warning('Ollama request error: %s', exc)
        raise AINetworkError(str(exc)) from exc

    if r.status_code != 200:
        logger.warning('Ollama %s: %s', r.status_code, r.text[:300])
        raise AIServerError(f'Ollama вернул {r.status_code}')

    data = r.json()
    text = ((data.get('message') or {}).get('content') or '').strip() or '(пустой ответ)'
    return {
        'text': text,
        'stop_reason': data.get('done_reason'),
        'usage': {
            'input_tokens': data.get('prompt_eval_count', 0),
            'output_tokens': data.get('eval_count', 0),
            'backend': 'ollama',
        },
        'model': payload['model'],
        'agent': profile['title'] if profile else None,
    }


def ollama_status(timeout=2):
    base = ollama_base_url()
    model = ollama_model()
    status = {
        'configured': bool(base),
        'available': False,
        'base_url': base,
        'model': model,
        'model_installed': False,
        'models': [],
        'error': '',
    }
    if _running_tests() and os.getenv('LIVE_LOCAL_AI_IN_TESTS') != '1':
        status['configured'] = False
        status['error'] = 'disabled during tests'
        return status
    if not base:
        status['error'] = 'OLLAMA_BASE_URL is empty'
        return status

    try:
        response = requests.get(f'{base}/api/tags', timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        status['error'] = str(exc)
        return status

    models = [
        item.get('name') or item.get('model')
        for item in data.get('models', [])
        if isinstance(item, dict) and (item.get('name') or item.get('model'))
    ]
    status.update(
        {
            'available': True,
            'models': models,
            'model_installed': model in models or any(name.split(':', 1)[0] == model for name in models),
            'error': '',
        }
    )
    return status


def pytorch_status():
    status = {
        'configured': True,
        'available': False,
        'model_exists': False,
        'model_path': '',
        'model_version': '',
        'error': '',
    }
    try:
        from Dolg_APP.ml.neural import MODEL_VERSION, default_model_path, torch_available

        path = default_model_path()
        status.update(
            {
                'available': torch_available(),
                'model_exists': path.exists(),
                'model_path': str(path),
                'model_version': MODEL_VERSION,
            }
        )
    except Exception as exc:
        status['error'] = str(exc)
    return status


def runtime_status(timeout=2):
    backend = active_backend()
    return {
        'backend': backend,
        'live_enabled': backend == 'ollama',
        'cloud': {
            'enabled': False,
            'reason': 'disabled_for_local_only_runtime',
        },
        'ollama': ollama_status(timeout=timeout),
        'pytorch': pytorch_status(),
        'fallback': 'rule_based',
    }


def call_live(messages, system, *, mode=None, **kwargs):
    backend = active_backend()
    if backend == 'ollama':
        result = call_ollama(messages, system, mode=mode, **kwargs)
    else:
        raise AINotConfiguredError()

    usage = result.setdefault('usage', {})
    if isinstance(usage, dict):
        usage.setdefault('backend', backend)
    result.setdefault('backend', backend)
    return result
