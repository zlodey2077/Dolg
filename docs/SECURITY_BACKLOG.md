# DOLG Security Backlog — paranoid edition

Параноидальный аудит проекта по 12 категориям. Для каждой категории —
что сделано (✅), что частично (🟡), что отсутствует (❌), приоритет
и оценка времени. Сортировка внутри каждой секции — по реальному риску
и сложности фикса.

Легенда:
- ⛔ **CRITICAL** — закрыть до публичного запуска / до защиты при наличии демки;
- 🔥 **HIGH** — реальный риск, исправить как можно скорее;
- 🟧 **MEDIUM** — желательно, но не блокирует;
- 🟢 **LOW** — гигиена, можно отложить;
- 📚 **NICE-TO-HAVE** — post-defense / production-ready полировка.

---

## Статус HIGH-tier на 2026-06-21 (проверено по коду)

8 из 9 рекомендованных до защиты HIGH-пунктов закрыты и подтверждены в коде.
Исключение: CSP/inline-JS остаётся частично закрытым, потому что текущий
`Dolg_PR/settings.py` всё ещё вынужден разрешать `'unsafe-inline'` для
тяжёлых рабочих страниц симулятора.

| HIGH | Статус | Подтверждение |
|---|---|---|
| H1 Permission audit (2.12, 2.13) | ✅ | `@staff_member_required` на всех вьюхах `Dolg_APP/ml_admin_views.py`; `@login_required` + owner-scoping на project/API |
| H2 IDOR / org isolation (1.7, 4.9, 11.7) | ✅ | `_project_for_read` / `_project_for_write` / `_review_for_read` в `Dolg_APP/views.py`; org-вьюхи через `user_can()` RBAC |
| H3 Stripe webhook signature (11.5) | ✅ | `orders/payment_views.py:stripe_webhook` + `Dolg_APP/views.py:billing_stripe_webhook` — `construct_event` + `SignatureVerificationError` |
| H4 bandit + gitleaks + pip-audit pre-commit (9.2-9.4) | ✅ | commit `fd452b0` |
| H5 gitleaks history scan + rotate (3.3) | ✅ | скан 2026-06-06 через `.gitleaks.toml` → **no leaks found**, ротировать нечего |
| H6 SSRF guard (1.5) | ✅ | commit `1629e95` |
| H7 AI prompt injection (11.1) | ✅ | commit `fa0ee38` |
| H8 SPICE/formula eval sandbox (11.2) | ✅ | commit `a73f7df` (sympify sandbox) |
| H9 CSP nonce для inline-JS (1.3) | 🟡 | `Dolg_PR/settings.py:252-273` включает CSP только opt-in и оставляет `'unsafe-inline'`; нужна дальнейшая декомпозиция `simulation.html` |

Следующий уровень риска — MEDIUM (rate limits на `/api/ai/chat/` и `/cad/api/import/`, GDPR cascade delete, log scrubbing, JSON body-size limit, file-upload MIME/size, open-redirect `next=`). Не блокирует защиту.

### Update 2026-06-21 - password/token limits hardening

- Passwords are stored through Django hashers, not as plaintext. Runtime hashers are `pbkdf2_sha256` first, with compatibility for `pbkdf2_sha1`, `argon2`, `bcrypt_sha256` and `scrypt`; tests may override to MD5 only under `IS_TESTING`.
- Registration already validates passwords through `AUTH_PASSWORD_VALIDATORS` before `User.objects.create_user(...)`.
- Login brute-force protection is now two-layered: the old session counter remains for UX, and a cache-backed username+IP lockout prevents a fresh cookie/session from bypassing repeated failed attempts.
- Organization API tokens remain one-time-display and SHA-256 hashed; creation now enforces an active-token cap and an allowlist of scopes server-side.
- Remaining token/limit work: body-size guards for heavy JSON endpoints, stronger per-IP/per-user throttles for AI/CAD import, upload content sniffing/quarantine, and incident alerts for suspicious login/token/admin activity.

---

## Доклад 2026-06-21: комплексная защита данных от целевых атак

### Executive summary

DOLG уже не выглядит как проект "только с токенами": в коде есть рабочие
слои защиты для сессий, CSRF, продовых cookie-флагов, Stripe webhook
signatures, SSRF-guard, audit log, hashed organization API tokens, RBAC/org
permissions и безопасный async-контур для server engines. Это хорошая база для
защиты перед комиссией.

Главный вывод: против целевого атакующего надо защищать не один endpoint, а
цепочку. Реалистичная атака будет идти через credential stuffing -> захват
админской/организационной роли -> IDOR/tenant escape -> выгрузку БД/media/logs
или через supply-chain/worker/parser -> RCE/SSRF -> lateral movement в будущих
Docker/Kubernetes сервисах. Поэтому следующий уровень защиты — это
defense-in-depth: строгий CSP, hardened uploads, лимиты тела/частоты запросов,
централизованный audit/alerting, supply-chain checks, sandbox для движков,
PostgreSQL backup/encryption policy и incident runbook.

Каркас контроля: OWASP ASVS 5.0 для проверяемых требований к приложению,
OWASP Top 10/Cheat Sheets для типовых web/appsec атак, NIST CSF 2.0 для цикла
Govern/Identify/Protect/Detect/Respond/Recover.

### Активы и границы доверия

Активы:

- Пользовательские аккаунты, session cookies, 2FA state, SSO-связки.
- Проекты схем, BOM, PCB/3D artifacts, симуляции, `EngineJob` payload/result.
- Заказы, платежи, Stripe customer/subscription/payment identifiers.
- Organization API tokens, `METRICS_TOKEN`, Stripe keys/webhook secrets,
  AI/provider tokens, future Docker/K8s secrets.
- БД SQLite/PostgreSQL, media/uploads, backups, logs, CI/CD artifacts.
- Админка, Data Console, ML/admin tools, management commands.

Границы доверия:

- Browser -> Django: формы, fetch API, CSRF, session auth.
- Django -> DB/media/cache/logs: ORM, FileField/ImageField, audit trails.
- Django -> Stripe: webhook signature вместо CSRF.
- Django -> outbound HTTP: SSRF-sensitive imports/downloads.
- Django -> EngineJob workers: сейчас local worker, позже Docker/K8s workers.
- GitHub/CI -> deploy/runtime: dependencies, secrets, workflow permissions.

### Что уже есть в коде

- Production baseline частично fail-closed: `SECRET_KEY` и `ALLOWED_HOSTS`
  проверяются при `DEBUG=False` (`Dolg_PR/settings.py:51-87`).
- CSRF middleware включён (`Dolg_PR/settings.py:198-210`); AJAX-сценарии
  осознанно читают CSRF cookie из JS (`Dolg_PR/settings.py:623-647`).
- Secure cookie/header baseline для prod: `SESSION_COOKIE_SECURE`,
  `CSRF_COOKIE_SECURE`, SSL redirect, HSTS, `X_FRAME_OPTIONS='DENY'`,
  nosniff/referrer/COOP (`Dolg_PR/settings.py:622-656`).
- Optional brute-force/CSP middleware подключаются через env-флаги
  (`Dolg_PR/settings.py:163-185`, `Dolg_PR/settings.py:241-273`).
- Stripe webhook заменяет CSRF подписью Stripe и reject'ит отсутствующую
  signature (`orders/payment_views.py:158-190`).
- SSRF guard разрешает только HTTPS, запрещает private/link-local/metadata IP,
  ограничивает порты, redirects, timeout и размер ответа
  (`Dolg_APP/services/ssrf_guard.py:31-145`).
- Organization API tokens генерируются случайно, хранятся хешем и сравниваются
  через `hmac.compare_digest` (`Dolg_APP/models.py:448-475`).
- Audit trail уже есть для org actions и project events
  (`Dolg_APP/models.py:341-388`, `Dolg_APP/models.py:927-952`).
- EngineJob API ограничивает видимость owner/staff scope и пишет job audit
  (`Dolg_APP/views.py:2760-2845`).
- Data Console использует DB introspection и quoting table names для read-only
  подсчётов, а не raw user SQL (`Dolg_APP/ml_admin_views.py:360-384`).

### Findings

**DA-01. High - CSP пока не защищает от полноценного XSS-сценария.**

Impact: при найденном DOM/template XSS атакующий сможет читать действия
пользователя в той же сессии, запускать state-changing fetch и атаковать
админские/проектные API.

Evidence: CSP middleware включается только при `ENABLE_CSP`, а `script-src`
оставляет `'unsafe-inline'` из-за тяжёлого `simulation.html`
(`Dolg_PR/settings.py:252-273`). `server-engine-ui.js` ещё генерирует HTML с
inline `onclick` handlers (`shop/static/simulation/server-engine-ui.js:121-161`).

Fix: продолжать вынос inline JS из `simulation.html`/CAD в внешние файлы,
переводить inline handlers на `addEventListener`, затем включить nonce/hash CSP
без `'unsafe-inline'`. Для защиты: сначала Report-Only на staging, затем enforce.

False positive notes: текущий риск частично снижен Django autoescape и ручным
escaping в `server-engine-ui.js`, но CSP как второй слой сейчас слабый.

**DA-02. High - upload pipeline проверяет размер и browser MIME, но не делает
полный content-sniff/quarantine.**

Impact: вредный файл под видом изображения/материала может стать stored XSS,
malware carrier, decompression bomb или атакой на будущие PDF/Gerber/worker
парсеры.

Evidence: avatar/logo checks используют `avatar.content_type`/`logo.content_type`
и size limit (`accounts/views.py:360-400`). В проекте есть несколько
`ImageField`/`FileField` (`accounts/models.py:78`, `accounts/models.py:104`,
`Dolg_APP/models.py:190`, `knowledge/models.py:95`, `shop/models.py:121`).

Fix: единый upload service: extension allowlist + magic-byte sniff + Pillow
`verify()`/re-encode for images + max pixels + quarantine path + malware scan
hook. Media отдавать как attachment там, где файл не должен исполняться в
браузере.

False positive notes: Django storage сам нормализует имена файлов, но это не
заменяет проверку содержимого.

**DA-03. High - admin/Data Console/ML tools являются high-value target и требуют
отдельного режима усиления.**

Impact: компрометация staff-аккаунта даёт обзор БД, jobs, media, модерации,
заказов и ML/admin инструментов; это быстрее всего превращается в data
exfiltration.

Evidence: Data Console читает таблицы/модели/файловые поля
(`Dolg_APP/ml_admin_views.py:344-384`). Brute-force protection через Axes
подключается только при `ENABLE_AXES` (`Dolg_PR/settings.py:163-185`,
`Dolg_PR/settings.py:241-250`).

Fix: для staff/admin включить обязательную 2FA, sudo-mode для опасных действий,
rate-limit на login/admin, IP allowlist/VPN для публичной демки, отдельные audit
events на login/logout/password/2FA/admin actions и alerts на массовый export.

False positive notes: многие views уже закрыты decorators, но целевой атакующий
обычно бьёт не только authorization, а захват роли + тихую выгрузку.

**DA-04. Medium - Stripe demo defaults должны fail-closed в prod/demo-live.**

Impact: если `STRIPE_WEBHOOK_SECRET` случайно останется `demo_mode` при живом
платёжном контуре, webhook endpoint принимает событие без проверки подписи.

Evidence: `STRIPE_WEBHOOK_SECRET` имеет default `demo_mode`
(`Dolg_PR/settings.py:555`), а webhook при demo secret сразу возвращает success
(`orders/payment_views.py:165-167`).

Fix: при `DEBUG=False` и включённом платёжном backend падать на старте, если
Stripe secret/webhook secret равны `demo_mode`; для локального demo оставить
явный `ALLOW_DEMO_PAYMENTS=1`.

False positive notes: сейчас это удобно для локальной защиты/демо, но для
production-like демо лучше отделить "нет Stripe" и "Stripe live".

**DA-05. Medium - reverse-proxy trust нужно закрепить runtime-чеком.**

Impact: если Django окажется напрямую доступен извне, spoofed
`X-Forwarded-Proto`/`X-Forwarded-Host` может исказить `is_secure()` и абсолютные
URL; это влияет на cookies, redirects, email links и CSRF assumptions.

Evidence: `SECURE_PROXY_SSL_HEADER` и `USE_X_FORWARDED_HOST` включены глобально
ради Cloudflare/ngrok (`Dolg_PR/settings.py:648-660`).

Fix: документировать обязательное условие "proxy strips forwarded headers",
добавить env-флаг `TRUST_X_FORWARDED_HOST=1` для prod-like deployments и
health-check, который показывает effective scheme/host только staff.

False positive notes: для Cloudflare Tunnel это практично и нужно; риск появляется
при смене topology.

**DA-06. Medium - future Docker/K8s server engines должны считаться untrusted
compute.**

Impact: внешний Xyce/PySpice/GnuCap/OpenModelica/GNU Radio worker будет парсить
netlist/model/archive от пользователя; это типичная точка RCE, SSRF и lateral
movement к БД/secrets.

Evidence: проект уже имеет `dolg-engine-router` и `EngineJob` result contract,
а `EngineJob` принимает `netlist`, `scheme_data`, `options`
(`Dolg_APP/views.py:2791-2837`).

Fix: запускать engines только в отдельном worker-контуре: read-only image,
non-root user, no host mounts, CPU/RAM/time limits, deny egress by default,
ephemeral FS, signed job/result envelope, artifact allowlist, audit log,
container image scan, K8s NetworkPolicy/PodSecurity.

False positive notes: текущий local router делегирует в NumPy MNA и не запускает
внешний CLI внутри web request, что уже снижает риск.

**DA-07. Medium - security monitoring пока не собран в единый incident loop.**

Impact: даже при хороших контролях атака может пройти незамеченной, если нет
alerts по anomalous login, token use, массовым exports, webhook errors,
EngineJob failures и suspicious admin reads.

Evidence: есть `AuditLog`/`ProjectEvent` и webhook mismatch logging
(`Dolg_APP/models.py:341-388`, `Dolg_APP/models.py:927-952`,
`orders/payment_views.py:183-190`), но нет единого alerting/runbook в этом
документе.

Fix: добавить incident runbook: severity matrix, кто смотрит, где логи, как
отзывать tokens/sessions, как ротировать secrets, как останавливать workers, как
восстанавливать из backup. Минимум alerts: failed login spike, staff login,
new/revoked API token, bulk data access, worker stale/error spike, Stripe
signature mismatch.

False positive notes: для дипломного MVP достаточно документа + минимальных
логов; production потребует Sentry/SIEM/Prometheus alerts.

### P0/P1 план усиления

P0, до публичной демки/защиты:

1. Зафиксировать этот доклад как официальный раздел безопасности и использовать
   его в ответах комиссии.
2. Включить проверку `DEBUG=False` + non-demo `SECRET_KEY`, `ALLOWED_HOSTS`,
   Stripe secrets для production-like запуска.
3. Добавить body-size/rate-limit guard для тяжёлых JSON/API: AI chat, CAD import,
   simulation job submit.
4. Ввести upload service для avatar/logo/materials/products с magic-byte sniff и
   max pixels.
5. Staff/admin hardening: обязательная 2FA, sudo-mode для критичных действий,
   audit events на login/logout/password/2FA/admin.

P1, сразу после:

1. CSP migration: убрать inline handlers, включить nonce/hash CSP без
   `'unsafe-inline'`, добавить Trusted Types backlog для рабочих страниц.
2. Server engine sandbox: Docker/K8s worker profile с NetworkPolicy, limits,
   non-root, artifact allowlist и image scanning.
3. Supply-chain: GitHub CodeQL/Dependabot/secret scanning/push protection,
   `pip-audit`, SBOM, container scan.
4. Postgres protection: отдельный least-privilege DB user, backups, restore drill,
   encryption policy, audit/log retention.
5. Incident runbook + alerts: auth anomalies, token lifecycle, Stripe signature
   mismatch, mass exports, worker failures.

### Что сказать комиссии простыми словами

> В проекте защита построена не одной проверкой, а слоями. Пользовательские
> действия защищены сессиями, CSRF, правами доступа и audit log. Платёжные
> события принимаются только по подписи Stripe. Любые будущие тяжёлые движки
> вынесены в очередь `EngineJob`, чтобы не запускать внешние процессы внутри
> web-запроса. Следующий уровень — изолировать Docker/Kubernetes workers,
> усилить CSP, проверку загрузок, мониторинг и реагирование. То есть проект
> проектируется не только против случайных ошибок, но и против цепочки целевой
> атаки: захват аккаунта, обход прав, вредный файл, SSRF/RCE, выгрузка данных.

### Источники контроля

- OWASP ASVS 5.0: https://owasp.org/www-project-application-security-verification-standard/
- OWASP Cheat Sheet: Content Security Policy:
  https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html
- OWASP Cheat Sheet: File Upload:
  https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
- OWASP Cheat Sheet: SSRF Prevention:
  https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
- NIST Cybersecurity Framework 2.0:
  https://www.nist.gov/cyberframework
- NIST CSF 2.0 PDF:
  https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf

---

## 1. AppSec / OWASP Top 10

| # | Что | Состояние | Прио | Усилие |
|---|---|---|---|---|
| 1.1 | CSRF на всех POST формах | ✅ Django middleware включён, `CSRF_TRUSTED_ORIGINS` сконфигурен | — | — |
| 1.2 | XSS через template auto-escape | ✅ Django по умолчанию | — | — |
| 1.3 | **CSP `script-src` с `'unsafe-inline'`** | 🟡 разрешён → XSS защита частично выключена. `simulation.html` имеет 15k+ строк инлайн-JS, nonce-CSP сложен | 🔥 | 2-3 дня (вынос JS в файлы + nonce middleware) |
| 1.4 | SQL-injection через ORM | ✅ raw SQL не используется (grep подтвердил) | — | — |
| 1.5 | SSRF (юзер-URL для загрузки фото / каталога) | ❓ нужен аудит `Dolg_APP/services/artifact_ingestion.py` и т.п. — проверка, что URL не указывает на 127.0.0.1/169.254.169.254 (cloud metadata) | 🔥 | 1 ч + allow-list |
| 1.6 | Open redirect через `next=` параметр | ❓ нужен аудит login/logout views на валидацию next URL | 🟧 | 30 мин |
| 1.7 | Mass assignment / Direct Object Reference (IDOR) | 🟡 select_related есть, но нужен явный owner-check на `/projects/<id>/`, `/reviews/<id>/` | 🔥 | 2 ч аудита + декоратор `owner_required` |
| 1.8 | File upload validation (тип, размер, content-sniff) | 🟡 Pillow валидирует image, но размер до Pillow и MIME-type из заголовка не проверены | 🟧 | 1 ч |
| 1.9 | Subprocess shell-injection (`Dolg_APP/views.py:1002`) | ✅ cmd как list, `shell=False` по умолчанию | — | — |
| 1.10 | Path traversal в загружаемых именах файлов | ❓ нужно проверить, что upload paths sanitize `..` | 🟧 | 30 мин |
| 1.11 | Insecure deserialization (pickle/yaml.load) | ✅ не используется | — | — |
| 1.12 | Prototype pollution / template injection | ✅ Django template engine безопасен; ничего не eval'им на сервере | — | — |
| 1.13 | Server-Side Template Injection (SSTI) | ✅ — | — | — |
| 1.14 | Limited-rate / quota на тяжёлые эндпоинты | 🟡 `enforce_daily_quota('simulations')` есть на симуляциях. Нет на /api/ai/chat/, на /cad/api/import/ | 🟧 | 1 ч |
| 1.15 | JSON-flooding / oversized payload (`scheme_data`) | ❌ Нет лимита на размер JSON; теоретически юзер может загрузить 100 МБ scheme_data | 🟧 | 30 мин (max body size) |

## 2. Аутентификация / Авторизация

| # | Что | Состояние | Прио | Усилие |
|---|---|---|---|---|
| 2.1 | 2FA (TOTP + backup codes) | ✅ `django-otp`, 2 views, тесты | — | — |
| 2.2 | SSO (Google/Microsoft/GitHub) | ✅ `django-allauth` | — | — |
| 2.3 | Brute-force на login (`django-axes`) | ✅ `AXES_FAILURE_LIMIT=5`, `COOLOFF=1h` | — | — |
| 2.4 | Password strength validators | ❓ нужно проверить `AUTH_PASSWORD_VALIDATORS` | 🟢 | 5 мин |
| 2.5 | Password breach check (HaveIBeenPwned k-anonymity) | ❌ | 📚 | 1 ч |
| 2.6 | Account enumeration на /login и /reset/ | ❓ generic-сообщения "если email существует, мы отправили..."? | 🟧 | 15 мин аудит |
| 2.7 | Session fixation после login | ✅ Django по умолчанию rotate session | — | — |
| 2.8 | Timing attack на password compare | ✅ Django использует constant-time compare | — | — |
| 2.9 | Sudo-mode для критических действий (delete account, change password, change 2FA) | ❌ | 🟧 | 2 ч |
| 2.10 | OAuth state/PKCE в allauth | ✅ allauth handles | — | — |
| 2.11 | JWT vs session | N/A — используем session cookies (правильный выбор для server-rendered) | — | — |
| 2.12 | Permission decorators на staff-only views | 🟡 `login_required` есть, `staff_required`/`permission_required` нужно проверить на ML/admin views | 🔥 | 1-2 ч аудита |
| 2.13 | API endpoints без auth (`/api/...`) | 🟡 у некоторых `login_required`, у других — нет. Нужен аудит | 🔥 | 1 ч |

## 3. Secrets & crypto

| # | Что | Состояние | Прио | Усилие |
|---|---|---|---|---|
| 3.1 | SECRET_KEY refuses default in prod | ✅ guard at `settings.py:72` | — | — |
| 3.2 | .env не в git | ✅ `.env` в `.gitignore`, есть `.env.example` | — | — |
| 3.3 | Git history scan на случайно закоммиченные secrets | ❌ | 🔥 | 30 мин (`gitleaks detect`) |
| 3.4 | Pre-commit hook secret-scanning | ❌ | 🟧 | 5 мин (`gitleaks` или `detect-secrets` в `.pre-commit-config.yaml`) |
| 3.5 | Stripe live keys vs test keys (отдельные env) | ✅ через `STRIPE_API_KEY` env-var | — | — |
| 3.6 | Anthropic API key rotation | ❌ ручная rotation, no automated | 📚 | — |
| 3.7 | Database encryption at rest | ❌ SQLite plain file. Postgres + pgcrypto — post-defense | 📚 | — |
| 3.8 | Encrypted backups | 🟡 `backups/` создаются, но без шифрования | 🟧 | 30 мин (`age` или `gpg`) |
| 3.9 | **Secrets manager — HashiCorp Vault + GitOps** | ❌ env-vars сейчас в plaintext. После K8s — Vault Secrets Operator ([ricoberger/vault-secrets-operator](https://github.com/ricoberger/vault-secrets-operator)) синхронизирует Vault → K8s `Secret` через Custom Resources, прокидывается через Flux/Argo (см § 16.6) | 📚 | post-K8s, 1 день |
| 3.10 | TLS на всех соединениях (cert auto-renewal) | ✅ Cloudflare Tunnel terminates TLS | — | — |
| 3.11 | Hash алгоритм для паролей | ✅ Django PBKDF2 (или Argon2 если установлен) | — | — |

## 4. Data protection / PII

| # | Что | Состояние | Прио | Усилие |
|---|---|---|---|---|
| 4.1 | PII inventory (что хранится — email, имя, фото, история заказов) | ❌ нет formal inventory | 🟧 | 1 ч |
| 4.2 | GDPR: data subject access (export) | ❌ | 📚 | 1 день |
| 4.3 | GDPR: right to be forgotten (delete account + cascade) | 🟡 удаление user'а каскадно удаляет проекты, но не всегда полностью | 🟧 | 2 ч |
| 4.4 | Data retention policy (когда удаляем неактивные аккаунты) | ❌ | 📚 | policy doc |
| 4.5 | Logs scrubbing (не логируем passwords/tokens) | ❓ нужен аудит на `logger.info(request.POST)` и т.п. | 🟧 | 30 мин |
| 4.6 | Cookie consent / cookie banner | ❌ | 🟧 | 1 ч |
| 4.7 | Privacy Policy + Terms of Service страницы | ❌ | 🟧 | 2 ч (текст + шаблон) |
| 4.8 | Audit trail (кто что сделал, когда) | 🟡 есть `ProjectEvent` для проектов; нет для login/logout/password change | 🟧 | 2 ч |
| 4.9 | Org-level multi-tenant isolation | 🟡 есть `Organization` FK, но нужен аудит каждого filter на `request.user.organization` | 🔥 | 2-3 ч |

## 5. Supply chain

| # | Что | Состояние | Прио | Усилие |
|---|---|---|---|---|
| 5.1 | Все зависимости pinned (==) | ✅ requirements.txt с конкретными версиями | — | — |
| 5.2 | Lockfile (pip-tools / poetry / uv) для reproducible builds | ❌ | 🟧 | 30 мин (`uv pip compile`) |
| 5.3 | `pip-audit` / `safety` в CI | ❌ | 🔥 | 15 мин (GitHub Action) |
| 5.4 | Renovate / Dependabot security updates | ❌ | 🟧 | 10 мин config |
| 5.5 | SBOM (Software Bill of Materials) | ❌ | 📚 | `cyclonedx-py` 5 мин |
| 5.6 | License audit (нет ли GPL'ных libs в proprietary code) | ❌ | 🟢 | 30 мин (`pip-licenses`) |
| 5.7 | SRI (Subresource Integrity) для CDN | N/A — используем локальные libs (`shop/static/lib/`) | — | — |

## 6. Container / DevOps security

| # | Что | Состояние | Прио | Усилие |
|---|---|---|---|---|
| 6.1 | Dockerfile multi-stage build | 🟡 есть production-ready single-stage `python:3.14-slim`; multi-stage оставлен optional, потому что тяжёлые wheel-зависимости ставятся без C-toolchain | 🟢 | post-runtime |
| 6.2 | Non-root user в контейнере | ✅ `USER dolg` в `deploy/Dockerfile` | — | — |
| 6.3 | Минимальный base image (`slim` / `distroless`) | ✅ `python:3.14-slim` | — | — |
| 6.4 | `.dockerignore` (не копируем .git, venv) | ✅ корневой `.dockerignore` исключает `.git`, `.venv`, docs, media, logs, `.codex` | — | — |
| 6.5 | Container scanning (Trivy / Snyk / Grype) в CI | ✅ Trivy image scan в `.github/workflows/django.yml` | — | — |
| 6.6 | Docker secrets / docker-compose secrets вместо env | 🟡 local smoke через ignored env-file; для prod нужен внешний secret supply | 🟢 | post-runtime |
| 6.7 | Health checks (`HEALTHCHECK` в Dockerfile, `/healthz` endpoint) | ✅ Dockerfile, compose и K8s probes используют `/healthz` | — | — |
| 6.8 | Resource limits (cpu/memory limits в compose) | ✅ compose limits + K8s requests/limits | — | — |
| 6.9 | Read-only root filesystem | 🟡 включено для app/nginx контейнеров; stateful/monitoring сервисы требуют отдельной политики | 🟢 | 30 мин |
| 6.10 | Drop capabilities (`cap_drop: [ALL]`) | ✅ compose и K8s workloads drop `ALL` capabilities | — | — |
| 6.11 | K8s manifests (Deployment + Service + Ingress) | 🟡 base `deploy/k8s` добавлен: Deployment/Service/nginx edge; Ingress/Helm оставлены следующим слоем | 🟢 | post-runtime |
| 6.12 | K8s NetworkPolicy / PodSecurityPolicy | 🟡 `deploy/k8s/networkpolicy.yaml` + Pod Security baseline/warn-restricted добавлены; полный restricted enforce после runtime smoke | 🟢 | post-runtime |

## 7. Network / инфраструктура

| # | Что | Состояние | Прио | Усилие |
|---|---|---|---|---|
| 7.1 | Cloudflare Tunnel — нет публичного IP | ✅ `cloudflared.exe` в deploy/ | — | — |
| 7.2 | WAF (Cloudflare WAF rules) | 🟡 Cloudflare дефолтные правила работают, кастомные — нет | 🟧 | 30 мин на dashboard |
| 7.3 | DDoS protection | ✅ Cloudflare | — | — |
| 7.4 | nginx hardening (`server_tokens off`, не отдавать версию) | ❓ нужно посмотреть `deploy/nginx.conf` | 🟧 | 10 мин |
| 7.5 | DB не expose'ит порт наружу | ✅ SQLite, нет порта | — | — |
| 7.6 | SSH key rotation policy | ❌ | 🟢 | — |
| 7.7 | SSH disable password auth, key-only | ❓ — нужно проверить на yc-bootstrap.sh | 🟧 | — |
| 7.8 | SSH fail2ban | ❌ | 🟢 | 5 мин |
| 7.9 | Firewall rules / VPC security groups | ❓ | 🟧 | — |
| 7.10 | TLS 1.2+ only | ✅ Cloudflare default | — | — |
| 7.11 | CDN cache poisoning защита | N/A | — | — |
| 7.12 | Bot management (hCaptcha на формы) | ❌ | 🟢 | 30 мин |

## 8. Мониторинг / детекция

| # | Что | Состояние | Прио | Усилие |
|---|---|---|---|---|
| 8.1 | Sentry error tracking | ✅ `sentry-sdk` в requirements, активируется через env | — | — |
| 8.2 | Failed-auth detection (через axes events) | ✅ `django-axes` логирует | — | — |
| 8.3 | Grafana + Prometheus | 🟡 `deploy/grafana` + `prometheus.yml` есть, нужно убедиться что метрики экспортируются | 🟧 | 1 ч |
| 8.4 | Uptime monitoring (UptimeRobot / Pingdom / self-hosted) | ❌ | 🟢 | 5 мин |
| 8.5 | Alerting (Pagerduty / Slack / Telegram bot) | ❌ | 🟢 | — |
| 8.6 | Audit log aggregation (ELK / Loki) | 🟡 Prometheus есть, log aggregator нет | 📚 | — |
| 8.7 | Honeypot fields в forms | ❌ | 🟢 | 15 мин |
| 8.8 | Anomaly detection (внезапный спайк траффика, новая страна логина) | ❌ | 📚 | — |

## 9. Code hygiene / SDL

| # | Что | Состояние | Прио | Усилие |
|---|---|---|---|---|
| 9.1 | Pre-commit hooks | ✅ `.pre-commit-config.yaml` с ruff + ruff-format | — | — |
| 9.2 | **`bandit` (Python SAST)** | ❌ | 🔥 | 10 мин + первый прогон с triage |
| 9.3 | **`gitleaks` / `detect-secrets` в pre-commit** | ❌ | 🔥 | 5 мин |
| 9.4 | `pip-audit` в pre-commit или CI | ❌ | 🔥 | 5 мин |
| 9.5 | `eslint-plugin-security` для JS | ❌ | 🟢 | 30 мин |
| 9.6 | Semgrep (cross-language SAST) | ❌ | 🟧 | 15 мин CI |
| 9.7 | Branch protection на `main` (require PR + checks) | ❓ нужно посмотреть `.github/` | 🟧 | 5 мин на gh dashboard |
| 9.8 | CODEOWNERS файл | ❌ | 🟢 | 5 мин |
| 9.9 | PR template | ❓ | 🟢 | 5 мин |
| 9.10 | Signed commits (GPG / SSH) | ❌ | 🟢 | — |
| 9.11 | Security.md (vulnerability disclosure policy) | ❌ | 🟧 | 10 мин |

## 10. Compliance / governance

| # | Что | Состояние | Прио | Усилие |
|---|---|---|---|---|
| 10.1 | Privacy Policy | ❌ | 🟧 | 2 ч (текст) |
| 10.2 | Terms of Service | ❌ | 🟧 | 2 ч |
| 10.3 | Cookie banner | ❌ | 🟢 | 1 ч |
| 10.4 | Incident response plan (1-page) | ❌ | 🟢 | 30 мин doc |
| 10.5 | DPA (если используем third-parties processing PII) | ❌ — Anthropic API получает чат с PII, OpenAI/HF тоже | 📚 | doc |
| 10.6 | GDPR DSR endpoint (`/account/export-my-data`) | ❌ | 📚 | 4 ч |

## 11. DOLG-specific риски

| # | Что | Состояние | Прио | Усилие |
|---|---|---|---|---|
| 11.1 | **AI prompt injection через `/api/ai/chat/`** | ❌ юзерский ввод улетает в Claude, могут попробовать заставить раскрыть system prompt или выполнить «инструкции» вроде «удали проект». Smart-search и т.п. тоже | 🔥 | 1 день (input sanitization + system prompt hardening + output filtering) |
| 11.2 | SPICE netlist injection (eval'им netlist на сервере?) | ❓ — нужно проверить, что serverside netlist парсится stdlib, а не eval'ится | 🔥 | 30 мин аудита |
| 11.3 | Schema JSON oversized payload | ❌ см 1.15 | 🟧 | 30 мин |
| 11.4 | Lithium import — XSS через имена пакетов/компонентов | 🟡 наш парсер escape'ит `<` `>` в attrs (мы сделали для XML), но рендеринг на странице нужно проверить | 🟧 | 30 мин |
| 11.5 | Shop checkout / Stripe webhook signature verification | ❓ — нужно убедиться, что webhook'и валидируют `Stripe-Signature` | 🔥 | 15 мин проверка |
| 11.6 | File upload (продукт-фото) — content-sniffing, dimension limits | 🟡 Pillow проверяет формат, но `media/products/` может содержать non-image | 🟧 | 30 мин |
| 11.7 | Org isolation для проектов / отчётов | 🟡 см 4.9 | 🔥 | 2-3 ч |
| 11.8 | Admin views с `is_staff` checks | 🟡 см 2.12 | 🔥 | 1-2 ч |
| 11.9 | DWG-converter subprocess (`views.py:1002`) — path traversal в tmp_path | 🟧 нужно проверить, что tmp_path = `Path(tempfile.mkdtemp())` (не user-controlled) | 🟧 | 5 мин аудита |

## 12. File hygiene / репозиторий

| # | Что | Состояние | Прио | Усилие |
|---|---|---|---|---|
| 12.1 | Очистка артефактов (`*.log`, `~$*.docx`, `.tmp_*/`) | ✅ commit `837a59c` (16 PNG + 5 JPG + 2 Office-локов снесены, `.gitignore` расширен) | — | — |
| 12.2 | **`docs/` консолидация** roadmap/backlog/research-файлов | ✅ 2026-06-16: старые планы сжаты в `docs/DEVELOPMENT_HISTORY.md`, активный фронт оставлен в `docs/WORK_FRONT_20260619.md`, поглощённые файлы удалены | — | — |
| 12.3 | **`scripts/` чистка** — one-shot генераторы с датами: `update_diploma_materials_20260519.py` (60 КБ), `build_presentation_*_20260519.py` (×2 × 29 КБ, почти дубль), `update_speech_scheme_questions_20260519.py`, `rebuild_defense_materials_20260524.py` (40 КБ), `generate_diploma_two_chapter_rework.py` (59 КБ), `update_diploma_v3_from_docs_20260510.py`, DRC-chain (`expand_drc_rules.py` 46 КБ + `finalize_drc_rules.py` + `enable_drc_rules.py`), `seed_ml_dataset.py` (59 КБ) → `scripts/archive/` или `git rm` | 🟧 | 1 ч (нужен confirm) |
| 12.4 | `management/commands/` ревизия (38 файлов) — отметить one-shot (seed/backfill/migrate/normalize) → `archive/`; репитативные → оставить или объединить в `health_check` | 🟧 | 2-3 ч |
| 12.5 | `simulation.html` split (18 640 строк → отдельные `shop/static/simulation/scheme-{presets,erc,multisection,router,utils}.js`) | 📚 | 1 день, **post-defense** (риск ломануть рендер) |
| 12.6 | `media/` orphan-файлы — фото товаров без `Product`, ML артефакты без модели → cleanup-команда + cron | 🟢 | 1 ч |
| 12.7 | `backups/` retention policy — `hourly-snapshot.bat` создаёт tarballs, нет авто-удаления старых | 🟢 | 30 мин (`find … -mtime +14 -delete` в bat) |
| 12.8 | DB squash миграций (16+ → `0001_initial_squashed.py`) | 📚 | post-defense, ускоряет fresh `migrate` |
| 12.9 | `.dockerignore` (не копируем `.git`, `.venv`, `docs/`, `backups/` в контейнер) | 🟧 | 5 мин |
| 12.10 | LFS / large binaries audit — нет ли больших `.docx` / `.pptx` без LFS | 🟢 | `git lfs ls-files` + audit |

## 13. GitHub hygiene (репо settings + workflows + history)

| # | Что | Состояние | Прио | Усилие |
|---|---|---|---|---|
| 13.1 | **Branch protection** на `main` — require PR review, require checks pass, no force-push, no direct push | ❓ нужно глянуть в Settings | 🔥 | 5 мин в Settings → Branches |
| 13.2 | **`SECURITY.md`** — vulnerability disclosure policy (контакт, scope, response time) | ❌ | 🟧 | 10 мин (template) |
| 13.3 | `CODEOWNERS` файл (`* @zlodey2077`) — авто-reviewer на PR | ❌ | 🟢 | 5 мин |
| 13.4 | PR template + Issue templates (`.github/ISSUE_TEMPLATE/`) | ❓ нужно глянуть | 🟢 | 10 мин |
| 13.5 | GitHub Actions workflows — pin actions по SHA (не по `@v3`, который mutable) | ❓ нужен аудит `.github/workflows/` | 🟧 | 30 мин |
| 13.6 | `permissions:` в Actions (default — `contents: read`, явно разрешать `write` только где нужно) | ❓ | 🟧 | 30 мин |
| 13.7 | GitHub Secrets — аудит, что хранится; rotate если что-то старше 90 дней | ❓ | 🟢 | manual в Settings |
| 13.8 | **Dependabot security updates** — `dependabot.yml` для pip + github-actions | ❌ | 🟧 | 10 мин (`.github/dependabot.yml`) |
| 13.9 | **Repo visibility** — частный/публичный, по статусу диплома | ❓ зависит от защиты — публичный после защиты, до — лучше private/internal | 🟧 | manual |
| 13.10 | `.github/workflows/ci.yml` — добавить `bandit` + `pip-audit` + `gitleaks` step'ы (= H4 из § 9) | ❌ | 🔥 | 30 мин |
| 13.11 | **Git history scrub** — secrets (если найдутся через H5 gitleaks), AI-fingerprints (датированные комменты — отдельный backlog [[project-anti-ai-cleanup-backlog]]) | ❌ | 🟧 после H5 | 1-2 ч `git filter-repo` + force-push (требует приватного репо или координации) |
| 13.12 | Stale branches / closed PRs cleanup | ❓ глянуть `git branch -a` | 🟢 | 5 мин |
| 13.13 | Release tags / история изменений | 🟡 история теперь в `docs/DEVELOPMENT_HISTORY.md`, git tags ещё нет | 🟢 | 5 мин на тег `v1.0.0-defense` |
| 13.14 | Repository description + topics + README badges (защитные значки security/license/python-version) | 🟢 | 10 мин на Settings |
| 13.15 | GitHub Advanced Security — code scanning (CodeQL) — бесплатно для public repo | ❌ | 🟢 | 5 мин на `.github/workflows/codeql.yml` |
| 13.16 | Dependabot alerts включены в Settings → Code security | ❓ | 🟧 | 1 клик |
| 13.17 | Secret scanning alerts (GitHub native, public repo only) | ❓ | 🟧 | 1 клик |
| 13.18 | Push protection (отказ push'а с обнаруженным secret'ом) | ❓ | 🟧 | 1 клик |

## 14. Runtime detection / IDS / anomaly response (запрос юзера 2026-06-04)

Связка «детектор + автоматический response» — чтобы я меньше «выдумывал»
проблемы, а реальные подозрительные действия отлавливались утилитами.
DOLG сейчас закрыт django-axes (только login). Расширяем.

### 14.A — Host / network уровень

| # | Что | Тип | Состояние | Прио | Усилие |
|---|---|---|---|---|---|
| 14.1 | **CrowdSec** (open-source, замена fail2ban + crowdsourced IP-reputation) — детект подозрительных HTTP-паттернов (SQL-i, XSS, scanners) + автоматический block через nginx-bouncer | network-IDS + auto-block | ❌ | 🔥 | 1 ч (deb-пакет + nginx bouncer) |
| 14.2 | fail2ban на SSH (5 неудачных → 1ч ban) | network | ❓ нужно глянуть `yc-bootstrap.sh` | 🟧 | 5 мин |
| 14.3 | **Falco** (eBPF runtime security для контейнеров) — детект suspicious syscalls (`/etc/shadow` read, reverse shell и т.п.) | container runtime | ❌ — нужен K8s или docker | 📚 | post-K8s (см § 16) |
| 14.4 | **Wazuh** (host-IDS, FIM + log monitoring + rootcheck) | HIDS | ❌ | 📚 | 4-6 ч setup |
| 14.5 | Auditd на хосте (audit-trail для критичных файлов/процессов) | host | ❌ | 🟧 | 30 мин policy |
| 14.6 | **ModSecurity / Coraza** в nginx (WAF с OWASP CRS) — режет SQL-i/XSS на L7 до Django | WAF | ❌ | 🟧 | 1 ч |
| 14.7 | **Cloudflare WAF rules** — Custom Rules (rate limit per-IP, geo-block, bot fight) | edge WAF | 🟡 базовые правила работают, кастомные не настроены | 🟧 | 30 мин на dashboard |

### 14.B — Application уровень (circuit breakers / kill switches)

| # | Что | Состояние | Прио | Усилие |
|---|---|---|---|---|
| 14.8 | **Axes расширить за пределы login** — на /api/ai/chat/, /cad/api/import/, /reviews/ создать кастомные failure-точки (axes имеет `lockout_callable`) | 🟡 axes есть, но только login | 🔥 | 1 ч |
| 14.9 | **Honeypot endpoints** — `/wp-admin/`, `/.env`, `/phpmyadmin/` → middleware ловит → bans IP в axes/CrowdSec → 1 строка лога | ❌ | 🟧 | 30 мин |
| 14.10 | **Honeypot fields** в формах регистрации (hidden input — если заполнен, бот) | ❌ | 🟢 | 15 мин |
| 14.11 | **Feature kill switches** — `FEATURE_FLAGS` модель: `ai_chat_enabled`, `lithium_import_enabled`, `simulation_enabled` — админ может отрубить одной кнопкой при инциденте | ❌ | 🟧 | 2 ч |
| 14.12 | **Circuit breaker для AI/ML endpoints** — если error rate за 5 мин >20%, фича авто-отключается на 10 мин, в Sentry летит alert | ❌ | 🟧 | 2 ч (см. `pybreaker` либа — dev-tooling, можно ставить) |
| 14.13 | **Rate limit per-user** на тяжёлые операции (поверх существующих daily-quota) — мгновенный per-minute throttle | 🟡 daily quota есть, per-minute нет | 🟧 | 1 ч |
| 14.14 | **Admin-action audit trail** — каждое staff-действие (delete, edit чужого) → `AdminAuditLog` модель + Sentry breadcrumb | 🟡 ProjectEvent для project-mutations есть, для остального нет | 🟧 | 2 ч |
| 14.15 | **Anomaly alert** — если суточный traffic вырос в 3× — Telegram-bot пишет «спай» | ❌ | 🟢 | 1 ч (management command + cron) |
| 14.16 | **Anti-CSRF на admin-actions через двойной HMAC** — если паранойя, действия типа «delete project» требуют второй token из почты | ❌ | 📚 | — |

### 14.C — Bug tracking (для того, чтобы я не выдумывал, что упустил)

| # | Что | Состояние | Прио | Усилие |
|---|---|---|---|---|
| 14.17 | **Sentry** — error/exception tracking | ✅ `sentry-sdk` в requirements, активируется env | — | — |
| 14.18 | **GlitchTip** — self-hosted Sentry-совместимый, если хочется без облака | ❌ | 📚 | post-defense |
| 14.19 | **Sentry performance monitoring** — slow queries, slow views | ❌ — sentry-sdk умеет, нужен `traces_sample_rate` | 🟧 | 5 мин config |
| 14.20 | **`django-silk` или `django-debug-toolbar`** в dev/staging — профилирование запросов | ❌ | 🟢 | 10 мин (dev only) |
| 14.21 | **`django-health-check`** — `/healthz/` с DB/cache/storage/Sentry/Stripe API status | ❌ | 🟧 | 15 мин |
| 14.22 | **Uptime monitor** (UptimeRobot бесплатно, или CrowdSec community alerts) | ❌ | 🟢 | 5 мин |

## 15. Углублённая чистка файлов с access-control (запрос юзера 2026-06-04)

Сверх § 12 — не просто удалить/переместить, но и закрыть доступ к
перенесённым артефактам, чтобы случайный gh-clone'ер не видел диплом-
доки/презы/секреты.

| # | Что | Состояние | Прио | Усилие |
|---|---|---|---|---|
| 15.1 | **Diploma `.docx`/`.pptx` из git → вне репо** | в `docs/` лежат `Диплом_DOLG_финальная_редакция_*.docx` (3 МБ), `Презентация_DOLG_основная_защита_*.pptx` (3 МБ), `Речь_и_вопросы_к_защите_*.docx` (40 КБ) — это PII (мой текст + сведения) | 🔥 | 30 мин: перенести в `~/Documents/DOLG_diploma_artifacts/`, симлинк в `docs/local/` (gitignored), git-rm из репо. Git history scrub через `git filter-repo` |
| 15.2 | **`docs/diploma_assets/generated/`** (новые ассеты, не закоммичены) — в `.gitignore` если не нужны под версионированием | ❓ | 🟧 | 5 мин |
| 15.3 | **`backups/` за пределы репо** — `~/.dolg-backups/` (gitignored ✅), но добавить encryption-at-rest через `age -p` (или `gpg --symmetric`) | 🟡 gitignored, не зашифрованы | 🟧 | 1 ч (расширить `hourly-snapshot.bat`) |
| 15.4 | **`media/products/`, `media/avatars/` chmod 750** на проде (group www-data, не world-readable) | ❓ | 🟧 | nginx config + chmod |
| 15.5 | **`.env` chmod 600** + audit `git ls-files` что не закоммичен | ✅ gitignored, нужно проверить chmod на проде | 🟧 | 5 мин |
| 15.6 | **`deploy/cloudflared.exe` (65 МБ binary)** — gitignored ✅, проверить что нет в истории | ✅ check | 🟢 | 5 мин (`git log --all --full-history -- deploy/cloudflared.exe`) |
| 15.7 | **Login-required доступ к `/static/screenshots/` и `/static/cad/templates/`** через nginx `auth_request` или Django serve — внутренние demo-материалы | ❌ | 🟧 | 30 мин |
| 15.8 | **`docs/`-папка с tier'ами** — `docs/public/` (README, ARCHITECTURE, DEPLOY) и `docs/internal/` (planning, security backlog, gap analyses) с .htaccess/nginx deny если репо публичный | ❌ | 🟢 | 30 мин (если защищаем приватность планов) |
| 15.9 | **EXIF strip с upload'ов** — Pillow `image.info` чистка GPS-координат и devicе info при сохранении продуктовых фото | ❌ | 🟧 | 15 мин (`piexif` или ручной clean) |
| 15.10 | **db.sqlite3** — gitignored ✅, но на проде шифровать ФС-уровнем (LUKS на YC volume) | 🟡 plain | 📚 | — |
| 15.11 | **`importtime_check.log`** — снёс ✅ commit `837a59c` | ✅ | — | — |
| 15.12 | **`scripts/archive/`** — старые genenrator'ы перенести; **gitignore** их или закоммитить как archive read-only | ❌ | 🟧 | 30 мин |
| 15.13 | **`.claude/` и `~/.claude/projects/`** memory-файлы со ВСЕЙ моей перепиской — НЕ в репо ✅ (это локальная папка Claude), но проверить что нигде не закоммитили | ✅ check | — | — |
| 15.14 | **Audit `git log -p` на любые секреты в history** — = H5 (gitleaks) — ⚠ результат может потребовать `git filter-repo` + force-push | ❌ | 🔥 | см. H5 |
| 15.15 | **Презентации с avatar/email в metadata** — pptx содержит автора, проверить «Свойства документа» в Office перед коммитом | ❓ | 🟢 | manual |
| 15.16 | **`media/ml/`** — ML модели/датасеты gitignored ✅, проверить .gitattributes для LFS если будут >100МБ | 🟡 | 🟢 | 10 мин |

## 16. Docker / K8s roadmap (явный запрос юзера на будущее)

| # | Что | Состояние | Прио | Усилие |
|---|---|---|---|---|
| 16.1 | Dockerfile production-ready (multi-stage, slim, non-root) | 🟡 slim + non-root + healthcheck готовы; multi-stage optional после runtime smoke | 🟢 | post-runtime |
| 16.2 | docker-compose с health checks + resource limits | ✅ compose закрывает db/redis/web/asgi/worker/nginx/prometheus/grafana | — | — |
| 16.3 | **`buildg`** — интерактивный отладчик Dockerfile с IDE-интеграцией (VS Code), breakpoints + step exec на build шагах, основан на BuildKit. [ktock/buildg](https://github.com/ktock/buildg) | ❌ | 🟢 (dev-tool, ставится по желанию при отладке billion-step Dockerfile) | 5 мин binary install |
| 16.4 | K8s Deployment + Service + Ingress | 🟡 base Deployment/Service/nginx edge готов; Ingress/Helm values ещё нет | 🟢 | post-runtime |
| 16.5 | Helm chart | ❌ | 📚 | 1 день |
| 16.6 | **Vault Secrets Operator + ArgoCD/Flux GitOps**: коммит → Flux pull → applies → Vault Secrets Operator читает из HashiCorp Vault → создаёт K8s Secret. Operator: [ricoberger/vault-secrets-operator](https://github.com/ricoberger/vault-secrets-operator). Закрывает § 3.9 (Secrets manager) | ❌ | 📚 | 1 день setup Vault + 1 день operator |
| 16.7 | Альтернатива 16.6 — **ExternalSecrets Operator** + AWS SM/Azure KV/GCP SM (если не хотим self-host Vault) | ❌ | 📚 | — |
| 16.8 | **Sealed Secrets** (Bitnami) — простой вариант для маленького кластера, ключ encryption-at-rest шифрует секреты внутри git | ❌ | 📚 | 2 ч |
| 16.9 | HPA (Horizontal Pod Autoscaler) | ❌ | 📚 | — |
| 16.10 | NetworkPolicy default-deny | ✅ default-deny + allow-list для nginx/web/asgi/db/redis/prometheus/grafana | — | — |
| 16.11 | PodSecurityStandard `restricted` | 🟡 namespace enforces `baseline`, warns/audits `restricted`; workloads drop caps + RuntimeDefault seccomp | 🟢 | post-runtime |
| 16.12 | **Falco** (см § 14.3) — eBPF runtime security для контейнеров | ❌ | 📚 | post-K8s |
| 16.13 | **Trivy / Grype** container image scan в CI | ✅ Trivy image scan добавлен в container job | — | — |
| 16.14 | **Cosign / Sigstore** image signing | ❌ | 📚 | — |

---

## Сводка приоритетов

### ⛔ CRITICAL — нет (все базовые crud-уязвимости закрыты, есть 2FA, axes, CSP, HSTS, sentry)

### 🔥 HIGH (рекомендуется до защиты, 1-2 рабочих дня суммарно)

1. **2.12 + 2.13 + 11.8** — аудит permission_required / staff_required / API auth (`~3 ч`).
2. **1.7 + 4.9 + 11.7** — IDOR / org isolation: декоратор `owner_required`, явный owner-check на `/projects/<id>/`, `/reviews/<id>/`, `/orgs/<id>/...` (`~3 ч`).
3. **11.5** — Stripe webhook signature verification (`~15 мин`).
4. **9.2 + 9.3 + 9.4** — `bandit` + `gitleaks` + `pip-audit` в pre-commit (`~30 мин`).
5. **3.3** — `gitleaks detect` по git history, найти и rotate любые случайно закоммиченные secrets (`~30 мин`).
6. **1.5** — SSRF guard на user-URL загрузке (allow-list) (`~1 ч`).
7. **11.1** — AI prompt injection защита: input sanitization + system prompt hardening + output filtering (`~1 день`).
8. **11.2** — SPICE netlist eval audit (`~30 мин`).
9. **1.3** — частичное CSP-укрепление: добавить nonce для inline-JS в **новых** страницах (старые simulation.html не трогаем до post-defense split) (`~2 ч`).

### 🟧 MEDIUM (полировка, можно после защиты)

- 1.14, 1.15 (rate limit + JSON size limit)
- 4.3, 4.5 (GDPR cascading delete + log scrubbing)
- 6.6, 6.9, 6.12 (secret supply + read-only polish + restricted enforce after runtime)
- 7.4 (nginx hardening)
- 8.3 (Grafana metrics export)
- 9.7 (branch protection)
- 10.1, 10.2 (Privacy / ToS)
- 11.4 (Lithium XSS в renderer)

### 📚 NICE-TO-HAVE (post-defense, production-readiness)

- Helm/GitOps/secrets слой для K8s + full restricted PodSecurity after smoke + 6.9 polish.
- 4.1, 4.2, 4.6, 4.8 (PII inventory + DSR + cookie consent + audit trail).
- 8.5, 8.6, 8.8 (alerting + log aggregation + anomaly detection).
- 3.7, 3.8 (DB encryption at rest, encrypted backups).
- 2.5, 2.9 (HIBP password check + sudo mode).

---

## Связано

- [[project-2fa-sso]] — закрыто
- [[project-stripe-billing]] — нужно проверить webhook signatures (11.5)
- [[project-master-plan-3weeks]] — план фич; security — поверх
- [[project-server-cleanup-todo]] — отдельный server-side cleanup backlog
- [[project-postgres-migration]] — миграция нужна для DB encryption (3.7)
