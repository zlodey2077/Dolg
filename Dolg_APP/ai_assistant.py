"""
AI-ассистент DOLG: три специализированных «агента» поверх Claude API.

Каждый режим — это отдельный профиль с собственной персоной, моделью,
температурой и системным промптом. Идея: модель, заточенная под одну задачу,
даёт более полезный ответ, чем универсальный prompt:

- recommend → инженер-схемотехник: подбирает компоненты под расчёт
- explain   → schematic-reviewer: разбирает схему, ищет ошибки
- replace   → supply-chain-эксперт: подбирает замену EOL по корпусу/pin-out

Без ANTHROPIC_API_KEY модуль остаётся в demo-режиме: UI работает, endpoint
возвращает понятное сообщение, что ключ не настроен.
"""

import hashlib
import json
import logging
import os

import requests
from django.conf import settings
from django.core.cache import cache

from shop.models import Product

logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
# 2024-10-22 — стабильная версия API на момент сборки. Включает prompt
# caching (cache_control) без beta-флага, files API, computer-use.
ANTHROPIC_VERSION = "2024-10-22"
TIMEOUT_SEC = 30

# Бюджет JSON-snapshot, передаваемого в system prompt: больше токенов = дороже,
# меньше = модель не видит достаточно вариантов. 6000 символов ≈ 1.5к токенов.
CATALOG_BYTES_BUDGET = 6000
SCHEME_BYTES_BUDGET = 4000

# Минимальный размер system-блока для prompt caching на haiku-4-5: 1024 токена.
# Кириллица в Anthropic-токенайзере — ≈ 0.4 токена/символ, поэтому 4500 chars ≈
# 1800 токенов — гарантированно выше порога даже на коротких CATALOG-snapshot-ах.
# Раньше стояло 3000 — было borderline (~1200 токенов), иногда не попадало.
PROMPT_CACHE_MIN_CHARS = 4500


# --- Доменные исключения для понятных HTTP-маппингов в view ----------------

class AIError(Exception):
    """Базовое исключение модуля. http_status — что вернуть пользователю."""
    http_status = 502
    user_message = "AI временно недоступен."


class AINotConfiguredError(AIError):
    http_status = 503
    user_message = "AI-ассистент не настроен (ANTHROPIC_API_KEY)."


class AIAuthError(AIError):
    http_status = 502
    user_message = "Ключ Anthropic недействителен. Свяжитесь с администратором."


class AIRateLimitError(AIError):
    http_status = 429
    user_message = "Anthropic временно лимитирует запросы. Подождите 30 секунд."


class AINetworkError(AIError):
    http_status = 504
    user_message = "Сеть недоступна или Claude API не отвечает."


class AIServerError(AIError):
    http_status = 502
    user_message = "Anthropic вернул ошибку сервера. Попробуйте ещё раз."


def _api_key():
    return os.getenv("ANTHROPIC_API_KEY") or getattr(settings, "ANTHROPIC_API_KEY", "")


def is_enabled():
    return bool(_api_key())


def _product_to_dict(p):
    return {
        "name": p.name,
        "pn": p.part_number or p.slug,
        "cat": p.category.slug if p.category_id else None,
        "mfr": p.manufacturer,
        "price": float(p.price) if p.price is not None else None,
        "stock": p.stock,
        "lifecycle": p.lifecycle_status,
        "package": p.package_type or "",
        "params": p.parameters or {},
    }


CATALOG_CACHE_TTL_SEC = 60  # короткий TTL — каталог меняется редко, но
# не хочется кешировать stale-цены или новые товары на полчаса.


def _catalog_cache_key(category_slugs, lifecycle_in, exclude_pn, limit):
    payload = json.dumps({
        "c": sorted(category_slugs) if category_slugs else None,
        "l": sorted(lifecycle_in) if lifecycle_in else None,
        "x": (exclude_pn or "").lower(),
        "n": int(limit),
    }, ensure_ascii=False)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"dolg:catalog_snapshot:{digest}"


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

    qs = Product.objects.select_related("category").all()
    if category_slugs:
        qs = qs.filter(category__slug__in=list(category_slugs))
    if lifecycle_in:
        qs = qs.filter(lifecycle_status__in=list(lifecycle_in))
    if exclude_pn:
        qs = qs.exclude(part_number__iexact=exclude_pn)
    qs = qs.filter(stock__gt=0).order_by("-stock", "price")[:limit]
    snapshot = [_product_to_dict(p) for p in qs]
    cache.set(key, snapshot, CATALOG_CACHE_TTL_SEC)
    return snapshot


# --- Профили агентов ----------------------------------------------------
#
# Каждый профиль — самодостаточная конфигурация Claude API:
#   model      — конкретная модель (haiku для скорости, sonnet для глубины)
#   temperature — креативность (низкая для технических задач)
#   max_tokens — размер ответа
#   persona    — кто отвечает (формирует тон)
#   guidelines — что и как делать
#   output_hint — структура ответа (модель чаще её соблюдает)

AGENT_PROFILES = {
    "recommend": {
        "title": "Инженер-схемотехник",
        "model": "claude-haiku-4-5-20251001",
        "temperature": 0.3,
        "max_tokens": 1024,
        "persona": (
            "Ты — опытный инженер-схемотехник. Подбираешь компоненты из "
            "доступного каталога DOLG под конкретную задачу пользователя."
        ),
        "guidelines": (
            "1) Выбирай компоненты ТОЛЬКО из CATALOG (не выдумывай part_number).\n"
            "2) Расчёт обязателен: закон Ома, формула делителя, RC-постоянная и т.п.\n"
            "3) Указывай номиналы по E12-ряду, если каталог даёт выбор.\n"
            "4) Учитывай лимит мощности: P=V²/R для R, проверяй TDP.\n"
            "5) Если задача неоднозначна — задай 1-2 уточняющих вопроса."
        ),
        "output_hint": (
            "Структура ответа:\n"
            "**Расчёт:** короткая выкладка с формулой и числами.\n"
            "**Компоненты:**\n"
            "- R1 = 10 кОм (PN-12345, 0.25 Вт, 5%)\n"
            "- C1 = 100 нФ (PN-67890)\n"
            "**Что получится:** одна строка о результате."
        ),
    },
    "explain": {
        "title": "Schematic reviewer",
        "model": "claude-haiku-4-5-20251001",
        "temperature": 0.2,
        "max_tokens": 1200,
        "persona": (
            "Ты — schematic-reviewer: разбираешь принципиальную схему и "
            "ищешь конкретные ошибки. Не философствуешь, а указываешь пальцем."
        ),
        "guidelines": (
            "1) Сначала — ОДНА строка о назначении схемы (что она делает).\n"
            "2) Потом 2-3 ключевых узла с расчётом (V, I).\n"
            "3) Затем — список потенциальных ошибок с точным id компонента:\n"
            "   - отсутствует GND\n"
            "   - короткое замыкание (узел X)\n"
            "   - превышение TDP резистора Rn\n"
            "   - LED без токоограничителя\n"
            "   - плавающий вход транзистора\n"
            "4) Если ошибок нет — прямо скажи 'критичных проблем нет'."
        ),
        "output_hint": (
            "Структура:\n"
            "**Назначение:** одна строка.\n"
            "**Ключевые узлы:** N1 = ... В, ток через R1 = ... мА.\n"
            "**Проблемы:** список или 'критичных проблем нет'.\n"
            "**Что улучшить:** 1-2 пункта (опционально)."
        ),
    },
    "replace": {
        "title": "Supply-chain-эксперт",
        "model": "claude-haiku-4-5-20251001",
        "temperature": 0.2,
        "max_tokens": 900,
        "persona": (
            "Ты — supply-chain-эксперт по замене EOL/устаревших компонентов. "
            "Главное — совместимость по корпусу, pin-out и ключевым параметрам."
        ),
        "guidelines": (
            "1) Подбирай 1-3 замены ТОЛЬКО из CATALOG (lifecycle=active/nrnd).\n"
            "2) Сравнение по: package_type, ключевым параметрам, температуре.\n"
            "3) Обязательно отметь РИСКИ замены: отличия pin-out, корпуса, рейтингов.\n"
            "4) Если pin-out отличается — пометь это как 'требует переразводки PCB'.\n"
            "5) Если в CATALOG нет адекватной замены — скажи прямо."
        ),
        "output_hint": (
            "Структура:\n"
            "**Целевой компонент:** PN из запроса + что это.\n"
            "**Замены:**\n"
            "1. PN-1 — package, ключевые отличия, риск (низкий/средний/высокий).\n"
            "2. PN-2 — ...\n"
            "**Рекомендация:** какой выбрать и почему."
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

    Если стабильный блок короче PROMPT_CACHE_MIN_CHARS — cache_control
    не выставляется (Anthropic всё равно не закеширует, а лишний флаг
    усложняет диагностику usage).
    """
    profile = AGENT_PROFILES.get(mode) or AGENT_PROFILES["recommend"]
    catalog_json = json.dumps(catalog, ensure_ascii=False, default=str)[:CATALOG_BYTES_BUDGET]
    stable_text = "\n".join([
        profile["persona"],
        "\nОтвечай на русском, кратко (до трёх абзацев), по делу. "
        "Если данных мало — открыто скажи об этом, не выдумывай.",
        "\nПравила:\n" + profile["guidelines"],
        "\n" + profile["output_hint"],
        f"\nCATALOG ({len(catalog)} позиций, JSON):\n{catalog_json}",
    ])
    blocks = [{"type": "text", "text": stable_text}]
    if len(stable_text) >= PROMPT_CACHE_MIN_CHARS:
        blocks[0]["cache_control"] = {"type": "ephemeral"}

    volatile_parts = []
    if mode == "explain" and scheme is not None:
        scheme_json = json.dumps(scheme, ensure_ascii=False, default=str)[:SCHEME_BYTES_BUDGET]
        volatile_parts.append(f"SCHEME (текущая схема пользователя):\n{scheme_json}")
    elif mode == "replace":
        volatile_parts.append(f"Целевой компонент для замены: {target_pn or '(не указан)'}")
    if volatile_parts:
        blocks.append({"type": "text", "text": "\n".join(volatile_parts)})

    return blocks


def build_system_prompt(mode, catalog, scheme=None, target_pn=None):
    """Backwards-compat: плоский текст system-prompt-а (для тестов и логов)."""
    blocks = build_system_blocks(mode, catalog, scheme=scheme, target_pn=target_pn)
    return "\n".join(b["text"] for b in blocks)


# Маппинг HTTP-кода Anthropic → исключение домена. Сделано таблицей, чтобы
# легко расширять (например, отдельный код 529 «overloaded»).
_ANTHROPIC_STATUS_TO_EXC = {
    400: AIError,           # bad request — наша вина
    401: AIAuthError,
    403: AIAuthError,
    404: AIError,
    429: AIRateLimitError,
}


def call_claude(messages, system, *, mode=None, model=None, max_tokens=None,
                temperature=None, timeout=TIMEOUT_SEC, use_cache=True):
    """Вызов Anthropic Messages API. Если задан mode — параметры берутся из
    AGENT_PROFILES[mode]; явно переданные model/max_tokens/temperature их
    переопределяют (для тестов).

    Параметр system принимается и как str (плоский текст), и как list
    блоков {type, text, cache_control?}. Если строка и use_cache=True и
    длиннее PROMPT_CACHE_MIN_CHARS — оборачиваем в один cached-блок.
    """
    api_key = _api_key()
    if not api_key:
        raise AINotConfiguredError("ANTHROPIC_API_KEY не задан")

    profile = AGENT_PROFILES.get(mode) if mode else None
    payload = {
        "model": model or (profile["model"] if profile else "claude-haiku-4-5-20251001"),
        "max_tokens": max_tokens or (profile["max_tokens"] if profile else 1024),
        "messages": messages,
    }
    if isinstance(system, list):
        payload["system"] = system
    elif use_cache and isinstance(system, str) and len(system) >= PROMPT_CACHE_MIN_CHARS:
        payload["system"] = [{"type": "text", "text": system,
                              "cache_control": {"type": "ephemeral"}}]
    else:
        payload["system"] = system

    temp = temperature if temperature is not None else (profile["temperature"] if profile else None)
    if temp is not None:
        payload["temperature"] = temp

    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    try:
        r = requests.post(ANTHROPIC_URL, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        logger.warning("Claude API request error: %s", exc)
        raise AINetworkError(str(exc)) from exc

    if r.status_code != 200:
        logger.warning("Claude API %s: %s", r.status_code, r.text[:300])
        exc_cls = _ANTHROPIC_STATUS_TO_EXC.get(r.status_code, AIServerError)
        raise exc_cls(f"Claude API вернул {r.status_code}")

    data = r.json()
    text_chunks = []
    for block in data.get("content", []):
        if block.get("type") == "text":
            text_chunks.append(block.get("text", ""))
    return {
        "text": "".join(text_chunks).strip() or "(пустой ответ)",
        "stop_reason": data.get("stop_reason"),
        "usage": data.get("usage", {}),
        "model": payload["model"],
        "agent": profile["title"] if profile else None,
    }
