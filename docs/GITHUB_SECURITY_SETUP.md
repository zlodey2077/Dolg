# GitHub Settings — пошагово, что включить кликами

Чек-лист для репо `zlodey2077/Dolg`. Большинство — нативные фичи
GitHub, не требуют CLI/PR. Кликни ссылку — попадёшь сразу на нужную
страницу настроек (замени `zlodey2077/Dolg`, если репо переименован).

> Все settings — в **Settings** репозитория (шестерёнка наверху → `Settings`).

---

## 1. ✅ Branch protection (ты сделал)

**Settings → Branches → Branch protection rules → Add rule** (или Edit
существующего).

Branch name pattern: `main`

Минимум что должно стоять:
- ☑ **Require a pull request before merging**
  - ☑ Require approvals: **1** (если работаешь один — оставь 0, но
    включи «Require status checks» обязательно)
- ☑ **Require status checks to pass before merging**
  - Кликни **search** и добавь:
    - `lint`
    - `security`
    - `test`
    - `analyze (python)` (после первого прогона CodeQL)
    - `analyze (javascript)`
  - ☑ **Require branches to be up to date before merging**
- ☑ **Require conversation resolution before merging**
- ☑ **Do not allow bypassing the above settings**
- ☐ Restrict who can push — оставь пустым (ты один)
- ☐ Allow force pushes — **отключено**
- ☐ Allow deletions — **отключено**

[**Кликабельная ссылка:**](https://github.com/zlodey2077/Dolg/settings/branches)

---

## 2. Code security & analysis (главная страница безопасности)

**Settings → Code security and analysis** (в левом меню).

Включи (по очереди — у каждой кнопка `Enable`):

- ☑ **Dependency graph** — обычно уже on. Нужен для следующих двух.
- ☑ **Dependabot alerts** — алерты при появлении CVE в твоих зависимостях.
- ☑ **Dependabot security updates** — авто-PR с фиксом версии CVE.
- ☑ **Dependabot version updates** — у нас уже есть `.github/dependabot.yml`
  (пункт 13.8). GitHub автоматически подхватит.
- ☑ **Code scanning** → **Set up** → **Default** или «через workflow».
  Если предлагает «через workflow» — выбирай это, мы уже добавили
  `.github/workflows/codeql.yml` (запустится автоматически на следующем
  push).
- ☑ **Secret scanning** (для приватных репо нужен GHAS, для публичных
  бесплатно).
- ☑ **Push protection** под Secret scanning — отказ push'а если в
  diff'е есть похожий на secret pattern.

[**Кликабельная ссылка:**](https://github.com/zlodey2077/Dolg/settings/security_analysis)

---

## 3. Actions permissions (защита от запуска чужих workflow)

**Settings → Actions → General**.

- **Actions permissions:**
  - Если репо приватный/internal: **Allow zlodey2077, and select non-zlodey2077, actions and reusable workflows** (минимум).
  - Если публичный: **Allow zlodey2077 actions and reusable workflows** + ☑ Allow actions created by GitHub + ☑ Allow Marketplace verified.

- **Workflow permissions:**
  - ⦿ **Read repository contents and packages permissions** (default `read`).
  - ☐ Allow GitHub Actions to create and approve pull requests — **отключено** (Dependabot и так умеет).

[**Кликабельная ссылка:**](https://github.com/zlodey2077/Dolg/settings/actions)

---

## 4. Required workflows (опционально, если хочешь жёстче)

**Settings → Actions → General → Required workflows**.

Можешь указать, что для merge в main обязательны `django.yml` и
`codeql.yml`. По факту это дублирует «Require status checks» из § 1,
но добавляет слой защиты.

---

## 5. General → Features (уборка лишнего)

**Settings → General → Features**.

- ☑ Issues — оставить (если хочешь, чтобы можно было репортить баги/security).
- ☑ Discussions — по желанию.
- ☐ Wiki — если не используешь, выключить (уменьшает attack surface).
- ☐ Projects — если не используешь.
- ☐ Sponsorships — если не нужно.

---

## 6. General → Pull requests

**Settings → General → Pull requests**.

- ⦿ **Allow squash merging** (только) — линейная история, проще
  читать `git log`.
- ☐ Allow merge commits — отключить.
- ☐ Allow rebase merging — отключить (или оставить, по вкусу).
- ☑ **Always suggest updating pull request branches**
- ☑ **Allow auto-merge**
- ☑ **Automatically delete head branches** — после merge удаляем
  feature-branch, репо чище.

---

## 7. General → Repository visibility

**Settings → General → Danger Zone**.

- **До защиты диплома**: рекомендую **Private** (никто не видит
  историю, материалы диплома, заметки в `docs/`).
- **После защиты** (если хочешь портфолио): **Public**. Перед этим:
    - Прогнать `gitleaks` по истории (H5 в backlog).
    - Снести `docs/диплом*.docx` и `docs/Презентация*.pptx` из репо
      (см. § 15.1 backlog).
    - Подчистить датированные AI-fingerprints (см.
      [[project-anti-ai-cleanup-backlog]]).

---

## 8. Webhooks (если используешь Cloudflare Tunnel / deploy hooks)

**Settings → Webhooks**.

Проверить:
- Все webhooks имеют **Secret** (HMAC подпись).
- `Content type: application/json`.
- `SSL verification: Enabled`.
- Только нужные events (не **all events**).

---

## 9. Secrets and variables → Actions

**Settings → Secrets and variables → Actions**.

Аудит:
- Какие secrets хранятся? (Кликни на каждый — видно только имя, не
  значение.)
- Если есть `OLD_*`, `DEPRECATED_*`, `TEST_*` — снести.
- Если `CLAUDE_API_KEY` / `STRIPE_LIVE_KEY` / `SENTRY_DSN` старше
  90 дней — ротировать.

---

## 10. После настройки — smoke-test

```powershell
# 1. Push безобидной правки в feature-ветку — проверь, что CI запустился.
git checkout -b smoke/test
echo "test" >> README.md
git add README.md
git commit -m "smoke: проверка CI"
git push -u origin smoke/test

# 2. Открыть PR в GitHub UI → убедиться:
#    - Run checks автоматически запустились
#    - Merge button **заблокирован** пока CI красная
#    - Если CI зелёная — merge становится доступен

# 3. Обратно
git checkout main
git branch -D smoke/test
git push origin --delete smoke/test  # если pushнул
```

---

## Чего НЕ делать

- ❌ **Не отключай** branch protection «временно чтобы быстро запушить
  фикс». Если нужен hotfix — открой PR, дождись CI.
- ❌ **Не давай Actions write-permissions** по умолчанию. Только
  workflow, который явно требует (например, релиз-тэги).
- ❌ **Не клади secrets в workflow.yml**. Только через `Settings →
  Secrets → Actions`.
- ❌ **Не делай force-push в main** даже один раз. История —
  свидетельство для защиты.

---

## Связано

- `docs/SECURITY_BACKLOG.md` § 13 — full GitHub hygiene checklist.
- `.github/dependabot.yml`, `.github/CODEOWNERS`, `.github/workflows/codeql.yml` — уже добавлены commit `d00bcc1`.
- `SECURITY.md` — vuln disclosure policy (commit `d00bcc1`).
- `.pre-commit-config.yaml` — pre-push ruff hook (commit `d00bcc1`).
