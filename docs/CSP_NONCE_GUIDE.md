# CSP nonce для новых страниц — короткий гайд

После H9 (`160d4cc` security backlog) DOLG поддерживает CSP nonce для
inline-скриптов и стилей. На новых страницах используем nonce, на
старых пока живёт `'unsafe-inline'`.

## Как использовать

### 1. Inline `<script>` в шаблоне

```django
{% load static %}
<!DOCTYPE html>
<html>
<head>
    <script nonce="{{ request.csp_nonce }}">
        // Этот скрипт допустим, потому что nonce совпадает с одним из
        // CSP nonce'ов в Content-Security-Policy header'е этого ответа.
        console.log('hello from nonce-protected inline');
    </script>
</head>
<body>
    ...
</body>
</html>
```

### 2. Inline `<style>` в шаблоне

```django
<style nonce="{{ request.csp_nonce }}">
    .cool-class { color: cyan; }
</style>
```

### 3. Внешние `<script src>` и `<link rel="stylesheet">`

Не требуют nonce — для них работают `'self'` и whitelisted CDN'ы из
`Dolg_PR/settings.py` (`CSP_SCRIPT_SRC`, `CSP_STYLE_SRC`).

## Что НЕ делать

- ❌ Хардкодить nonce в строке — он меняется на каждый запрос.
- ❌ Использовать `<script>...</script>` без nonce, если хочешь когда-
  нибудь убрать `'unsafe-inline'`.
- ❌ Inline event-handlers: `<button onclick="...">` — CSP их не пускает
  даже с nonce. Используй `addEventListener` в nonce-script.

## Миграция старых шаблонов (post-defense)

`simulation.html` имеет 15k+ строк inline-JS — миграция = задача
[[project-security-backlog]] § 1.3, ~1-2 дня:
1. Вытащить JS в `shop/static/simulation/scheme-*.js` (см. Phase 5 в
   `project_admin_cache_bust` бэклоге — там же лежит план split'а).
2. После того как **все** inline-блоки → внешние файлы или нонсированы,
   убрать `'unsafe-inline'` из `CSP_SCRIPT_SRC` в settings.py.
3. Аналогично для `'unsafe-inline'` в `CSP_STYLE_SRC` (там inline-стили
   меньше, можно за полдня).

## Тестирование

После правки шаблона — открыть DevTools → Console. Если nonce не
совпадает, увидишь:

```text
Refused to execute inline script because it violates the following
Content Security Policy directive: "script-src 'self' 'unsafe-inline'
'nonce-XXXXX' cdn.jsdelivr.net ...". Either the 'unsafe-inline'
keyword, a hash ('sha256-...') or a nonce ('nonce-XXXXX') is required
to enable inline execution.
```

Если видишь такое — добавь `nonce="{{ request.csp_nonce }}"` на тег.

## Связано

- `Dolg_PR/settings.py:226-239` — CSP конфиг
- `docs/SECURITY_BACKLOG.md` § 1.3 — финальная цель убрать 'unsafe-inline'
- `docs/GITHUB_SECURITY_SETUP.md` — общие GitHub-security рекомендации
