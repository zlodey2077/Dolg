# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in DOLG, please report it
**privately** (do not open a public GitHub issue).

- **Contact:** rampage.ninja.dev@gmail.com
- **Subject prefix:** `[DOLG security]`
- **PGP/Signal/etc.** — на запрос.

Опишите:
- что нашли, где (файл/URL/команда),
- как воспроизвести (минимальный PoC),
- ожидаемое и реальное поведение,
- impact (data leak / RCE / DoS / privilege escalation),
- ваш ник для credit (по желанию).

## Disclosure timeline

- **24-72 ч** — подтверждение приёма
- **7 дней** — первичная оценка severity и план
- **30 дней** — патч в `main` для high/critical
- **90 дней** — публичное раскрытие (или раньше по согласованию)

## Scope

In-scope:
- Этот репозиторий (`zlodey2077/Dolg`)
- Endpoints на работающем демо-инстансе

Out-of-scope:
- Самостоятельно установленные форки/деплои
- Social engineering / физическая безопасность хостинга
- DoS через объём (rate-limit является механикой защиты, не уязвимостью)
- Self-XSS, без user interaction

## Supported versions

Поддерживается только `main`. Старые теги — без обновлений безопасности.

## Hall of fame

Если ваш репорт привёл к патчу — добавим вас сюда (по желанию):
- _пока пусто_
