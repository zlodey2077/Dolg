"""Отдельный канал ops-алертов: ошибки и события безопасности — НЕ в пользовательский чат.

Best practice: ошибки приложения ловит Sentry (если задан SENTRY_DSN — см. settings). Этот модуль —
единый channel-agnostic нотификатор для событий безопасности (брутфорс-локаут axes, подозрительная
активность) и критических ошибок, с доставкой в отдельный ops-канал и троттлингом (не спамить).

Приоритет доставки (по наличию настроек):
  1) Webhook `OPS_ALERT_WEBHOOK_URL` — авто-формат по хосту: Slack / Discord / Telegram / generic JSON.
  2) Иначе email на `ADMINS` (через текущий EMAIL_BACKEND).
  3) Иначе — в лог `dolg.ops` (dev / не настроено).

Гарантия: notify_ops() никогда не бросает — сбой алертинга не должен ронять приложение.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.request

from django.conf import settings

logger = logging.getLogger('dolg.ops')

# Простой in-process троттл: {ключ: ts последней отправки}. Для многопроцессного прода можно
# заменить на cache, но для отсечки спама одинаковыми алертами этого достаточно.
_last_sent: dict[str, float] = {}

_LEVELS = {'info': 20, 'warning': 30, 'error': 40, 'critical': 50}


def _throttle_window() -> int:
    return int(getattr(settings, 'OPS_ALERT_THROTTLE_SEC', 300) or 0)


def _should_send(key: str) -> bool:
    win = _throttle_window()
    if win <= 0:
        return True
    now = time.time()
    last = _last_sent.get(key, 0)
    if now - last < win:
        return False
    _last_sent[key] = now
    # подчищаем старые ключи, чтобы словарь не рос бесконечно
    if len(_last_sent) > 256:
        cutoff = now - win
        for k in [k for k, ts in _last_sent.items() if ts < cutoff]:
            _last_sent.pop(k, None)
    return True


def _format_text(title: str, message: str, level: str, kind: str, meta: dict | None) -> str:
    env = getattr(settings, 'SENTRY_ENVIRONMENT', '') or (
        'dev' if getattr(settings, 'DEBUG', False) else 'prod'
    )
    icon = {'security': '🛡', 'error': '🔥', 'log': '📋'}.get(kind, '🔔')
    lines = [f'{icon} [{level.upper()}] DOLG/{env}: {title}', message]
    if meta:
        for k, v in meta.items():
            lines.append(f'• {k}: {v}')
    return '\n'.join(str(line) for line in lines if line)


def _webhook_payload(url: str, text: str) -> dict:
    host = url.lower()
    if 'hooks.slack.com' in host:
        return {'text': text}
    if 'discord.com' in host or 'discordapp.com' in host:
        return {'content': text[:1900]}
    if 'api.telegram.org' in host:
        chat_id = getattr(settings, 'OPS_ALERT_TELEGRAM_CHAT_ID', '')
        return {'chat_id': chat_id, 'text': text, 'disable_web_page_preview': True}
    return {'text': text, 'message': text}


def _deliver_webhook(url: str, text: str) -> bool:
    payload = json.dumps(_webhook_payload(url, text)).encode('utf-8')
    req = urllib.request.Request(
        url, data=payload, headers={'Content-Type': 'application/json'}, method='POST'
    )
    with urllib.request.urlopen(req, timeout=5):
        return True


def _deliver_email(title: str, text: str) -> bool:
    if not getattr(settings, 'ADMINS', None):
        return False
    from django.core.mail import mail_admins

    mail_admins(subject=f'[DOLG ops] {title}'[:180], message=text, fail_silently=True)
    return True


def notify_ops(
    title: str,
    message: str = '',
    *,
    level: str = 'error',
    kind: str = 'security',
    meta: dict | None = None,
    from_log: bool = False,
) -> bool:
    """Отправить ops-алерт в отдельный канал. Возвращает True, если доставлено (или залогировано).

    level: info|warning|error|critical. kind: security|error|log (влияет на иконку/маршрут).
    Троттлится по (kind, title). Никогда не бросает исключение.
    """
    try:
        min_level = _LEVELS.get(getattr(settings, 'OPS_ALERT_MIN_LEVEL', 'warning'), 30)
        if _LEVELS.get(level, 40) < min_level:
            return False

        key = hashlib.sha1(f'{kind}|{title}'.encode()).hexdigest()
        if not _should_send(key):
            return False

        text = _format_text(title, message, level, kind, meta)
        url = getattr(settings, 'OPS_ALERT_WEBHOOK_URL', '') or ''

        if url:
            try:
                _deliver_webhook(url, text)
                return True
            except Exception:
                logger.warning('ops-alert webhook не доставлен, пробую email/лог', exc_info=True)

        if _deliver_email(title, text):
            return True

        # Фолбэк: лог в 'dolg.ops' (НЕ в 'dolg.security' — иначе рекурсия через log-handler).
        logger.log(_LEVELS.get(level, 40), 'OPS-ALERT %s', text)
        return True
    except Exception:  # алертинг не должен ронять приложение
        try:
            logger.exception('notify_ops провалился')
        except Exception:
            pass
        return False


class OpsAlertLogHandler(logging.Handler):
    """LOGGING-handler: пробрасывает ERROR+ записи (напр. 'django.request', 'dolg.security')
    в notify_ops. from_log=True гасит лог-фолбэк, чтобы не зациклиться."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = record.levelname.lower()
            notify_ops(
                title=f'{record.name}: {record.getMessage()[:120]}',
                message=record.getMessage(),
                level=level if level in _LEVELS else 'error',
                kind='error',
                from_log=True,
            )
        except Exception:
            pass
