"""Скрабинг чувствительных данных в логах (PII/секреты).

Logging-фильтр, который маскирует API-ключи, Bearer/CSRF-токены, пароли и email
в сообщениях логов — чтобы секреты и персональные данные не утекали в лог-файлы
(GDPR + не светить API-ключи в трейсбеках). Подключается к console-handler'у
в settings.LOGGING.
"""

from __future__ import annotations

import logging
import re

_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'sk-[A-Za-z0-9._\-]{8,}'), 'sk-***'),  # hosted-LLM style keys
    (re.compile(r'(Bearer\s+)[A-Za-z0-9._\-]{6,}', re.IGNORECASE), r'\1***'),
    (re.compile(r'(api[_-]?key["\']?\s*[:=]\s*["\']?)[A-Za-z0-9._\-]{6,}', re.IGNORECASE), r'\1***'),
    (re.compile(r'(password["\']?\s*[:=]\s*["\']?)\S+', re.IGNORECASE), r'\1***'),
    (re.compile(r'(token["\']?\s*[:=]\s*["\']?)[A-Za-z0-9._\-]{6,}', re.IGNORECASE), r'\1***'),
    (re.compile(r'csrftoken=[^;\s]+'), 'csrftoken=***'),
    (re.compile(r'[\w.+\-]+@[\w\-]+\.[\w.\-]+'), '***@***'),  # email
]


def scrub(text: str) -> str:
    """Маскирует чувствительные подстроки. Возвращает строку с `***`."""
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


class SensitiveDataFilter(logging.Filter):
    """Logging-фильтр: скрабит record.msg и строковые args. Всегда пропускает запись."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = scrub(record.msg)
            if isinstance(record.args, tuple):
                record.args = tuple(scrub(a) if isinstance(a, str) else a for a in record.args)
            elif isinstance(record.args, dict):
                record.args = {k: scrub(v) if isinstance(v, str) else v for k, v in record.args.items()}
        except Exception:
            # Логирование никогда не должно падать из-за скрабинга.
            pass
        return True
