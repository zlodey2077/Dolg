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

## Статус HIGH-tier на 2026-06-06 (проверено по коду)

Все 9 рекомендованных до защиты HIGH-пунктов закрыты и подтверждены в коде:

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
| H9 CSP nonce для inline-JS (1.3) | ✅ | commit `55ef51a` (simulation.html — post-defense split) |

Следующий уровень риска — MEDIUM (rate limits на `/api/ai/chat/` и `/cad/api/import/`, GDPR cascade delete, log scrubbing, JSON body-size limit, file-upload MIME/size, open-redirect `next=`). Не блокирует защиту.

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
| 6.1 | Dockerfile multi-stage build | ❓ нужно проверить `deploy/Dockerfile` | 🟧 | — |
| 6.2 | Non-root user в контейнере | ❓ | 🟧 | 5 мин (`USER appuser`) |
| 6.3 | Минимальный base image (`slim` / `distroless`) | ❓ | 🟢 | 10 мин |
| 6.4 | `.dockerignore` (не копируем .git, venv) | ❓ | 🟧 | 5 мин |
| 6.5 | Container scanning (Trivy / Snyk / Grype) в CI | ❌ | 🟧 | 15 мин CI step |
| 6.6 | Docker secrets / docker-compose secrets вместо env | ❌ env через `--env-file` | 🟢 | — |
| 6.7 | Health checks (`HEALTHCHECK` в Dockerfile, `/healthz` endpoint) | ❓ | 🟧 | 30 мин |
| 6.8 | Resource limits (cpu/memory limits в compose) | ❓ | 🟢 | 5 мин |
| 6.9 | Read-only root filesystem | ❌ | 📚 | — |
| 6.10 | Drop capabilities (`cap_drop: [ALL]`) | ❌ | 📚 | — |
| 6.11 | K8s manifests (Deployment + Service + Ingress) | ❌ | 📚 (post-defense, по запросу юзера на «установить на будущее») | 1 день |
| 6.12 | K8s NetworkPolicy / PodSecurityPolicy | ❌ | 📚 | 1 день |

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
| 12.2 | **`docs/` консолидация** 52 → ≤10 файлов: слить `NEXT_PLAN` + `IMPROVEMENT_PLAN_*` + `PRIORITY_ROADMAP_*` + `CAD_REDESIGN_PLAN` + `CAD_HARD_UPGRADE_PLAN` + `SIMULATOR_LIVENESS_PLAN` в один `BACKLOG.md`; 8× `WORKFRONT_*` + 4× `AUDIT_*` + `EMERGENCY_*` + `ACCUMULATED_ISSUES` + `SCHEMATIC_EDITOR_FIXES` + `FULL_CODE_AUDIT` + `CODE_AUDIT_AND_DEFENSE_DOCS_WORKFLOW` + `ENGINEERING_PROCESS_NOTES` + `PROJECT_SESSION_*` → `docs/archive/` (или просто `git rm`, история сохранится) | 🟧 | 2 ч (нужен confirm на удаление) |
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
| 13.13 | Release tags / changelog | 🟡 `docs/CHANGELOG.md` есть, но git tags нет | 🟢 | 5 мин на тег `v1.0.0-defense` |
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
| 16.1 | Dockerfile production-ready (multi-stage, slim, non-root) | 🟡 есть Dockerfile, нужна полировка | 🟢 | 1 ч |
| 16.2 | docker-compose с health checks + resource limits | 🟡 есть compose, дополнить | 🟢 | 30 мин |
| 16.3 | **`buildg`** — интерактивный отладчик Dockerfile с IDE-интеграцией (VS Code), breakpoints + step exec на build шагах, основан на BuildKit. [ktock/buildg](https://github.com/ktock/buildg) | ❌ | 🟢 (dev-tool, ставится по желанию при отладке billion-step Dockerfile) | 5 мин binary install |
| 16.4 | K8s Deployment + Service + Ingress | ❌ | 📚 | 1 день |
| 16.5 | Helm chart | ❌ | 📚 | 1 день |
| 16.6 | **Vault Secrets Operator + ArgoCD/Flux GitOps**: коммит → Flux pull → applies → Vault Secrets Operator читает из HashiCorp Vault → создаёт K8s Secret. Operator: [ricoberger/vault-secrets-operator](https://github.com/ricoberger/vault-secrets-operator). Закрывает § 3.9 (Secrets manager) | ❌ | 📚 | 1 день setup Vault + 1 день operator |
| 16.7 | Альтернатива 16.6 — **ExternalSecrets Operator** + AWS SM/Azure KV/GCP SM (если не хотим self-host Vault) | ❌ | 📚 | — |
| 16.8 | **Sealed Secrets** (Bitnami) — простой вариант для маленького кластера, ключ encryption-at-rest шифрует секреты внутри git | ❌ | 📚 | 2 ч |
| 16.9 | HPA (Horizontal Pod Autoscaler) | ❌ | 📚 | — |
| 16.10 | NetworkPolicy default-deny | ❌ | 📚 | — |
| 16.11 | PodSecurityStandard `restricted` | ❌ | 📚 | — |
| 16.12 | **Falco** (см § 14.3) — eBPF runtime security для контейнеров | ❌ | 📚 | post-K8s |
| 16.13 | **Trivy / Grype** container image scan в CI | ❌ | 🟧 | 15 мин CI step |
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
- 6.4, 6.5, 6.7 (.dockerignore + container scan + health checks)
- 7.4 (nginx hardening)
- 8.3 (Grafana metrics export)
- 9.7 (branch protection)
- 10.1, 10.2 (Privacy / ToS)
- 11.4 (Lithium XSS в renderer)

### 📚 NICE-TO-HAVE (post-defense, production-readiness)

- Категория 12 целиком (K8s) + 6.9-6.10 (read-only fs, drop caps).
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
