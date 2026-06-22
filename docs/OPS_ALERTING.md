# Ops-алерты: ошибки и безопасность в отдельный канал (не в чат)

Best-practice: критические ошибки и события безопасности (брутфорс, подозрительная активность)
доставляются автоматически в **отдельный ops-канал**, изолированный от пользовательского чата.

## Два слоя

| Слой | Что ловит | Чем |
|---|---|---|
| **Ошибки приложения** | необработанные исключения, 500-е | **Sentry** (sentry-sdk уже в зависимостях) |
| **Безопасность + критич. ошибки** | брутфорс-локаут (axes), 500-е, custom security-события | `notify_ops()` → webhook / email |

## Модуль `Dolg_APP/services/ops_alerts.py`

`notify_ops(title, message, *, level, kind, meta)` — единый нотификатор. Доставка по приоритету:

1. **Webhook** `OPS_ALERT_WEBHOOK_URL` — авто-формат по хосту: Slack (`hooks.slack.com`),
   Discord (`discord.com`), Telegram (`api.telegram.org` + `OPS_ALERT_TELEGRAM_CHAT_ID`), иначе generic JSON.
2. **Email** на `ADMINS` (через текущий `EMAIL_BACKEND`), если webhook не задан.
3. **Лог** `dolg.ops` (dev / канал не настроен).

Свойства: троттлинг по `(kind, title)` (`OPS_ALERT_THROTTLE_SEC`, дефолт 300с — не спамить),
фильтр по уровню (`OPS_ALERT_MIN_LEVEL`, дефолт `warning`), **никогда не бросает** (сбой алертинга
не роняет приложение). Stdlib (`urllib`), без новых зависимостей.

## Что уже подключено

- **Брутфорс-локаут** django-axes → `notify_ops` (сигнал `user_locked_out` в `accounts/signals.py`).
- **LOGGING-мост**: handler `OpsAlertLogHandler` на логгерах `dolg.security` (WARNING+) и
  `django.request` (ERROR / 500-е — только если канал настроен). Любой код может слать:
  `logging.getLogger('dolg.security').warning('...')` → уйдёт в ops-канал.

## Включение (одна из опций)

```bash
# Вариант 1 — webhook (рекомендуется, проще всего; работает Slack/Discord/Telegram):
setx OPS_ALERT_WEBHOOK_URL "https://hooks.slack.com/services/XXX/YYY/ZZZ"
#   Telegram: OPS_ALERT_WEBHOOK_URL=https://api.telegram.org/bot<TOKEN>/sendMessage
#             OPS_ALERT_TELEGRAM_CHAT_ID=<chat_id>

# Вариант 2 — email админам:
setx DJANGO_ADMINS "Admin <ops@dolg.local>"
setx EMAIL_BACKEND "django.core.mail.backends.smtp.EmailBackend"   # + SMTP-настройки

# Ошибки приложения — Sentry (отдельно, свои алерты в UI Sentry):
setx SENTRY_DSN "https://...@oXXXX.ingest.sentry.io/XXXX"

# Тонкая настройка:
setx OPS_ALERT_MIN_LEVEL "warning"     # info|warning|error|critical
setx OPS_ALERT_THROTTLE_SEC "300"
```

Без переменных всё работает «вхолостую»: алерты идут в лог `dolg.ops`, приложение не падает.

## Проверка

```python
from Dolg_APP.services.ops_alerts import notify_ops
notify_ops('Тест', 'проверка канала', level='warning', kind='security', meta={'ip': '1.2.3.4'})
```

Проверено (2026-06-22): форматы Slack/Discord/Telegram/generic, троттлинг, фильтр уровня,
лог-фолбэк, `manage.py check` — 0 issues.
