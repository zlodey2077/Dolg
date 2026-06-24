# DOLG Project Knowledge Base

Сводный файл проектных решений, истории разработки, аудитов и backlog. Сформирован из разрозненных документов, чтобы в docs оставались только актуальные справочники.

## Состав
- [3D SURFACE REPORT](#3d-surface-report)
- [AI ANSWER QUALITY ANALYSIS](#ai-answer-quality-analysis)
- [CATALOG AUDIT](#catalog-audit)
- [CONTAINERS AND KUBERNETES](#containers-and-kubernetes)
- [CSP NONCE GUIDE](#csp-nonce-guide)
- [DEFENSE PROJECT](#defense-project)
- [DEMO SCENARIO](#demo-scenario)
- [DEVELOPMENT HISTORY](#development-history)
- [DIPLOMA AI DECLARATION DRAFT](#diploma-ai-declaration-draft)
- [DIPLOMA CHAPTER2 DRAFT](#diploma-chapter2-draft)
- [DIPLOMA CHECKLIST](#diploma-checklist)
- [DIPLOMA DEFENSE PREP](#diploma-defense-prep)
- [DIPLOMA GIA AI POLICY](#diploma-gia-ai-policy)
- [DIPLOMA QUESTIONS FOR SUPERVISOR](#diploma-questions-for-supervisor)
- [DIPLOMA UPDATES](#diploma-updates)
- [DOLG Diploma reworked 20260603](#dolg-diploma-reworked-20260603)
- [ENGINES COMPARISON](#engines-comparison)
- [GITHUB SECURITY SETUP](#github-security-setup)
- [INSTRUMENTS PLAN](#instruments-plan)
- [LEGAL RESOURCE MAP 20260526](#legal-resource-map-20260526)
- [MODERATION ROLES](#moderation-roles)
- [NEURAL UPGRADE PLAN](#neural-upgrade-plan)
- [OPENSOURCE GEMS BACKLOG](#opensource-gems-backlog)
- [OPS ALERTING](#ops-alerting)
- [PRODUCT DATA 3D SOURCES](#product-data-3d-sources)
- [SCHEMATIC EDITOR FIXES](#schematic-editor-fixes)
- [SCREENSHOT GUIDE](#screenshot-guide)
- [SECURITY BACKLOG](#security-backlog)
- [SERVER ENGINES INSTALL](#server-engines-install)
- [STARTUP RELIABILITY AUDIT](#startup-reliability-audit)
- [TESTS AND REPORTS](#tests-and-reports)
- [UX FRONTEND AUDIT](#ux-frontend-audit)
- [VISUALIZATION 3D PLAN](#visualization-3d-plan)
- [WORK FRONT 20260619](#work-front-20260619)
- [WOW ANIMATIONS BACKLOG](#wow-animations-backlog)
- [YC DEPLOY](#yc-deploy)

---

## 3D SURFACE REPORT

Источник: `3D_SURFACE_REPORT.md`

# Отчёт: 3D-графики результатов симуляции (готово + проверено)

Реализованы и **проверены в реальном симуляторе** информативные 3D-графики данных. Кнопка
**«📈 3D-поле»** открывает полноэкранный 3D-график с осями, легендой и числовой шкалой.

## Два графика

- **kind=wave (по умолчанию) — «Бегущая волна по LC-линии»**: LC-лестница (линия задержки),
  переходный процесс → поле `[время][узел]`. Видно распространение фронта с задержкой √(LC),
  LC-звон (рябь) и **удвоение напряжения при отражении от открытого конца** (vmax ≈ 2× входа,
  ~10.8 В при входе 5 В). Это «интересный и сложный» график.
- **kind=grid — «Распределение по резисторной сетке»**: сетка N×N, DC → поле `[позиция][позиция]`,
  гладкий потенциальный рельеф (источник→земля).

## Информативность (повышена)

Оси с подписями (**X** = позиция/узел, **Z** = время, **Y** = напряжение В), числовые засечки по
вертикали (мин/середина/макс в В), сетка-пол, осевой бокс, **цветовая легенда-шкала** (градиент +
мин/макс), динамический заголовок и единицы из эндпоинта. Подписи спрайтов — авто-ширина (не режутся).

## Что сделано (в git)

| Слой | Файл | Коммит |
|---|---|---|
| 3D-рендер поверхности | `shop/static/simulation/scheme-3d-surface.js` (`DolgSurface3D`) | 6576bcd |
| Overlay по U/I на плате | `scheme-3d.js` → `setNodeOverlay()` | 6576bcd |
| Эндпоинт поля | `views.py` → `api_simulation_voltage_field` + url | 674c27d |
| Кнопка + модалка | `simulation.html` → `#surface3d-btn` / `showVoltageSurface()` | 674c27d |

## Пайплайн (всё сходится)

```
Xyce/ngspice/MNA  →  large_circuits.generate_resistor_grid_circuit(N)  →  solve_dc
   →  voltage_field (2D-поле)  →  /simulation/api/voltage-field/ (JSON)
   →  DolgSurface3D (Three.js): z=рельеф, цвет=turbo-colormap, OrbitControls
```

## Как работает

Кнопка **«📈 3D-поле»** (рядом с «3D» платы) → `showVoltageSurface()` → fetch поля сетки N×N →
полноэкранная модалка с 3D-поверхностью. Источник в углу = красный пик (V=10), земля в
противоположном = синяя впадина (~0); монотонный градиент = физика. Вращается мышью.

## Проверка (self-check)

- **Эндпоинт:** `GET /simulation/api/voltage-field/?n=10` → 200 JSON, поле 10×10, углы
  V[0][0]=10.0 / V[-1][-1]=2.49 (физика верная).
- **Standalone-демо** (`scripts/make_surface_demo.py` + playwright): сетка 25×25 рендерится
  корректным 3D-рельефом, colormap верный, `surface:ok`, 0 ошибок консоли.
- **В реальном симуляторе** (playwright, залогинено): `DolgSurface3D=True`, кнопка в DOM,
  INFO = «сетка 30×30 · 901 узлов · 1742 элементов», рельеф красный→синий. Скриншот снят.

## Что чинил по ходу (self-check → fix)

- `DisallowedHost` тест-клиента → override `ALLOWED_HOSTS` (артефакт теста, не код).
- **500 `no such column: accounts_userprofile.interface_density`** — незакоммиченная миграция
  параллельной сессии (workspace prefs). Применил `migrate` (`accounts.0006`, `Dolg_APP.0021`).
- Unicode-`print` `×` на cp1251-консоли → UTF-8.
- В тест-сессии поверх рендера всплывали онбординг-тур + cookie-баннер — косметика теста, фича
  под ними работает.

## Осталось (некритично)

- **Анимация по transient**: `DolgSurface3D.update(field)` для морфинга по кадрам готов — привязать
  к плейбек-слайдеру.
- **Overlay по U/I** (`setNodeOverlay`) — код готов, визуальная проверка на открытой 3D-плате с
  результатами.
- Размер сетки кнопки фиксирован (N=30); можно вынести в параметр/слайдер.

---

## AI ANSWER QUALITY ANALYSIS

Источник: `AI_ANSWER_QUALITY_ANALYSIS.md`

# Анализ качества ответов ассистента (полнота, достоверность, калибровка)

Разбор того, как `build_rule_based_reply` собирает ответ, где он силён, где слаб по
**полноте** и **достоверности**, и приоритизированный план улучшений. Грунтовано на коде
`Dolg_APP/services/rule_ai.py`, `ai_retrieval.py`, `ai_algorithms.py` и Ф3-семантике
(`shop/static/ai/dolg-semantic.js`).

## Как ответ строится сейчас

Детерминированный конвейер (без внешнего LLM по умолчанию):

1. **Intent** — `_detect_intent`: подстрочный матч по `KEYWORD_INTENTS` (first-match-wins),
   followup-эвристика реюзает прошлый intent.
2. **План** — `ai_algorithms.plan_for(message, intent)`: для обзорных/диагностических запросов
   несколько движков сразу, иначе план = `[intent]`.
3. **Движки считают числа** — MNA `solve_dc`, Monte-Carlo, RF, формульные. **Числа из движков,
   не из текста** (compute-don't-guess) — ключевая сила по достоверности.
4. **Компоновка секций** — `_compose_reply`: шапка + план + секции под intent.
5. **Grounding** — `build_retrieval_context`: TF-IDF-lite (IDF-вес + диверсификация источников)
   по glossary/статьям/практикумам/каталогу/артефактам/legal.
6. **Семантика (Ф3)** — `dolg-semantic.js`: клиентский нейро-эмбеддинг запроса → косинус по
   `corpus_embeddings.json` → блок «Семантически близкое». **Только в UI-панели симулятора.**

## Сильные стороны (сохранить)

- **Числа верифицируемы**: потенциалы/токи/разбросы из реальных решателей, не галлюцинация.
  Для защиты это главный аргумент — ответы воспроизводимы и проверяемы.
- **Видимый план** (`План проверки (агент)`) — ReAct-трассируемость: видно, какие движки прогнаны.
- **Grounding с источниками**: `context_sources` + ссылки на статьи/глоссарий.
- **Штатная деградация**: нет модели/сети → серверный TF-IDF остаётся.

## Слабые места

### Полнота

1. **Intent — first-match-wins по подстроке** (`_detect_intent`, `KEYWORD_INTENTS`).
   Чувствителен к порядку списка; запрос, попадающий в 2+ интента, берёт первый. Нет скоринга,
   нет синонимов/транслита/опечаток. Перефраз вне ключевиков уходит в `fix_plan`/`overview` →
   ответ не по вопросу.
2. **Семантика Ф3 не кормит тело ответа.** Клиентский косинус живёт отдельным UI-блоком и НЕ
   попадает в серверный `_compose_reply`/grounding. Сам ответ остаётся лексическим (TF-IDF).
3. **Корпус мал**: glossary ≈24 термина; в `export_ai_corpus` срез `articles[:200]`,
   `lessons[:200]`, `tasks[:300]`. Тонкая база → бедный grounding на широких вопросах.
4. **Память диалога поверхностная**: followup = реюз `last_intent` + строковый `session_summary`.
   Нет структурного состояния (сущности, ссылки на компоненты/узлы между репликами).
5. **Таксономия интентов закрытая**: нет общего `general_qa`-фолбэка, который при слабом матче
   опирался бы на retrieval сильнее, чем на шаблон секций.

### Достоверность

1. **Confidence не калибрована** (`_confidence`): фикс-бакеты 0.55/0.72/0.86 по числу evidence
   (компоненты/связи/findings/измерения/симуляции). Не зависит ни от качества retrieval, ни от
   того, посчитали ли движки реально, ни от уверенности роутинга. Неверный intent всё равно
   покажет 0.72/0.86.
2. **Нет провенанса по claim'ам**: `context_sources` перечислены общим списком, но конкретные
   утверждения в теле не привязаны к сниппету. Читатель не видит, что из проекта, что из
   источника, что — общее знание.
3. **Порог семантики 0.35 произволен** (`dolg-semantic.js`). У multilingual-MiniLM косинусы
   несвязанных текстов часто 0.3–0.5 → слабые совпадения попадут в «близкое».
4. **Нет проверки согласованности** ответа с retrieved-сниппетами (NLI/grounding-verify) — текст
   может утверждать сверх того, что подтверждено числами/источниками.
5. **Glossary-алиасы по подстроке** (multi-word) могут ложно срабатывать на коротких токенах.

## План улучшений (приоритизирован)

### P0 — дёшево, до защиты

- **Кормить Ф3-семантику в ответ.** Клиент считает эмбеддинг (только он умеет) → шлёт top-K
  сниппеты как `client_context` в `/api/ai/chat/` → `rule_ai` мёржит в `retrieval_context`.
  Тогда тело ответа выигрывает от семантики, а не только боковой блок. *(Серверной семантики
  без эмбеддера нет — это и есть Python-wheel-блокер §AJ; клиент→сервер обходит его.)*
- **Калибровать confidence**: учитывать (а) реально ли движки вернули числа, (б) top-score и
  число grounded-источников retrieval, (в) силу intent-матча. Добавить «неуверенную» полосу с
  хеджированием формулировок.
- **Скоринг интента** вместо first-match: считать число попаданий ключевиков на intent, брать
  максимум; добавить базовые синонимы/транслит; ввести `general_qa`-фолбэк (retrieval-heavy).

### P1

- **Расширить корпус**: glossary 24→100+; поднять срезы статей/уроков; добавить факты из
  datasheet'ов компонентов. Больше grounded-базы = полнее ответы.
- **Inline-провенанс**: привязать секции/утверждения к меткам источников (число — `движок`,
  факт — `источник`, иначе — `общее знание`).
- **Guard согласованности**: помечать в ответе claim'ы, не подтверждённые ни числом, ни сниппетом.

### P2

- **Эмпирически откалибровать порог семантики** (выборка запросов, разделимость косинусов,
  возможно — порог на источник).
- **Reranker** (cross-encoder) — позже клиентским ONNX (Python-wheel-блокер).
- **Структурная память диалога**: сущности/узлы/последняя схема между репликами, не строка-сводка.

## Что трогать не нужно

- Слой движков (MNA/MC/RF) — он и даёт достоверность; улучшения касаются роутинга, grounding'а и
  подачи уверенности, не самих расчётов.

---

## CATALOG AUDIT

Источник: `CATALOG_AUDIT.md`

# Аудит каталога — баги, ошибки, состояние (2026-06-22)

Полная проверка по запросу: данные, медиа, runtime, визуал. Итог: **функциональных багов/ошибок
не найдено**; каталог рабочий и чистый. Главный недостаток — низкое покрытие РЕАЛЬНЫМИ фото
(чинится новым пайплайном). Ниже — что проверено и что осталось.

## ✅ Чисто (проверено)

| Проверка | Результат |
|---|---|
| **Целостность данных** (`check_data_integrity`) | OK — критичных несоответствий нет. 364 товара, 227 РЭБ, 23 категории, 22 статьи, 12 demo-проектов |
| **Качество медиа** (`audit_catalog_media_quality`) | Все 364 картинки валидны: средний score **100**, **0** битых/пустых/нечитаемых, **0** perceptual-дублей |
| **Runtime** (playwright, 6 страниц) | Индекс, категория, категория+фильтр (manufacturer), категория+фильтр (spice), карточка товара, поиск (кириллица) — **0 console-ошибок, 0 pageerror, 0 битых static (404/500)** |
| **Визуал** | Сетка карточек ровная, UGO-арт чистый (резистор с полосами и т.п.), название/рейтинг/параметры/цена/доставка на местах |

## ⚠️ Главный недостаток: покрытие реальными фото

- **Реальных фото только 21.7%** (79 verified / 285 сгенерированных UGO).
- Категории с **0% реальных фото:** `modules` (0/35), `monitors` (0/4), `tools` (0/25).
- Низкое: `resistors` 6%, `inductors` 8%, `ics` 15%, `connectors` 15%, `capacitors` 22%.
- **Не баг, а контент-пробел.** UGO-генерация валидна и выглядит аккуратно, но это заглушки, не фото.
- **Решение (готово, commit b78f1ac):** `python manage.py fetch_product_photos` — мульти-источниковый
  поиск (official-CDN → Nexar/Octopart → LCSC) + гейт качества; генерация осталась fallback.
  Нужен интернет + (опц.) Nexar-ключ. Сначала `--dry-run` посмотреть кандидатов.

## 🔧 Мелочи кода (латентные, не runtime-баги)

- **SVG-рассинхрон** в `shop/services/product_images.py`: `find_local_product_asset` берёт только растр
  (.png/.jpg/.jpeg/.webp), но `is_local_product_svg_asset` / `is_allowed_product_image` ссылаются на
  SVG — мёртвая/несогласованная SVG-ветка. Почистить (либо включить SVG в выбор, либо убрать SVG-хелперы).
- `OFFICIAL_CDN_PHOTOS` в photo_sources пока узкий (4 slug) — расширять курируемыми CDN-URL
  (Mouser/Digikey/TI/SparkFun) или подключить DigiKey API (см. docs/PRODUCT_DATA_3D_SOURCES.md).

## Рекомендации (приоритет)

1. **Прогнать `fetch_product_photos`** (с интернетом, Nexar-ключ) → поднять реальное покрытие; начать
   с категорий 0% (modules/monitors/tools) и крупных (resistors 78 шт.).
2. Прикрутить **RemBG + ImageMagick/Wand** пост-обработку фото (единый белый фон) — фото-качество.
3. Почистить SVG-рассинхрон в product_images.
4. Расширить official-CDN список / добавить DigiKey источник.

**Вывод:** каталог технически здоров (0 багов/ошибок/битых), готов к защите. Единственное «к улучшению» —
реальные фото вместо UGO-заглушек, и инструмент для этого теперь есть.

---

## CONTAINERS AND KUBERNETES

Источник: `CONTAINERS_AND_KUBERNETES.md`

# Containers and Kubernetes runbook

This project now has three container layers:

- Docker Desktop bootstrap for Windows.
- Docker Compose for local/prod-like runs.
- Kubernetes manifests in `deploy/k8s` for Docker Desktop Kubernetes, kind,
  minikube, or a small cluster.

## 1. Windows Docker Desktop

Check the current machine:

```powershell
docker version
docker compose version
kubectl version --client
```

If `docker version` shows a client but cannot connect to
`npipe:////./pipe/docker_engine`, start the Windows service and Desktop app:

```powershell
scripts/bootstrap_docker_desktop.ps1 -StartVisible
```

If the script relaunches with UAC, accept it. Docker Desktop service start is a
Windows admin operation; a non-admin shell cannot complete that part. After the
first successful start, normal project commands should work from the usual
terminal.

## 2. Docker Compose local run

From the repository root:

```powershell
scripts/docker_compose_up.ps1
```

The script creates ignored local secrets in `deploy/.env.docker.local`, validates
the compose file, builds the image, starts Postgres/Redis/Django/nginx/
Prometheus/Grafana, and waits for `/healthz`.

To only create the local env file and validate Compose without a running Docker
daemon:

```powershell
scripts/docker_compose_up.ps1 -ConfigOnly
```

URLs:

- App: `http://localhost:8080/`
- Prometheus: `http://localhost:9090/`
- Grafana: `http://localhost:3000/`

Stop:

```powershell
scripts/docker_compose_down.ps1
```

Stop and remove volumes:

```powershell
scripts/docker_compose_down.ps1 -Volumes
```

## 3. Kubernetes local run

One-command local flow:

```powershell
scripts/k8s_local_up.ps1
```

The script validates Kubernetes manifests, builds `dolg:local`, applies
`deploy/k8s`, waits for the migration Job and rollouts, then prints the current
pods/services/PVCs.

Open the app through port-forwarding:

```powershell
kubectl -n dolg port-forward svc/dolg-nginx 8080:80
```

Then open `http://localhost:8080/`.

To start the port-forward inside the same foreground script run:

```powershell
scripts/k8s_local_up.ps1 -PortForward
```

For kind, load the image before applying:

```powershell
scripts/k8s_local_up.ps1 -KindCluster <cluster-name>
```

Stop Kubernetes objects:

```powershell
scripts/k8s_local_down.ps1
```

Stop workloads but keep PVC data:

```powershell
scripts/k8s_local_down.ps1 -KeepPvcs
```

## 4. Static checks

These do not require a live Docker daemon:

```powershell
python scripts/check_docker_static.py
python scripts/check_k8s_static.py
docker compose --env-file deploy/.env.docker.local -f deploy/docker-compose.yml config
```

`docker compose config` requires the env file because production-like compose
fails fast on missing secrets.

## 5. Production notes

- Do not use `deploy/.env.docker.local` outside local smoke runs.
- Replace Kubernetes `secretGenerator` literals with a real secret supply:
  external Secret, SealedSecret, SOPS, cloud secret manager, or CI/CD injection.
- Replace `dolg:local` with an immutable registry tag.
- Keep `METRICS_TOKEN` synchronized between Django and Prometheus.
- Run migrations as an explicit release job before scaling web replicas.
- The base namespace enforces Pod Security `baseline` and warns/audits
  `restricted`. Workloads drop Linux capabilities and use `RuntimeDefault`
  seccomp.
- Django pods run as uid/gid `1000`, mount writable PVCs through `fsGroup`, and
  use startup/readiness/liveness probes.
- Prometheus reads `METRICS_TOKEN` through a mounted Kubernetes Secret file,
  not a literal token in the Prometheus ConfigMap.
- `dolg-web` has a PodDisruptionBudget so voluntary disruptions keep at least
  one web replica available.
- `deploy/k8s/networkpolicy.yaml` starts with default-deny and opens only the
  DOLG flows needed for nginx, Django, ASGI, Postgres, Redis, Prometheus, and
  Grafana.

## 6. What remains

- OS/runtime: start `com.docker.service` through UAC/admin once and confirm
  `docker info` returns the server version.
- If Docker Desktop hangs while the Docker service is stopped or `vmcompute` is
  stopped, run `scripts/bootstrap_docker_desktop.ps1 -StartVisible` and accept
  the UAC prompt. The bootstrap checks WSL, `vmcompute`, `hns`,
  `LxssManager`, `docker-users`, and the Docker Desktop service.
- Runtime smoke: run `scripts/docker_compose_up.ps1` and verify the app,
  Prometheus, and Grafana URLs.
- Kubernetes smoke: enable Docker Desktop Kubernetes or use kind/minikube, then
  run `scripts/k8s_local_up.ps1`.
- Production hardening: replace local literals with a real secret manager,
  publish immutable images to a registry, add Helm values per environment,
  move from Pod Security `baseline` to `restricted` after runtime smoke, and
  document Postgres backup/PITR.

## 7. Внешние материалы для самообучения (DevOps/SRE, на будущее)

Справочный список — не часть рабочего пайплайна, а ориентир для прокачки по
инфраструктуре. Приоритет низкий (после защиты); полезно, когда дойдём до
реального деплоя «комбайна» (серверная симуляция на Xyce, headless 3D-CAD в
контейнере, очередь Celery+Redis).

- **Локальный Kubernetes без облаков** (Flant, Habr) — поднять k8s локально без
  Yandex/Cloudflare. URL в дампе обрезан (`habr.com/ru/companies/flant/arti…`),
  при необходимости найти полную статью по блогу Flant. Прямо релевантно нашему
  `deploy/k8s` + Docker Desktop/kind/minikube.
- **Инфраструктура как код (IaC), практики для DevOps** —
  <https://bookflow.ru/infrastruktura-kak-kod-praktiki-dlya-devops-inzhenerov/>.
  Terraform и принципы покрытия инфраструктуры кодом.
- **5 GitHub-репозиториев для роста в DevOps:**
  - How they SRE — `github.com/upgundecha/howtheysre` (как крупные компании практикуют SRE).
  - Awesome Scalability — `github.com/binhnguyennn/awesome-scalability` (паттерны масштабируемых систем).
  - DevOps Exercises — `github.com/bregman-arie/devops-exercises` (Linux, k8s, Terraform, Prometheus, Docker и вопросы для интервью).
  - Test your sysadmin skills — `github.com/trimstray/test-your-sysadmin-skills` (Linux sysadmin Q&A).
  - Awesome SRE — `github.com/dastergon/awesome-sre` (подборка ресурсов по надёжности).

> Имена репозиториев восстановлены из обрезанных ссылок дампа — перед
> использованием сверить точный путь на GitHub.

---

## CSP NONCE GUIDE

Источник: `CSP_NONCE_GUIDE.md`

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

---

## DEFENSE PROJECT

Источник: `DEFENSE_PROJECT.md`

# DOLG - отдельный проект защиты и допуска

Статус: отложено. Не трогать в текущем проектном потоке, пока не будет явного
запроса вернуться к защите, допуску, презентации или ВКР-документу.

Этот файл вынесен из `docs/WORK_FRONT_20260619.md`, чтобы основной фронт работ
оставался только про продукт, код, инфраструктуру и проектные улучшения.

## Цель

К дате защиты, указанной в рабочих материалах как 26 июня 2026, подготовить
документ, допуск, презентацию и стабильный демонстрационный маршрут.

## Дипломный Word-документ

- Вставить готовые блоки из `docs/DIPLOMA_UPDATES.md`: объект, предмет, методы, формулы для 2.6.
- Довести основной текст до требования из чек-листа: минимум 40 страниц, параграфы главы 2 - не короче 4 страниц.
- Заменить цифры во всех местах: товары, категории, статьи, материалы, тесты, AI-шаблоны.
- Перенумеровать приложения и рисунки цифрами, проверить подписи и источники.
- Подготовить титульный лист, задание, последний лист, подписи, файл по требуемому имени.

## Антиплагиат и ИИ

- Получить у научрука точный формат проверки и декларации.
- Использовать `docs/DIPLOMA_AI_DECLARATION_DRAFT.md` как черновик, но финальную формулировку согласовать.
- Снизить AI-след в тексте вручную: переписать очевидно сгенерированные абзацы, не запускать repo scrub без явной команды.

## Защита и демо

- Собрать презентацию на 15-20 слайдов: проблема, архитектура, схема->симуляция->BOM, AI/review, 3D/PCB, тесты, безопасность, развитие.
- Пройти `docs/DEMO_SCENARIO.md` вживую: короткий 3-5 мин и полный 7-10 мин маршруты.
- Переснять скриншоты по `docs/SCREENSHOT_GUIDE.md`.
- Заготовить ответы комиссии из `docs/DIPLOMA_DEFENSE_PREP.md`, особенно про ngspice/Xyce, AI, Canvas2D/WebGL, безопасность и "почему не полноценный production CAD".

## Когда возвращаться

Возвращаться к этому файлу только по прямому запросу: "заняться защитой",
"подготовить ВКР", "собрать презентацию", "проверить допуск" или похожему.

---

## DEMO SCENARIO

Источник: `DEMO_SCENARIO.md`

# DEMO_SCENARIO: сценарии показа DOLG

## Короткий сценарий, 3-5 минут

1. Открыть `/demo/`.
2. Показать маршрут: каталог -> энциклопедия -> лаборатория -> CAD -> симуляция -> BOM -> заказ.
3. Открыть товар с локальным generated-изображением и параметрами, например `TL072CDR`, `L7805CV`, `TX2-5V` или `Bourns 3386P`.
4. Открыть связанную статью с материалами и показать легальные источники: open textbook / official docs, а не скачанные архивы.
5. Открыть `/knowledge/lab/` и показать расчет стабилизатора или NE555 с инженерной оценкой.
6. Перейти в CAD и показать DRC/BOM/CAD -> SIM.
7. На результатах симуляции показать Pro-аналитику: FFT-спектр, Signal quality (THD/SINAD/ENOB), Bode plot, What-if sweep или Monte Carlo tolerance.
8. Открыть `/projects/`, нажать `Review` у демо-схемы и показать `Design Health Score`, NetworkX-топологию схемы, expert findings с `rule_id/evidence/recommendation`, fuzzy-risk, fault-сценарии, рекомендации и PDF-экспорт.
9. В симуляции сформировать BOM и перейти к корзине.

## Сценарий Media Quality Gate

1. Запустить `python manage.py check_data_integrity --json`.
2. Показать блок `catalog.media_quality`: 89 изображений проверены, `average_score=100`, `error_count=0`, `warning_count=0`, `imagehash_available=true`.
3. Объяснить, что активный каталог не берет изображения напрямую из Wikimedia/Commons: реальные фото сначала вручную/командой переносятся в `products/verified/`, а плохие кандидаты остаются на SVG/generated fallback.
4. Для защиты можно показать тестовый принцип: tiny/blank локальное изображение получает `image_too_small` и `image_near_blank`, а проверенное фото или generated PNG проходит gate.

## Сценарий Legal Knowledge Corpus

1. Запустить `python manage.py seed_legal_sources` после `populate_knowledge`.
2. Открыть `/knowledge/` и статью `Открытые источники и документация DOLG`.
3. Показать, что источники разделены по темам: электроника, CAD/SPICE, backend, graph/formula/unit stack, constraints, risk и AI.
4. Открыть одну профильную статью, например про закон Ома или RC-цепи, и показать блок материалов с All About Circuits/OpenStax/ngspice.
5. В `/search/?q=ngspice` или `/search/?q=PyTorch` показать отдельную группу `Источники и документация`; в header autocomplete показать suggestion типа `legal_source`.
6. Открыть `/knowledge/learning/` и урок из track `Практика по открытым инженерным источникам`: задания показывают `Материалы для проверки`, а rubric хранит `source_ids/source_topic/teacher_rule`.
7. В AI-панели задать вопрос `почему нужен GND?`: self-hosted ответ должен сослаться на review finding и legal sources в блоке `Опираюсь на`.
8. В `check_demo_ready --json` показать блок `legal_sources_stack`: `source_retrieval`, `rule_bibliography`, `search_smoke`, `learning_tasks_with_sources`, `training_examples_with_sources`.
9. Объяснить политику: внешние подборки книг используются как список тем, а DOLG работает с официальными docs, открытыми учебниками, datasheet, demo-проектами и opt-in схемами пользователей.

## Сценарий нового этапа: import -> review -> обучение

1. В `/search/?q=LTspice` показать, что глобальный поиск находит `CAD Import to Review`.
2. Открыть `/cad/`, загрузить `.cir/.net/.asc` или вставить простую SPICE-схему: `V1 in 0 DC 5`, `R1 in out 1k`, `R2 out 0 2k`, при необходимости добавить `.ac dec 10 1 1k`.
3. Показать боковую панель import preview: распознанные компоненты, узлы, GND, неподдержанные элементы, analysis directives и инженерные предупреждения.
4. Нажать `Сохранить проект + review`: DOLG создает `SchematicProject`, строит `ProjectReview` и открывает отчет.
5. В review показать DRC/ERC, наличие GND/источника, BOM risk, derating, topology metrics, floating nodes, expert rule findings, рекомендации и блок `Практика по результатам review`.
6. Показать, что схема распознана как делитель: есть связная компонента, путь до GND и output node; если убрать GND, graph-layer сразу дает предупреждение, а Learning-by-review предлагает урок по диагностике GND.
7. Перейти из карточки Learning-by-review в `/knowledge/learning/` и показать track `Диагностика простых схем`: ошибка схемы превращается в практическое задание.
8. В учебной задаче показать SymPy-проверку формулы делителя и SVG-схему, сгенерированную Schemdraw для отчета/урока.
9. В AI-чате без внешнего ключа показать self-hosted reply: помощник объясняет ошибку по `Expert trace`, данным review, graph metrics и предлагает план проверки.
10. Задать три разных вопроса, чтобы показать, что это не одна заглушка: `почему нужен GND?`, `что измерить и как сравнить expected vs measured?`, `что делать с BOM?`. В ответе должны появиться режим, уверенность и быстрые действия.

## Сценарий expert-first: правило -> расчет -> рекомендация

1. Открыть `/search/?q=rule-engine` или `/search/?q=z3` и показать, что глобальный поиск уже знает про новый экспертный слой.
2. В `/projects/` запустить Review для схемы без GND или с неподходящим номиналом.
3. В отчете показать finding: `rule_id`, severity, evidence, recommendation и confidence.
4. Пояснить, что Pint приводит `10k`, `6.8kOhm`, `2.5мА`, `100нФ`, `В/Ом/Гц` к единым числам, поэтому лаборатория, review и обучение не спорят о единицах.
5. Показать constraint-подбор как backend-сценарий: Z3 возвращает допустимые варианты делителя/LED-резистора/RC, а не одно "магическое" число.
6. Показать `check_demo_ready --json`: блок `neural_stack` подтверждает PyTorch `2.12.0` и обученную tiny-модель.
7. Пояснить neural roadmap: PyTorch уже подключен как optional deep-hints слой, но финальный инженерный verdict остается за expert review и человеком.

## Сценарий Self AI V2 и PyTorch deep-hints

1. Открыть `/simulation/`, раскрыть AI-панель и показать карточку "Разбор схемы": topology, score, GND/source, DRC/ERC, BOM и measurements.
2. Нажать quick action "Разобрать схему" и показать, что чат получает structured intent, context sources и session summary.
3. Переключиться на вкладку "Объясни" и задать follow-up: "а почему?" — помощник должен сохранить прошлый intent и отвечать в том же контексте.
4. Запустить `DOLG_AI_BACKEND=neural` для демо deep-hints и показать в pipeline explain `deep_hint`: topology confidence, risk score, trained=true.
5. Объяснить ограничение: PyTorch модель дает вероятностную подсказку, а DRC/ERC, expert rules и человек остаются контрольным слоем.

## Сценарий Pro-аналитики: расчет -> спектр -> запас

1. Войти пользователем с Pro-подпиской или включить demo Pro через админку.
2. Запустить TRAN-сценарий и отправить массив отсчетов на `/simulation/api/pro/fft/`; показать SVG FFT и найденную пиковую частоту.
3. Для RC-фильтра вызвать `/simulation/api/pro/bode/`; показать Bode plot и частоту среза около -3 дБ.
4. Для делителя или RC-цепи вызвать `/simulation/api/pro/monte-carlo/`; показать разброс результата при допусках компонентов.
5. Нажать `Сохранить измерение`: ключевая Pro-метрика попадает в `ProjectMeasurement` проекта и дальше может участвовать в review/обучении.
6. Открыть `/projects/api/<id>/simulation-runs/stats/` и показать Pandas-агрегацию: самые медленные запуски и среднее время по типам анализа.
7. Если браузерный расчет не проходит, показать `/simulation/api/fallback-solve/` на простой R/V/GND-схеме: серверный NumPy MNA возвращает напряжения узлов. Для Free этот endpoint показывает `plan_required=pro`, для Pro/Enterprise выполняет расчет.

## Сценарий тарифов и AI-балабола

1. Открыть `/billing/` и показать три уровня: Free, Pro, Enterprise.
2. Free: в `/simulation/` показать заблокированную Pro-аналитику и ответ API `plan_required`.
3. Pro: активировать trial/mock Pro, открыть AI-панель, показать счетчик токенов, `session_summary`, карточку "Разбор схемы" и pipeline-кнопки `Объясни схему` / `След. компонент`.
4. Enterprise: открыть `/orgs/<slug>/`, показать plan `ENTERPRISE`, командные роли, audit/API/approval flags и объяснить, что AI может учитывать проектный контекст команды.
5. Подчеркнуть ограничение: PyTorch deep-hints и AI-подсказки не являются финальным инженерным verdict; последнее решение остается за expert rules и человеком.

## Полный сценарий, 7-10 минут

1. Открыть `/search/?q=TL072` или `/search/?q=NE555` и показать глобальный поиск.
2. Открыть карточку товара и вкладки с техническими данными.
3. Открыть статью энциклопедии с вложенными материалами.
4. В инженерной лаборатории рассчитать NE555, стабилизатор или тепловой запас и показать статус `норма/риск/перегрев`.
5. Открыть `/knowledge/learning/` и показать маршрут "Прикладные узлы электроники", где те же расчеты превращены в задания; для математического задания показать SymPy-объяснение шага формулы.
6. В CAD показать smart wiring, net labels, GND, DRC и A3-экспорт.
7. Передать схему в симулятор.
8. Запустить расчет и показать график/предупреждения/BOM, затем открыть review и показать topology metrics схемы.
9. Запустить один Pro-расчет: FFT для осциллографа или Bode plot для AC.
10. Массово добавить BOM в корзину и перейти к оформлению заказа.

## Запасной сценарий

Если ручная сборка не нужна, открыть `/projects/`, выбрать готовую демо-схему и загрузить ее в симулятор. Перед показом проверить проект командой:

```powershell
.venv\Scripts\python.exe manage.py check_demo_ready
.venv\Scripts\python.exe manage.py check_data_integrity --json
```

---

## DEVELOPMENT HISTORY

Источник: `DEVELOPMENT_HISTORY.md`

# DOLG - история развития проекта

Этот файл заменяет старые roadmap/backlog/исследовательские черновики. Активный
фронт работ теперь ведётся отдельно в `docs/WORK_FRONT_20260619.md`.

Правило пополнения: сюда добавляются только закрытые этапы, принятые решения и
сжатые выводы после завершения задач. Новые незакрытые задачи не распылять по
отдельным Markdown-файлам, а сначала заносить в рабочий фронт.

## Текущее разделение документов

- `docs/WORK_FRONT_20260619.md` - единственный живой список работ.
- `docs/DEVELOPMENT_HISTORY.md` - история решений, закрытых этапов и поглощённых идей.
- `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/LOCAL_SETUP.md`, `docs/RUNBOOK.md`, `docs/DEPLOY.md` - справочники, которые обновляются по факту изменения системы.
- Дипломные файлы (`DIPLOMA_*`, `DEMO_SCENARIO.md`, `SCREENSHOT_GUIDE.md`) живут отдельно, потому что это не backlog, а материалы защиты.

## Хронология

### Апрель 2026 - базовый контур платформы

- Сформирован Django-проект с приложениями `shop`, `accounts`, `orders`, `knowledge`, `Dolg_APP`.
- Добавлены каталог, корзина, заказы, профили, базовые страницы магазина.
- Появились первые тесты для проектов схем, API, заказов, поиска, BOM и симуляционных квот.
- Схемный редактор получил сохранение проектов, версии, гостевой demo-режим, DRC, PDF/SVG export.
- Начат переход от "магазина компонентов" к платформе проектирования: схема, симуляция, BOM и заказ в одном маршруте.

### Май 2026 - инженерное ядро

- Добавлен scientific stack: NumPy, SciPy, Matplotlib, Pandas, FFT, Bode, Monte Carlo, signal quality, parameter sweep и серверный DC fallback.
- Сформирован expert-first review: правила, единицы, Z3 constraints, fuzzy-risk, fault library, derating, legal sources и PDF/HTML review.
- Добавлен импорт инженерных артефактов: LTspice/SPICE subset, KiCad subset, preview и learning-by-review.
- Создан self-hosted AI слой: rule-based assistant, intent modes, quick actions, context sources, session summary.
- Подключён tiny PyTorch backend как вероятностная подсказка, но final verdict остаётся за экспертными правилами.
- Создан legal knowledge corpus: открытые учебники, официальная документация, datasheet evidence, источники для правил и обучения.
- Каталог получил media quality gate, verified/generated images, запрет случайных Wikimedia/Commons fallback, datasheet intelligence baseline.
- Добавлены роли, тарифы Free/Pro/Enterprise, quota/entitlement слой, MLJob и staff ops dashboard.

### Конец мая - начало июня 2026 - качество, безопасность, данные

- Расширена ML-цепочка: `AITrainingExample`, curated schemes, normalize metadata, import/promote datasets, tiny model retraining.
- Добавлены staff/admin операции для ML, dataset curation и ops snapshot.
- HIGH-tier security backlog закрыт: основные CRUD/IDOR/secret/CSP/HSTS/axes/Sentry проблемы переведены в resolved baseline.
- Остаточный security фронт перенесён в medium/post-defense: rate limits, GDPR, upload validation, JSON body limits, log scrubbing, SBOM, K8s/Vault/Helm.
- Сформирован demo-ready слой: `check_demo_ready`, `check_data_integrity`, smoke tests, screenshot guide, demo scenario.

### Июнь 2026 - предзащита и консолидация

- Сформирован единый предзащитный приоритет: сначала документ, презентация, демо-маршрут и стабильность, затем low-risk вау-фичи.
- Подготовлены блоки для ВКР: объект, предмет, методы, формулы, глава 2, декларация ИИ, ответы комиссии.
- Собран текущий фронт работ `WORK_FRONT_20260619.md`, который заменяет старые scattered roadmap/backlog документы.
- Установлен и проверен pytest в `.venv`; корректная команда запуска: `.\.venv\Scripts\python.exe -m pytest`.
- Добавлен каталог серверных движков: Xyce, PySpice, GnuCap, OpenModelica, GNU Radio, Sigrok, OpenFPGA/OpenROAD, Zephyr, OpenWrt и другие.
- Сформирован router profile: Xyce как основной кандидат для серверной симуляции, PySpice как Python bridge, ngspice.wasm как интерактивный браузерный режим, NumPy/MNA как fallback.
- Настроен VS Code workspace-слой: рекомендованные расширения для Django/Python/Ruff/Docker/Kubernetes/YAML/SQL, tasks для pytest/Django/Docker/K8s/SQL/frontend, debug-конфиги, YAML schema associations и `scripts/check_vscode_stacks.ps1` для диагностики стеков с timeout.

## Принятые архитектурные решения

### Симуляция

- До защиты основной пользовательский путь остаётся клиентским: `ngspice.wasm` + JS/NumPy fallback.
- Серверный слой развивать через job API и отдельные worker-процессы, а не через тяжёлые CLI-вызовы внутри Django request.
- Основной будущий серверный SPICE-кандидат - Xyce. PySpice использовать как Python adapter/bridge, GnuCap как лёгкий fallback для mixed-signal/educational cases.
- Для внешних движков целевая форма - Docker image + REST contract + async jobs + artifacts.

### AI/ML/RAG

- AI не должен быть финальным инженерным авторитетом: числа и verdict берутся из движков, правил и расчётов.
- Tiny PyTorch/GNN/semantic search дают подсказки и ранжирование, но не отменяют expert-first review.
- До Postgres миграции RAG держится на TF-IDF/hybrid retrieval. pgvector, GraphRAG и reranker - post-defense.
- Transformers.js/ONNX Runtime Web - хороший путь для браузерной семантики без Python wheel blockers.

### CAD/PCB/3D

- Ценность DOLG не в копировании KiCad/AutoCAD, а в учебном web-flow: схема -> проверка -> симуляция -> BOM -> PCB/3D -> отчёт.
- Сначала нужен one-click pipeline и headless PCB DRC, затем полноценный PCB editor.
- 3D остаётся view над данными проекта, а не отдельным источником истины.
- GLB подходит для ближайших 3D-компонентов; STEP/IDF/CadQuery/OpenCASCADE - post-defense server-worker слой.
- ЕСКД-активы должны быть registry-driven и валидируемыми, а не свободно генерируемыми AI.

### Инфраструктура

- Локальная защита может жить на SQLite/ngspice.wasm/Cloudflare Tunnel.
- Production path: PostgreSQL, Docker Compose, nginx/gunicorn, Redis/Celery, мониторинг, backups.
- Kubernetes нужен после стабилизации runtime: Deployments/Services/Ingress сначала, Helm/Vault/HPA позже.
- Docker/K8s для серверных движков должны быть отдельным контуром, чтобы не тащить Xyce/OpenModelica/GNU Radio в web image.

## Отложенные идеи, которые не потеряны

### Server engines

- Xyce/PySpice сделать первым реальным worker MVP.
- Дальше подключать GnuCap, OpenModelica, Sigrok, GNU Radio, OpenFPGA/OpenROAD, Zephyr/OpenWrt как task-specific workers.
- Для TINA-TI/MapleSim учитывать лицензии: не включать в основной open-source runtime, держать как optional registered worker.

### Simulator/editor

- Logic engine для AND/OR/NOT/NAND/NOR/XOR, truth table и СДНФ.
- Wire-router L-route с обходом компонентов и wire-merge.
- Undo/redo fix для `setCompField()`.
- DRC dedup: GND warning должен приходить из одного источника.
- Virtual scope polish: V/div, time/div, trigger.

### PCB/3D

- One-click схема -> PCB -> 3D.
- IPC-2221 DRC: clearance, current width, decoupling distance, ground split.
- Realistic board: copper, soldermask, silkscreen, 45-degree routing, env-map.
- GLTF/GLB components, enclosure, STL/STEP export.

### CAD/ECAD

- Arrays, blocks, ortho/snap/polar/object snap.
- ЕСКД asset registry and validator.
- Symbol/footprint editor, multi-section components, buses, hierarchical sheets.
- Bidirectional schematic<->PCB sync и functional blocks.

### AI/ML/Data

- GNN train+bench на Open Schematics/Masala-CHAI/AnalogGym с лицензионным фильтром.
- ML-curation UI: queue, soft-delete, quality flags, promote/exclude.
- DatasetSource registry.
- RAG Phase A: better chunking, hybrid retrieval, glossary, citations.
- Post-defense: pgvector, GraphRAG, reranker, multimodal photo-to-schematic, voice/TTS.

### Product/catalog

- Favorites/bookmarks.
- Project cart: заказ связан со схемой/BOM.
- Project export as zip.
- Comments + moderation.
- Datasheet intelligence: pinout, absolute max, thermal, typical circuits.
- `rembg`/U2Net для чистого фона изображений.

### Security/ops

- Permission audit для ML/admin/API.
- Stripe webhook signature.
- Tier-aware rate limits.
- JSON body-size limits.
- Upload MIME/size validation.
- Log scrubbing, PII inventory, GDPR export/delete.
- SBOM/license audit, Dependabot/CodeQL, container scan.

## Поглощённые документы

Смысл этих файлов перенесён сюда и в `WORK_FRONT_20260619.md`; сами файлы можно не восстанавливать:

- `docs/AI_ASSISTANT_UPGRADE_PLAN.md`
- `docs/ARTIFACT_INGESTION_DEMO.md`
- `docs/AUTOCAD_AI_CODEGEN_PLAN.md`
- `docs/CAD_HARD_UPGRADE_PLAN.md`
- `docs/CHANGELOG.md`
- `docs/ENGINEERING_NOTES.md`
- `docs/ESKD_CERTIFIED_ASSET_PLAN.md`
- `docs/EXTERNAL_RESOURCES_INSPIRATION_20260602.md`
- `docs/FUNCTIONAL_BACKLOG_20260605.md`
- `docs/LECAD_LITHIUM_ECAD_RESEARCH_TODO_20260531.md`
- `docs/LITHIUM_ECAD_ANALYSIS.md`
- `docs/LITHIUM_INSPECTION_REPORT.md`
- `docs/MASTER_BACKLOG_20260605.md`
- `docs/PIPELINE_SCHEMATIC_TO_3D_PLAN.md`
- `docs/PRE_DEFENSE_REMAINING_20260614.md`
- `docs/PRE_DEFENSE_WOW_20260613.md`
- `docs/PROJECT_IMPROVEMENTS_20260614.md`
- `docs/REMAINING_WORK_20260615.md`
- `docs/RESTART_HANDOFF_20260609.md`
- `docs/SIM_3D_MODELS_PLAN.md`
- `docs/SERVER_ENGINE_ROUTER_PLAN.md`
- `docs/TRANSFORMERS_JS_SEMANTIC_PLAN.md`
- `docs/UNIFIED_ROADMAP_20260606.md`
- `docs/VIDEO_BACKLOG.md`
- `knowledge/notes/3d_priorities.md`
- `knowledge/notes/3d_research.md`
- `knowledge/notes/3d_roadmap.md`
- `knowledge/notes/ai_panel_rewrite.md`
- `knowledge/notes/circuit_datasets.md`
- `knowledge/notes/eda_toolbar_settings.md`

### 2026-06-20 - Django dev-loop acceleration

- Project URLConfs moved heavy view modules to lazy URL callbacks, so URL checks no longer import simulation, ML/admin, org, SSO, 2FA, chat, shop, accounts, orders, knowledge and moderation views during ordinary Django startup.
- The multi-line Django-template comment check is now opt-in through `DOLG_CHECK_DJANGO_COMMENTS=1` or active in CI, instead of scanning all HTML files on every local `manage.py check`.
- CLI-only checks can set `DOLG_SKIP_SOCIALACCOUNT_PROVIDERS=1` to avoid importing heavy OAuth provider stacks; normal site startup keeps Google/Microsoft/GitHub providers enabled.
- VS Code Python/Django tasks now pass fast local env flags for checks, migrations, focused pytest, engine worker and SQL inspect.
- Verification: `.venv\Scripts\python.exe -m ruff check Dolg_APP\urls.py Dolg_APP\checks.py`, `manage.py check`, URL reverse/resolve smoke, `/simulation/` and `/cad/` smoke, Stripe webhook CSRF smoke.
- Current light profile with ASGI, optional app probes and social providers skipped: `django.setup` ~8s, Django checks ~3-4s. Remaining startup weight is mostly Django core/admin/forms/model loading, so further cuts should be feature-specific rather than global.

### 2026-06-20 - Simulation/CAD asset smoke

- Added `Dolg_APP/tests_tool_asset_smoke.py` for fast `/simulation/` and `/cad/` smoke coverage without Playwright-heavy browser runs.
- The smoke renders both workspaces, checks rendered `/static/...` references through Django staticfiles, verifies critical simulation worker/wasm/lib/AI assets, and confirms the server-engine catalog/recommend APIs.
- During verification, stale ML training and VS Code `pytest --collect-only Dolg_APP` processes were stopped; VS Code Test Explorer now points at focused smoke/core test files instead of collecting the whole app by default.
- Verification: `ruff check Dolg_APP\tests_tool_asset_smoke.py`, `pytest Dolg_APP\tests_tool_asset_smoke.py -q`, `.vscode/settings.json` JSON parse.
- Next active item in `WORK_FRONT_20260619.md`: Session 2, first small extraction from `simulation.html` into `shop/static/simulation`.

### 2026-06-20 - Simulation server-engine UI extraction

- Extracted pure server-engine render helpers from `simulation.html` into `shop/static/simulation/server-engine-ui.js`.
- Kept the old global function names and inline handler contract in `simulation.html`; they now delegate to `window.DolgServerEngineUI`, so the current UI keeps working while the template gets smaller.
- Extended `Dolg_APP/tests_tool_asset_smoke.py` to verify the new static asset and run a Node VM contract smoke for result rendering, escaping, job counts and engine cards.
- Verification: `ruff check Dolg_APP\tests_tool_asset_smoke.py`, `pytest Dolg_APP\tests_tool_asset_smoke.py -q`, Node syntax check for `server-engine-ui.js`, and `git diff --check` for touched files.
- Next active item in `WORK_FRONT_20260619.md`: Session 3, EngineJob MVP-2.

### 2026-06-21 - EngineJob MVP-2 and first server engine

- Added `dolg-engine-router` to the server-engine catalog as the first real server-side engine entrypoint. Its worker adapter currently delegates to `dolg-numpy-mna`, records the route in result metrics/artifacts, and gives us a stable place to attach Xyce/PySpice/GnuCap/GNN workers later.
- Extended `EngineJob` with `reason`, `retry_count`, `max_retries`, `result_contract_version` and `audit_log`; added migration `0021_enginejob_mvp2`.
- Added lifecycle helpers for retry, stale heartbeat detection and audit events. `run_engine_worker --mark-stale --stale-after N` can now clean orphaned running jobs before processing the queue.
- Added API retry endpoint `/api/sim/jobs/<id>/retry/`, richer job serialization, terminal result status handling, and admin visibility for retry/reason/audit fields.
- Result payloads now normalize to `dolg.engine.result` contract v1, so future external workers can return the same shape.
- Verification: focused ruff, `manage.py check`, `makemigrations --check --dry-run`, and `pytest Dolg_APP/tests_server_engines.py Dolg_APP/tests_tool_asset_smoke.py -q` (`23 passed`).
- Next active item in `WORK_FRONT_20260619.md`: Session 4, security/data-protection report for targeted attacks.

### 2026-06-21 - Targeted attack data-protection report

- Added a full targeted-attack data-protection report to `docs/SECURITY_BACKLOG.md` instead of creating another standalone document.
- Mapped DOLG's real assets and trust boundaries against OWASP ASVS 5.0, OWASP Cheat Sheets/Top 10 themes, and NIST CSF 2.0.
- Documented current controls in code: production settings guardrails, CSRF/security headers, Stripe webhook signatures, SSRF guard, hashed organization API tokens, audit logs, project event logs and `EngineJob` audit/result boundaries.
- Prioritized the remaining gaps: strict CSP migration, hardened upload pipeline, admin/Data Console hardening, Stripe demo fail-closed behavior, proxy trust checks, future Docker/K8s worker sandboxing and incident monitoring.
- Corrected the security backlog status for CSP: it is still partial because `settings.py` keeps `'unsafe-inline'` until the heavy simulation UI is decomposed.
- Verification: documentation diff review and `git diff --check` for the touched markdown files.
- Next active item in `WORK_FRONT_20260619.md`: Session 5, Admin/Data Console v2.

### 2026-06-21 - Admin/Data Console v2

- Extended the staff Data Console with read-only filters for Django models, SQL tables, FileField entries and JSONField entries.
- Added JSONField inventory and compact sample previews with safe admin change links, so staff can inspect project/engine/audit payloads without writing custom SQL.
- Replaced hard-coded admin paths with reverse-resolved changelist/change URLs where the model is registered in Django admin.
- Kept media browsing read-only and bounded the recursive media scan to avoid freezing the console on large artifact directories.
- Added focused coverage for Data Console loading, filters and JSON preview.
- Verification: `ruff check Dolg_APP\ml_admin_views.py Dolg_APP\tests_ml_admin.py`, `py_compile Dolg_APP\ml_admin_views.py`, `manage.py check`, `pytest Dolg_APP\tests_ml_admin.py -q` (`11 passed`), and `git diff --check`.
- Next active item in `WORK_FRONT_20260619.md`: Session 6, CAD/simulation UX pass.

### 2026-06-21 - CAD/simulation workspace preference baseline

- Added shared `shop/static/shop/workspace-preferences.css` and `workspace-preferences.js`.
- CAD and simulation now receive profile density/layout/render/motion settings as stable body classes and datasets instead of leaving them as passive `data-*` attributes.
- Added `window.DolgWorkspaceInstrumentContract` as the baseline contract for future oscilloscope, generator, multimeter and probe animations with reduced-motion support.
- Simulation now respects an explicit profile render preference (`canvas2d` or `webgl`) while keeping the existing auto mode free to choose Pixi only when the current schematic needs it.
- Extended `Dolg_APP/tests_tool_asset_smoke.py` with static-asset checks and a Node VM contract smoke for the workspace preference module.
- Verification: `node -c shop\static\shop\workspace-preferences.js`, `.venv\Scripts\python.exe -m ruff check Dolg_APP\tests_tool_asset_smoke.py`, `.venv\Scripts\python.exe manage.py check`, `.venv\Scripts\python.exe -m pytest Dolg_APP\tests_tool_asset_smoke.py -q --no-header --no-migrations --reuse-db` (`5 passed`), and `git diff --check`.
- Next active item in `WORK_FRONT_20260619.md`: Session 7, security/token limits and password/brute-force hardening.

### 2026-06-21 - Password and organization token hardening

- Confirmed the password path uses Django hashers and `AUTH_PASSWORD_VALIDATORS`; new registrations go through `validate_password(...)` and `User.objects.create_user(...)`.
- Added cache-backed login lockout keyed by hashed username+IP, so brute-force attempts cannot bypass the old session counter by starting a fresh browser session.
- Hardened organization API token creation with a server-side active-token cap and a scope allowlist; raw tokens are still shown once and stored only as hashes.
- Added focused tests for cross-session login lockout, invalid API-token scopes and active-token limit enforcement.
- Verification: `.venv\Scripts\python.exe -m ruff check accounts\views.py Dolg_APP\org_views.py Dolg_APP\tests_registered.py Dolg_APP\tests_enterprise.py`, `.venv\Scripts\python.exe -m pytest Dolg_APP\tests_registered.py::LoginRateLimitTests Dolg_APP\tests_enterprise.py::ApiTokenTests -q --no-header --no-migrations --reuse-db` (`4 passed`), `.venv\Scripts\python.exe manage.py check`, and `git diff --check`.
- Next security item: body-size guard and throttles for heavy JSON/API endpoints.

## Шаблон новой записи

```markdown
### YYYY-MM-DD - название этапа

- Что изменилось.
- Почему принято такое решение.
- Какие проверки прошли.
- Что стало следующим активным пунктом в `WORK_FRONT_20260619.md`.
```

---

## DIPLOMA AI DECLARATION DRAFT

Источник: `DIPLOMA_AI_DECLARATION_DRAFT.md`

# Черновик: Декларация об использовании технологий генеративного ИИ (Приложение 1 к Положению)

> ⚠️ Это **черновик-шаблон**. Заполни честно под свой факт: ФИО, группа, направление, тема, и —
> главное — какие именно модели ты использовал и для чего. Курсивные примеры в Положении —
> ориентир, не копируй дословно. Декларацию визирует руководитель ВКР (его согласие легитимизирует
> использование ИИ по п. 4.10.1).

---

## ДЕКЛАРАЦИЯ об использовании технологий генеративного ИИ при подготовке ВКР

- **ФИО обучающегося:** Буряко Дмитрий Сергеевич
- **Группа:** Пи-141
- **Направление подготовки:** 09.03.03 Прикладная информатика
- **Направленность (профиль):** Прикладная информатика
- **Тема ВКР:** Разработка веб-приложения для продажи радио- и электронных компонентов со встроенными
  инструментами проектирования и симуляции схем

В ходе выполнения ВКР использовались перечисленные ниже технологии генеративного ИИ **в качестве
вспомогательного инструмента**. Итоговые решения, текст и код проверены, доработаны и осмыслены
автором.

**Использованные модели (название, URL):**

- Claude / Claude Code (Anthropic) — <https://claude.ai>, <https://claude.com/claude-code>
- ChatGPT (OpenAI) — <https://chatgpt.com>
- DeepSeek — <https://chat.deepseek.com>
- Qwen (Alibaba) — <https://chat.qwen.ai>

| Часть работы | Технология ИИ | Цель и способ применения | Степень участия ИИ |
|---|---|---|---|
| Введение (объект, предмет, гипотеза, методология, структура) | ChatGPT, Claude | Черновые формулировки методологических элементов | Частичное: черновик переработан и уточнён автором |
| Глава 2 (поясняющий текст к таблицам и решениям) | Claude / Claude Code | Черновое изложение и редактура описаний реализованных модулей по фактам проекта | Частичное: тексты выверены и переписаны автором своими словами |
| Исходный код приложения DOLG | Claude Code, ChatGPT, DeepSeek, Qwen | Помощь в написании и отладке кода под архитектуру и задачи, поставленные автором | Частичное: концепция, архитектура, состав модулей и проектные решения — авторские; код проверен, доработан и сопровождается автором |
| Перевод иноязычных источников | ChatGPT, DeepSeek | Перевод фрагментов документации и статей | Полное по переводу; проверено автором |
| Поиск и пост-обработка источников | ChatGPT, DeepSeek, Qwen | Помощь в поиске и кратком изложении источников для обзора | Частичное: отбор, проверка достоверности и выводы — авторские |
| Оформление (нормализация тире, нумерация рисунков, структура глав по ЛНА) | Claude Code | Технические правки оформления по требованиям ЛНА | Полное по форматированию; содержание авторское |

> *(сверь, какие модели для какой части ты реально использовал, и поправь графу «Технология ИИ».)*

Все применённые технологии согласованы с руководителем ВКР.

Система Retrieval-Augmented Generation (RAG) **для подготовки текста ВКР не применялась**. (RAG-механизм
присутствует в самом приложении DOLG как функция продукта и к написанию текста работы отношения не имеет.)

**Гарантия автора:** концепция, архитектура, проектные решения, состав и интеграция модулей и выводы
работы являются моим собственным интеллектуальным продуктом. Генеративный ИИ применялся как
вспомогательный инструмент (черновики и редактура текста, помощь с кодом, перевод и поиск источников);
итоговые текст и код проверены, доработаны и осмыслены мной — я понимаю результат и способен его
сопровождать и развивать.

Обучающийся ___________________ / _______________________ (подпись, Фамилия И.О.)
«____» ___________ 20___ г.

---

## Как сделать декларацию правдивой и безопасной
1. **Согласуй с руководителем ДО сдачи** — особенно строку про код. Использование ИИ при написании
   кода для IT-ВКР — чувствительный момент; руководитель подскажет, как это корректно оформить по
   «Политике использования ИИ» вуза, и его виза закрывает п. 4.10.1 («использование ИИ легитимно»).
2. **Будь готов защитить код вживую (§4.6).** Это главное: по техническому направлению могут попросить
   объяснить архитектуру, разобрать модуль, дописать/починить кусок кода. Пройдись по DOLG и убедись,
   что понимаешь каждый ключевой блок (MNA-солвер, netlist builder, модель данных, симуляцию, AI-слой)
   и можешь его изменить без подсказки. Гарантия автора правдива ровно настолько, насколько ты владеешь работой.
3. **Перепиши ИИ-черновики своими словами** — текст уже причёсан «под живого», но пройдись сам:
   где-то замени формулировку на свою. Тогда и детектор спокойнее, и на вопросах не поплывёшь.
4. **Указывай реальные модели и не занижай.** Честная широкая декларация безопаснее, чем заниженная:
   Положение прямо разрешает задекларированное использование, а скрытое — повод для доработки (п. 4.10.3).
5. **Прочитай «Политику использования генеративного ИИ»** вуза (§4.1) — там допустимые сферы, модели и
   лимиты. Это определяет, что считается «легитимным» в твоём случае.

---

## DIPLOMA CHAPTER2 DRAFT

Источник: `DIPLOMA_CHAPTER2_DRAFT.md`

# Глава 2 — расширенный текст параграфов (черновик для вставки в Word)

Цель — довести каждый параграф 2.1–2.6 до нормы ≥ 4 страниц. Существующие таблицы оставить,
этот текст добавить вокруг них (вступление + пояснение решений прозой). Ссылки [n] — по текущему
списку источников. Цифры — актуальные (364 товара, 22 статьи, 99 материалов).

---

## 2.1. Создание технологического стека и базового каркаса сайта

Перед началом реализации был зафиксирован принцип построения системы: единое монолитное
Django-приложение с разделением ответственности по доменным приложениям. Такой подход выбран
сознательно, поскольку для выпускной квалификационной работы важнее воспроизводимость и
проверяемость результата, чем формальная демонстрация распределённой инфраструктуры. Монолит
позволяет развивать магазин, редактор схем, CAD и симулятор в едином контуре аутентификации,
шаблонов и объектно-реляционного отображения (ORM), не вводя сетевых границ между подсистемами и
не усложняя локальный запуск [10, 18, 23].

Структурно проект разделён на шесть доменных приложений (таблица 2.1). Приложение `Dolg_PR`
содержит настройки, маршрутизацию, конфигурацию статики и медиа, а также тестовый и
производственный профили окружения. Коммерческий контур реализован приложениями `shop` (каталог из
364 товаров в 23 категориях, фильтры, карточки, спецификации BOM, экспорт CSV/XLSX), `accounts`
(регистрация, профиль, адреса, связь с заказами и проектами) и `orders` (корзина, оформление,
позиции заказа, статусы и сценарии email-уведомлений). Справочный контур образует приложение
`knowledge` (22 статьи по шести категориям, 99 дополнительных материалов, внутренние перекрёстные
ссылки, изображения, видео и инженерная лаборатория). Инженерный контур сосредоточен в приложении
`Dolg_APP` — здесь находятся модели схем, версии проектов, история симуляций, экспертная проверка
и сервис локального ассистента.

Выбор единой кодовой базы упрощает совместное использование моделей: компонент каталога и его
электрические параметры доступны как магазину, так и редактору схем без промежуточных API. Это
прямо отвечает ключевой идее работы — связать подбор компонента, его покупку и применение в схеме
в одном инструменте. Django-ORM при этом сохраняет возможность последующей замены СУБД: на этапе
разработки используется SQLite, обеспечивающая мгновенный локальный запуск и простоту тестирования,
а для промышленного развёртывания предусмотрен переход на PostgreSQL без переписывания
бизнес-логики, поскольку доменный слой остаётся неизменным [10, 14, 19].

Внешние технологии — Django REST Framework, JWT, Celery и Redis — в текущей редакции не вводятся
как обязательные компоненты. Они рассматриваются как перспективы развития: актуальная версия
закрывает пользовательские сценарии средствами Django views, сессионной аутентификации,
JSON-эндпоинтов и кратковременного локального кеша каталога для ассистента. Такое решение снижает
число внешних зависимостей и делает систему воспроизводимой в учебном окружении, что соответствует
заявленному статусу демонстрационного, но работоспособного прототипа [10, 11].

> *(после абзацев — таблица 2.1 «Фактические модули проекта DOLG», как в текущей версии)*

## 2.2. Проектирование базы данных

Проектирование данных выполнено на основе моделей Django ORM. Ведущий принцип — разделение трёх
групп сущностей: коммерческих (каталог, заказы), пользовательских (профили) и инженерных (проекты
схем, версии, результаты расчётов). Такое разделение отражает доменную структуру приложения и
позволяет развивать каждую группу независимо. Для технических параметров компонентов и схем
применяется поле типа JSONField: оно хранит параметры SPICE-моделей, координаты элементов,
описания соединений и runtime-настройки без постоянного изменения структуры таблиц, что особенно
важно при эволюции форматов схем [10, 19, 40].

Центральная инженерная сущность — проект схемы (`SchematicProject`). Схема сохраняется в
JSON-формате, совместимом с клиентским редактором: это массив компонентов, массив соединений,
координаты, порты, номиналы и метаданные. При загрузке и сохранении выполняется нормализация
структуры, что снижает риск несовместимости ранее созданных проектов с обновлённым построителем
списка соединений (netlist builder). История изменений ведётся через сущность `ProjectVersion`
(снимки схемы по версиям), а результаты расчётов — через `SimulationRun` (тип анализа, движок,
краткое резюме и полные данные результата). Демонстрационные схемы (12 проектов) помечены флагом
`is_demo` и доступны в режиме просмотра без авторизации.

Коммерческие сущности построены вокруг товара (`Product`) и категории (`Category`): хранятся
артикул, производитель, цена, остаток, статус жизненного цикла и набор технических параметров в
JSON. На момент актуализации каталог содержит 364 товара в 23 категориях. Профиль пользователя
(`UserProfile`) хранит контактные и адресные данные; заказ (`Order` / `OrderItem`) — статус, сумму,
количество и зафиксированную цену позиции на момент покупки. Связи между сущностями (таблица 2.2)
обеспечивают целостность данных средствами ORM.

Вопросы резервного копирования и перехода на PostgreSQL отнесены к плану промышленного
развёртывания. Такое разделение отражает фактический этап работы: ВКР проверяет работоспособность
архитектуры и пользовательских сценариев, а не имитирует незавершённый промышленный кластер. При
этом выбор JSONField и Django-ORM гарантирует, что переход на PostgreSQL с расширениями (например,
полнотекстовым поиском) не потребует пересмотра модели данных [8, 14].

> *(таблица 2.2 «Основные сущности данных» — как в текущей версии)*

## 2.3. Проектирование серверной части (backend)

Серверная часть построена по шаблону Django MVT (Model–View–Template): HTML-страницы формируются
шаблонами, а интерактивные операции редактора и симулятора используют JSON-эндпоинты. Это решение
снижает число внешних зависимостей и делает систему воспроизводимой в локальном учебном окружении,
не привязывая проект к отдельному SPA-фреймворку [10, 18]. Серверные сценарии (таблица 2.3)
включают управление проектами схем (создание, обновление, версии, загрузка в редактор),
публикацию схемы по ссылке (share-token и режим просмотра), сохранение результатов симуляции и
формирование PDF-представления.

Безопасность реализуется штатными средствами Django: сессионная аутентификация, защита от CSRF,
проверка принадлежности объектов пользователю и строгая валидация входных данных. Закрытые операции
требуют авторизации и проверки прав доступа, тогда как публичные сценарии (просмотр каталога,
демо-схемы, доступ по share-ссылке) ограничены режимом просмотра без изменения данных. Ролевая
модель включает гостя, зарегистрированного пользователя, менеджера и администратора. Режим
публичного просмотра специально ограничен по поведению, что позволяет демонстрировать проект по
QR-ссылке без выдачи прав на изменение данных [10, 39].

Модуль локального ассистента выделен в отдельный серверный файл (`rule_ai`), чтобы не смешивать
формирование ответа, обработку ошибок и view-логику. Ассистент построен на принципе
«вычислять, а не угадывать»: ответ собирается из фактов схемы, спецификации BOM, результатов
экспертной проверки и статей справочника, а число берётся из реального инженерного движка (узловой
анализ, Monte-Carlo, расчёт мощности), а не из языковой модели. Каталог для ассистента собирается
как ограниченный снимок и кратковременно кешируется, поэтому многошаговый диалог не выполняет
тяжёлый запрос к каталогу на каждом сообщении. Внешняя языковая модель не является обязательной —
в demo-режиме система отвечает полностью локально.

Такое разделение ответственности (представления, сервис-слой расчётов, отдельный AI-модуль)
соответствует принципам чистой архитектуры: бизнес-логика расчётов и проверок не зависит от
деталей доставки HTTP-ответа и может переиспользоваться как в синхронных view, так и в фоновых
сценариях при дальнейшем развитии (Celery) [10, 11].

> *(таблица 2.3 «Серверные сценарии и API» — как в текущей версии)*

## 2.4. Проектирование клиентской части (frontend) и пользовательского интерфейса

Клиентская часть реализована как серверно-рендеринговый интерфейс Django с интенсивным
использованием JavaScript на инженерных экранах. Коммерческие страницы (каталог, карточка товара,
корзина, личный кабинет) формируются серверными шаблонами, что ускоряет разработку и упрощает
сопровождение. Интерактивные области — схематический редактор, панель симуляции, чат ассистента,
3D-просмотр платы, виртуальная лаборатория и 2D-CAD — реализованы средствами Canvas2D, WebGL/Pixi.js
и Three.js, а не виртуального DOM, поскольку для графически насыщенных сцен прямое управление
отрисовкой эффективнее [16, 42]. Подсистемы интерфейса перечислены в таблице 2.4.

Ключевое инженерное решение клиентской части — автоматическое переключение режима отрисовки.
Базовым является Canvas2D, обеспечивающий полный контроль над условными графическими обозначениями
(УГО), проводами, сеткой и overlay-слоями. При росте числа элементов схемы подключается
WebGL-ускоритель Pixi.js, использующий аппаратное ускорение графики и позволяющий обрабатывать
большое число объектов с высокой частотой кадров. Переключение происходит без участия пользователя,
что снижает задержки на тяжёлых схемах и одновременно не усложняет базовый сценарий работы.
Состояние схемы хранится в явных JavaScript-структурах и JSON-представлении, совместимом с серверным
сохранением, поэтому переход между режимами отрисовки не влияет на данные проекта.

Отдельное внимание уделено контролю качества интерфейса. Поскольку ошибки в Canvas- и
overlay-интерфейсах плохо выявляются обычными модульными тестами Django, верстка проверяется
браузерными smoke-тестами: контролируются размеры ключевых панелей, отсутствие горизонтального
переполнения, корректное отображение модальных окон и наличие реальной отрисовки на canvas [42].
Это позволяет фиксировать визуальные регрессии инженерных экранов автоматически.

Интерфейс спроектирован с учётом ограничений целевых устройств: полноценное редактирование схем
доступно на десктопе и планшетах, тогда как на мобильных устройствах сохраняется просмотр каталога
и справочника. Применяется единый стиль оформления, поддержка горячих клавиш для основных операций
редактора (копирование, вставка, удаление, отмена/повтор) и локализованные сообщения об ошибках на
русском языке, что отвечает требованиям к юзабилити, сформулированным в первой главе.

> *(таблица 2.4 «Клиентские подсистемы» — как в текущей версии)*

## 2.5. Создание модуля проектирования для принципиальных схем

Модуль проектирования принципиальных схем приведён к единому практичному УГО-режиму, близкому к
принятому представлению электрических схем по ЕСКД. Ранее существовавший «modern»-стиль удалён, так
как ухудшал читаемость инженерных схем и не соответствовал отраслевым обозначениям [2, 3, 4]. В
УГО-режиме добавлены интеллектуальная маршрутизация проводов (smart wiring), магнитные выводы,
метки цепей (GND, +5V, OUT) и настраиваемый шаг перемещения элементов, отделённый от шага визуальной
сетки. Проектные решения редактора сведены в таблице 2.5.

Принципиально важна связь редактора с каталогом. При перетаскивании компонента из палитры на схему
создаётся его графическое представление с привязкой к реальному товару: электрические параметры
(сопротивление, ёмкость, индуктивность и т.д.) берутся из базы данных. Это позволяет формировать
спецификацию материалов (BOM) непосредственно из схемы: компоненты группируются, экспортируются в
CSV/XLSX и могут быть добавлены в корзину одним действием. Тем самым проектирование напрямую
смыкается с покупкой — устраняется типичная для существующих решений необходимость переключаться
между САПР и магазином и вручную переносить данные.

Сохранение проектов реализовано в устойчивом JSON-формате с нормализацией при загрузке, что
обеспечивает совместимость ранее созданных схем с обновлённым построителем netlist. Библиотека
компонентов расширяется без правки JavaScript: операционные усилители, резисторы и диоды
подключаются внешними JSON-шаблонами, что упрощает сопровождение и масштабирование. Предусмотрен
режим публичного просмотра схемы по URL и QR-коду без выдачи прав на редактирование — для быстрой
демонстрации проекта с другого устройства.

Параллельно развивается отдельный инструмент 2D-CAD: добавлены ГОСТ-шаблоны, слои, размеры в
миллиметрах, выноски, привязки к объектам, полярный режим, импорт форматов DOLG JSON/SVG/DXF/DWG/
SPICE и экспорт PNG/SVG/PDF формата A3. Вкладка энциклопедии убрана из CAD-панели, чтобы редактор
не дублировал справочник и оставался сосредоточенным на чертеже, проверке и спецификации [1, 2, 6].

> *(таблица 2.5 «Проектные решения редактора схем» — как в текущей версии)*

## 2.6. Проектирование модуля симуляции и интеграция с ngspice.js

Модуль симуляции выполняет анализы по постоянному току (DC), частотный (AC) и анализ переходных
процессов (TRAN) в браузере через WebAssembly-порт ngspice (`ngspice.wasm`), а при отказе основного
движка использует резервный режим узлового анализа на JavaScript для базового DC-сценария.
Вычислительное ядро запускается в браузерной среде, что снижает нагрузку на сервер и сохраняет
интерактивность интерфейса, хотя и накладывает ограничение на размер симулируемых схем [13, 16, 36, 38].

В основе расчёта лежит модифицированный узловой анализ. Система уравнений формируется из законов
Кирхгофа и в матричной форме записывается как

    G · V = I,                                                         (2.1)

где G — матрица проводимостей узлов; V — искомый вектор узловых потенциалов; I — вектор втекающих
токов источников. Для простейших цепей результат проверяется аналитически. Так, для делителя
напряжения

    Vout = Vin · R2 / (R1 + R2),                                       (2.2)

где Vin — входное напряжение; R1, R2 — сопротивления плеч; Vout — напряжение на R2. По результатам
DC-решения вычисляется рассеиваемая на резисторах мощность для оценки тепловой нагрузки и derating:

    P = ΔU² / R = I² · R,                                              (2.3)

где ΔU — падение напряжения; R — сопротивление; I — ток. Частотный анализ опирается на расчёт
частоты среза RC-цепи по уровню −3 дБ:

    fc = 1 / (2π · R · C),                                             (2.4)

где R и C — сопротивление и ёмкость; fc — частота среза. Ток ограничительного резистора светодиода
определяется по закону Ома:

    I_LED = (Vin − Vf) / R,                                           (2.5)

где Vf — прямое падение на светодиоде. Для анализа влияния разброса номиналов применяется метод
Monte-Carlo: по выборке симуляций оценивается среднеквадратичное отклонение σ результата и строится
доверительный интервал

    Δ = ±1,96 · σ,                                                     (2.6)

позволяющий оценить худший случай при заданном разбросе (например, ±5 %).

Поверх базового расчёта реализованы инженерные расширения (таблица 2.6): экспертная проверка
(Design Health Score, DRC/ERC, риск BOM, derating), модуль измерений (сравнение ожидаемого с
измеренным), импорт подмножества форматов LTspice/SPICE/KiCad, ассистент-объяснение ошибок,
разделяемая демонстрация по QR-коду. Генератор сигналов виртуальной лаборатории связан с
построителем netlist: синусоидальный источник преобразуется в SPICE-конструкцию SIN, меандр — в
PULSE, треугольная форма — в PWL-последовательность, поэтому интерфейс лаборатории влияет на
расчётный TRAN-анализ, а не только на визуальное представление источника [13].

Контроль качества реализации (таблица 2.7) подтверждает работоспособность: системная проверка
Django проходит без замечаний, стандартный тестовый прогон охватывает модели, представления, заказы
и инженерный контур, браузерные e2e-сценарии проверяют canvas, модальные окна, CAD и экспорт, а
набор проверок ассистента и публикации выполняется в ускоренном режиме. Таким образом, результаты
реализации и проверки интегрированы в проектную главу, а подробные доказательные материалы вынесены
в приложения, чтобы не перегружать основной текст.

> *(таблицы 2.6 «Реализованные расширения симуляции» и 2.7 «Контроль качества» — как в текущей версии)*

---

**Примечание по объёму.** Этот текст + существующие таблицы дают по каждому параграфу 2.1–2.6
порядка 4 страниц при шрифте TNR 14 / интервал 1.5. Формулы (2.1)–(2.6) обязательно набрать в
редакторе формул Word (Вставка → Уравнение), а не текстом, и снабдить ссылками в тексте
(«по формуле (2.1)…»).

---

## DIPLOMA CHECKLIST

Источник: `DIPLOMA_CHECKLIST.md`

# Чек-лист оформления и доработки ВКР (по Распоряжению №08 от 19.02.2024)

Сверка диплома «домашняя версия 6» с официальными правилами. Фокус — **Глава 2** и **Приложения**
(по запросу). Отметки: 🔴 обязательно исправить · 🟡 желательно · 🟢 уже ОК.

## Вердикт (кратко)

Работа содержательно сильная и в основном соответствует правилам, но есть **формальные нарушения,
сконцентрированные именно в Главе 2 и Приложениях** — без их устранения работу могут вернуть на
доработку. Главные три проблемы: (1) короткие параграфы Главы 2 (< 4 страниц — нарушение нормы),
(2) хаотичная нумерация приложений и рисунков/таблиц в них, (3) устаревшие/несходящиеся цифры
по каталогу. Всё это чинится; ниже точный список.

---

## A. Обязательная структура и титульные элементы

- 🔴 **Титульный лист** по образцу (Распоряжение, Приложение Д, Пример 2 для ВКР): шапка
  «МИНОБРНАУКИ… РГЭУ (РИНХ)… Таганрогский институт… Факультет… Кафедра…», блок «ДОПУСТИТЬ К ЗАЩИТЕ»,
  «ВЫПУСКНАЯ КВАЛИФИКАЦИОННАЯ РАБОТА на тему…», автор/группа/направление, руководитель, «Таганрог, 2026».
  В присланном PDF титульного нет — убедиться, что он есть и по форме.
- 🔴 **Задание на ВКР** (Приложение Б правил) — отдельный лист, подписи зав. кафедрой/руководителя/студента.
- 🔴 **Последний лист** с фразой «Выпускная квалификационная работа выполнена мною самостоятельно…» + дата,
  на обороте «В ВКР пронумеровано ___ страниц» (от руки, подпись).
- 🟡 Отдельно для подачи (не в тело работы): заявление на тему (Прил. А), отзыв руководителя (Прил. В).
  Рецензия (Прил. Г) — **только для магистратуры**; для бакалавра не нужна.
- 🟢 Оглавление — есть, собрано, с номерами страниц.

## B. Введение — добавить недостающие обязательные элементы

Правила требуют чёткую структуру введения. Сейчас есть: актуальность 🟢, цель 🟢, задачи 🟢,
практическая значимость 🟢, постановка задачи 🟢. **Отсутствуют и нужны:**

- 🔴 **Объект исследования** (напр.: процессы веб-ориентированного проектирования и закупки
  электронных компонентов).
- 🔴 **Предмет исследования** (напр.: архитектура и программная реализация веб-платформы, объединяющей
  каталог, редактор схем и симуляцию).
- 🔴 **Гипотеза** (напр.: объединение магазина, САПР и SPICE-симуляции в одном веб-контуре повышает
  эффективность подбора и проверки компонентов).
- 🔴 **Методология/методы исследования** (анализ предметной области, сравнительный анализ аналогов,
  проектирование БД/архитектуры, прототипирование, тестирование).
- 🔴 **Структура работы** (1–2 предложения: «работа состоит из введения, двух глав, заключения,
  списка из 42 источников и приложений»).
- 🟡 Апробация — для бакалавра необязательна (для магистра обязательна).
- 🟡 Объём введения по норме 3–5 страниц — проверить, что попадает.

## C. ГЛАВА 2 — главное (объём + актуализация)

- 🔴 **Объём параграфов.** Норма: каждый параграф ≥ **4 страниц** печатного текста. Сейчас 2.1–2.6
  по ~1–2 страницы (много таблиц, мало связного текста). Это **прямое нарушение**. Нужно нарастить
  текст в каждом параграфе 2.1–2.6 — описывать решения прозой, а не только таблицей:
  - 2.1 — детальнее про монолит Django, разнесение по доменным приложениям, почему так.
  - 2.2 — модель данных: связи сущностей, роль JSONField, нормализация scheme_data, миграции.
  - 2.3 — backend: MVT, JSON-эндпоинты, контроль доступа, сервис-слой, AI-модуль (rule_ai).
  - 2.4 — frontend: Canvas2D↔Pixi auto-switch, подсистемы, browser-smoke тесты.
  - 2.5 — редактор схем: УГО-режим, smart wiring, BOM-связь с каталогом, JSON-шаблоны.
  - 2.6 — симуляция: ngspice.wasm + JS-MNA fallback, Expert Review, Measurement, CAD import.
- 🔴 **Общий объём работы** ≥ **40 страниц без приложений** (Введение→Заключение). Сейчас основной текст
  ~36 стр. → **не хватает ~4–6 страниц**. Закрывается расширением Главы 2 (см. выше) + введения (B).
- 🟡 **Третья глава.** Норма допускает 2–3 главы; у вас 2 (теория + проектирование). Для ВКР рекомендуется
  3-я практическая глава (результаты/тестирование/анализ). Сейчас это свёрнуто в 2.6 и приложения —
  допустимо, но 3-я глава усилила бы работу. Решить с руководителем. Рекомендация пользователя: не делать, в этом нет надобности.
- 🔴 **Актуализация цифр (расхождение с реальной БД на 2026-06-08):**

  | В дипломе | Реальная БД сейчас | Действие |
  |---|---|---|
  | 89 товаров + 43 РЭБ (= 132) | **364 товара**, 23 категории | ✅ Проверено: это НЕ дубли (имена уникальны, дублей part_number = 3). Каталог реально вырос. **Обновить число везде** (Заключение, 2.1, Прил.). Скриншоты переснять. |
  | 21 статья | **22** статьи | обновить → 22 |
  | 50 доп. материалов | **99** (ArticleMaterial) | обновить → 99 |
  | 12 демо-схем | **12** (is_demo) | ✅ совпадает |
  | 4 маршрута, 13 уроков, 29 заданий | не проверено (модели под др. именами) | пере-верифицировать перед печатью |

  Эти числа фигурируют в Заключении, Главе 2.1 и Приложении 1 — **синхронизировать везде**.

## D. ПРИЛОЖЕНИЯ — главное (перенумерация)

- 🟢 **Обозначение приложений — цифрами 1–6** (требование научрука: везде цифрами, без букв).
  В версии 6 .docx уже исправлено: Приложение 1…6 подряд. (В старом PDF была смесь «1,2,3,4,Д,Е» — устранено.)
- 🔴 **Единая нумерация рисунков/таблиц/листингов — ВЕЗДЕ ЦИФРАМИ, без букв.** Сейчас в приложениях остались
  буквенные (Рис. В.4, В.5; листинги). Привести к:
  - **Рисунки** — сквозная нумерация по всей работе **Рисунок 1 … N** (без букв, без «глава.номер»).
    Карта переименования — см. [DIPLOMA_UPDATES.md](DIPLOMA_UPDATES.md) §4.
  - Таблицы приложений — цифрами (Таблица 1.3 и т.п. — уже так).
  - Листинги — цифрами (Листинг 4.1…).
- 🔴 **Ссылка в тексте на каждый рисунок/таблицу приложения** («…показано на рисунке 9», «см. таблицу 1.3»).
  Сейчас часть иллюстраций приложений в тексте не упомянута — норма требует ссылку на каждую.
- 🟡 **Скриншоты UI** (Прил. 2): скриншоты допустимы (это не скан), но должны быть чёткими, с подписью
  «Рисунок N – …» снизу по центру и ссылкой в тексте. Каталог переснять (вырос до 364 товаров).
- 🟡 Каждое приложение — **с новой страницы**, слово «ПРИЛОЖЕНИЕ А» по центру вверху, ниже заголовок
  (прописная, полужирный, по центру, без точки).

## E. Список использованной литературы и источников

- 🟢 42 источника ≥ 30 (норма ВКР) — ОК по количеству.
- 🟡 **Порядок.** Норма: по алфавиту (иностранные — в конце). У вас группировка по типу (ГОСТы → доки →
  учебники → зарубежные → электронные). Группировка по типу распространена и обычно принимается, но
  **внутри каждой группы — строго по алфавиту**; согласовать формат с руководителем.
- 🔴 **Тире.** Правила: «Длинное тире (—) в тексте не используется» — применять короткое «–». В списке
  литературы у вас местами длинное «—». Заменить «—» → «–» по всему списку (и тексту).
- 🟢 Ссылки в тексте в квадратных скобках [13, 37, 38] — формат верный.
- 🟡 Даты обращения разнобой (2024 и 2026) — допустимо, но лучше единообразно/актуально.

## F. Сквозное оформление (проверить по всей работе)

- 🟢 Шрифт Times New Roman 14, интервал 1.5, поля (лев 3 / прав 1 / верх-низ 2), абзац 1.25,
  выравнивание по ширине — если выставлено, не трогать.
- 🔴 **Подписи рисунков** — снизу по центру, «Рисунок N.N – Название», после подписи **пустая строка**.
  Номер = «глава.номер» в основном тексте; «буква.номер» — в приложениях.
- 🔴 **Подписи таблиц** — слева над таблицей «Таблица N.N – Название», без точки; источник под таблицей
  шрифтом 10; без пустых граф (ставить прочерк).
- 🟡 Заголовки глав «ГЛАВА 1.» (арабская + точка), параграфы «1.1.» — у вас так, ОК. Без переносов в заголовках.
- 🟡 Номера страниц — внизу по центру, TNR 11; на титульном и задании номер не печатается.

## G. Антиплагиат и объём (перед сдачей)

- 🔴 **Оригинальность ВКР бакалавра ≥ 40%** (магистр ≥ 60%), цитирование ≤ 10%. Проверяются Введение +
  основная часть + Заключение. Многие таблицы «фактическая реализация» оригинальны — это плюс.
- 🔴 Готовая работа — на кафедру за **14 дней** до защиты; ознакомление с отзывом — за 5 дней; передача в
  ГЭК — за 2 дня. Заложить время на правки.

---

## Что уже ОК (не трогать)

- Структура глав (анализ → проектирование), 1.1–1.4 и 2.1–2.6 как параграфы.
- Список ≥ 30 источников, ссылки [n] в тексте.
- Нумерация заголовков (ГЛАВА 1., 1.1.).
- 12 демо-схем совпадают с БД.
- Содержательное наполнение (таблицы фактической реализации, диаграммы UML, листинги).

## Чем могу помочь дальше (по твоему запросу «обновление информации»)

1. **Пересчитать и вычистить каталог** (364 → реальное число без дублей) и дать точные цифры для синхронизации.
2. **Дописать текст параграфов Главы 2** до нормы ≥4 стр (черновики прозой по 2.1–2.6) на основе реального кода.
3. **Сгенерировать корректную нумерацию приложений** (А–Е) и список «рисунок→новый номер / таблица→новый номер».
4. Свести **актуальные числа** (статьи 22, материалы 99, схемы 12, маршруты/уроки/задания — доверифицировать).
5. Обновить раздел про AI: за эту сессию реально добавлены L1–L5 toolkit, GNN net-based, Monte Carlo (NumPy),
   RF (scikit-rf) — можно отразить в 2.6 / Приложении «Актуализация».

---

## DIPLOMA DEFENSE PREP

Источник: `DIPLOMA_DEFENSE_PREP.md`

# Конспект для защиты ВКР (DOLG) — расширенный

Читай, отмечай непонятное, спрашивай. Цель: объяснять проект как свой. Формат: **коротко → что
сказать на защите → могут спросить.** Идея проекта — **комбайн**: единая платформа, в которой
магазин компонентов, проектирование схем и симуляция связаны и могут расти до промышленного уровня.

---

## 0. Про ИИ-декларацию (кратко, вопрос решён)
Декларация нужна, антиплагиат будет — целимся на **оригинальность ≥40%**. Декларация-.docx готова,
согласовать с руководителем. «Политику ИИ» вуза в открытом доступе не нашли (нет и на ЭИОС) — она на
твои действия не влияет, требования и так ясны. Дальше — про сам проект.

## 1. Лифт-питч (30 сек)
DOLG объединяет то, что обычно разнесено по разным программам: **магазин** радио- и электронных
компонентов, **редактор принципиальных схем** и **SPICE-симуляцию** — в одном браузерном сервисе.
Ключевое: компонент из каталога попадает в схему **с реальными параметрами**, а из схемы собирается
**спецификация (BOM)**, которую можно сразу купить. Это закрывает «разрозненность инструментов» и
«оторванность САПР от рынка» из введения и задумано как основа для большего — единого инженерного комбайна.

## 2. Архитектура и стек (честно)
- **Монолит на Django** с разделением по доменным приложениям: `shop`, `accounts`, `orders`,
  `knowledge`, `Dolg_APP` (инженерный контур), `Dolg_PR` (настройки).
- **Почему монолит (сильный ответ):** магазин, схема и симуляция работают с **общими моделями данных
  в одном контуре** (аутентификация, ORM, шаблоны). Компонент каталога и его электрические параметры
  доступны и магазину, и редактору схем **без сетевых вызовов между сервисами** — это и есть «связь в
  один контур». При этом монолит **модульный**: каждое доменное приложение изолировано, и при росте
  нагрузки тяжёлые части (симуляция, AI) можно вынести в отдельные сервисы, не переписывая ядро.
  То есть это не «упрощение ради ВКР», а осознанная база под расширяемый продукт.
- **Две БД под разные задачи (так и говорить):**
  - **SQLite** — быстрая, нетребовательная, ноль настройки. Её роль — **простые, небольшие данные и
    локальная разработка/демо**: подняли проект за секунду, без установки сервера.
  - **PostgreSQL** — для **большого массива данных и надёжного хранилища** (боевой профиль:
    `settings_prod.py` / `DATABASE_URL` → `django.db.backends.postgresql`). Её роль — **продакшен**:
    параллельная нагрузка, резервное копирование, и тип **JSONB** для схем — он индексирует и
    позволяет запрашивать содержимое JSON по ключам/значениям (SQLite так не умеет), плюс задел под
    `pgvector` (семантический поиск).
  - Код один (Django ORM), переключение — переменной окружения, без правки логики.

**Могут спросить:** «Почему две БД?» → *Это один и тот же код на Django ORM: в разработке — SQLite для
скорости запуска, в продакшене — PostgreSQL (JSONB для схем, нагрузка, бэкапы). Переключение — через
переменную окружения, без правки логики.* «Зачем JSONB?» → *Схема (`scheme_data`) — это граф из
компонентов и соединений; JSONB хранит его целиком и при этом позволяет искать/индексировать по полям.*

## 3. Симуляция — ядро инженерной части
### 3.1. Где и чем считаем
- **В браузере — ngspice, скомпилированный в WebAssembly (`ngspice.wasm`).** ngspice — это
  открытый, де-факто стандартный SPICE-симулятор (наследник Berkeley SPICE). Анализы: **DC, AC, TRAN.**
- **Резерв:** если ngspice не загрузился, для базового DC работает **свой решатель узловых уравнений
  на JavaScript (JS-MNA)**.
- **Netlist builder:** переводит нарисованную схему в текстовый SPICE-нетлист (узлы по портам,
  номиналы и источники → директивы), плюс проверка перед запуском (нет земли, висящие выводы).

### 3.2. Почему именно ngspice (альтернативы — частый вопрос)
- **LTspice** — бесплатный, но **закрытый** (Analog Devices), Windows-only, нельзя встроить в веб и нет исходников.
- **PySpice** — это Python-обёртка над ngspice/Xyce; требует **сервера** с Python, в браузере не идёт.
- **Xyce** (Sandia) — мощный параллельный SPICE, но тяжёлый, только серверный, избыточен для веб-демо.
- **Qucs / Falstad CircuitJS** — либо свой нестандартный движок, либо упрощённая модель (Falstad —
  учебная, без настоящих SPICE-моделей).
- **Вывод (что сказать):** ngspice — единственный, кто даёт **настоящую SPICE-точность + открытый код
  (можно встраивать) + поддерживаемый порт в WebAssembly**, то есть работает **полностью в браузере без
  сервера**. Поэтому он и выбран.

### 3.3. Метод и формулы
Модифицированный узловой анализ (MNA): систему по законам Кирхгофа пишем как **G·V = I** и решаем численно.
- (2.1) `G·V = I` — узловой анализ. (2.2) делитель `Vout=Vin·R2/(R1+R2)`. (2.3) мощность/нагрев `P=ΔU²/R=I²R`.
- (2.4) частота среза RC `fc=1/(2πRC)`. (2.5) ток светодиода `I=(Vin−Vf)/R`. (2.6) интервал Монте-Карло `Δ=±1,96·σ`.
- **Monte-Carlo (NumPy):** прогон множества испытаний с допуском номиналов (±5%), оценка разброса, σ и худшего случая.

### 3.4. Серверная симуляция — почему отложена и перспективы (важно для «комбайна»)
- **Сейчас расчёт в браузере** — это снимает нагрузку с сервера и даёт мгновенную интерактивность,
  но **ограничивает размер схемы** (WASM-память браузера) и не годится для долгих/массовых расчётов.
- **Почему серверная часть отложена:** это отдельный крупный блок — нужна очередь задач,
  изоляция процессов, управление ресурсами и заметно больше человеко-времени; для ВКР важнее было
  довести рабочий браузерный контур.
- **Какой движок ставить на сервер (важная оговорка):** ngspice хорош для браузера и интерактива, но
  как **серьёзный серверный движок для огромных схем он не лучший выбор** — он однопоточный и на
  больших задачах проседает. Для серверной части логичнее **Xyce** (Sandia National Labs):
  открытый, SPICE-совместимый, но **параллельный (MPI), рассчитан на очень большие схемы и HPC** —
  это и есть «полноценное серверное оборудование». То есть в комбайне роли делятся: **ngspice.wasm —
  в браузере (интерактив), Xyce — на сервере (масштаб)**. PySpice можно использовать как Python-обёртку
  для управления серверным движком.
- **Перспектива (vision):** гибрид — простые схемы считаются в браузере, тяжёлые уходят на сервер
  (**Xyce**) через очередь **Celery + Redis**; туда же — массовый Monte-Carlo, PCB-проверки в масштабе
  и обучение нейросетевого предсказателя (GNN). Это и есть «перерабатывать всё».

**Могут спросить:** «Потянет ли ngspice на сервере большие схемы?» → *Для интерактива в браузере —
да; для тяжёлых серверных расчётов он однопоточный и не идеален, поэтому на сервер планируется
параллельный Xyce, а ngspice остаётся в браузере. Связывает их очередь задач (Celery+Redis).*

## 4. Редактор схем, провода, спецификация (BOM)
### 4.1. Редактор и провода
- УГО-режим (ГОСТ-обозначения); **умная разводка прямо в редакторе схем**: провода **ортогональные**,
  выводы **магнитные**, на пересечении автоматически ставится **узел**, есть **изгибы**. Метки цепей
  (GND/+5V/OUT). Библиотека компонентов расширяется JSON-шаблонами.
- **Важно (ответ на «почему трассировка только в CAD»):** надо различать два слоя.
  - **Схема** — это *логические* связи. Здесь и работает ортогональная умная разводка (она в редакторе схем есть).
  - **PCB/CAD** — это *физическая* плата: дорожки из меди, зазоры, правила. Здесь работает
    **A*-автотрассировщик** (поиск пути по сетке 0,5 мм со штрафом за поворот). Автотрассировка
    дорожек — это задача именно платы, на схеме её делать незачем (там связи логические, а не медь).
  - То есть ортопровода и автотрассировка — **в нужных слоях**, а не «только в CAD»: в схеме —
    логическая разводка, на плате — физическая трассировка.
- **Связь логики схемы с логикой платы (forward annotation) — важное направление.** Эти два слоя не
  должны жить отдельно: **логические связи (цепи) из схемы должны напрямую задавать связность платы**.
  Мост между ними — **netlist (список цепей)**: схема описывает, *что с чем соединено* (граф цепей),
  и именно эта связность переносится на плату как «обязательства соединить» (ratsnest), по которым
  затем работает автотрассировщик. Благодаря этому при составлении схемы не нужно «лепить всё прямо»
  физически — рисуешь логику, а физическую разводку плата получает из этих же цепей. Сейчас связь идёт
  через общий netlist; дальнейшее развитие — полноценная **двусторонняя синхронизация схема↔плата**
  (изменил цепь в схеме → обновилась связность платы, и наоборот). *(детали допишу отдельно)*

### 4.2. BOM — спецификация (ключевой мост «схема → покупка»)
**BOM (Bill of Materials, спецификация)** — список всех компонентов схемы с количеством и привязкой к
товарам каталога. Как работает:
- компоненты схемы **группируются** (одинаковые — в одну позицию с количеством);
- каждая позиция **связана с реальным товаром** каталога (артикул, цена, наличие);
- BOM **выгружается в CSV/XLSX** и кнопкой **«добавить всё в корзину»** превращается в заказ.

Это и есть практическая ценность работы: проектирование напрямую смыкается с покупкой, без ручного
переноса между САПР и магазином.

**Могут спросить:** «Что такое BOM и как он у вас формируется?» → *Спецификация компонентов из схемы:
группируем элементы, привязываем к товарам каталога, выгружаем в CSV/XLSX и добавляем в корзину одним
действием.*

## 5. Рендеринг 2D — почему Canvas2D И WebGL/Pixi (вопрос «зачем два»)
- **Canvas2D — база.** Простой API, полный контроль над УГО, проводами, сеткой и слоями-подсказками,
  чёткий текст, лёгкий hit-test (попадание курсора в порт). Для типовых учебных схем (десятки–сотни
  элементов) его **с запасом хватает**.
- **WebGL/Pixi.js — ускоритель.** Подключается **только когда элементов очень много** (сотни–тысячи),
  где Canvas2D начинает тормозить (он перерисовывает всё за кадр). GPU тянет тысячи объектов на высоком FPS.
- **Почему не оставить один:**
  - только Pixi/WebGL — **избыточно и сложнее**: GPU-состояние, текст и УГО рисовать труднее, больше
    кода и поддержки; на маленьких схемах выигрыша нет;
  - только Canvas2D — **упрётся** на очень больших схемах.
- **Решение — двухуровневое (progressive enhancement):** по умолчанию Canvas2D, авто-переключение на
  Pixi. Сейчас триггер простой — порог числа элементов.
- **Куда развивать (сильный ответ на «почему просто порог»):** сделать **авто-анализ и выбор рендера
  по набору критериев**, а не по одному числу. Критерии: число компонентов + соединений (вес сцены),
  текущий зум и сколько объектов реально в кадре, возможности устройства (есть ли аппаратный WebGL,
  мобильное/слабое железо) и, главное, **замер фактического FPS**: если на Canvas2D частота кадров
  при перерисовке падает ниже порога (например, < 30 FPS) — система сама переключается на Pixi, и
  наоборот. То есть движок отрисовки выбирается **адаптивно по реальной нагрузке**, а не по жёсткому
  числу. Это запас по масштабу под «комбайн» с большими схемами.

**Могут спросить:** «Зачем для 2D и Canvas, и WebGL?» → *Canvas2D — простой и достаточный для обычных
схем; Pixi/WebGL подключается автоматически только на очень больших схемах, где Canvas2D тормозит. Это
запас по производительности, по умолчанию работает простой режим.*

## 6. AI-ассистент — подробно (что за технологии и зачем)
Ассистент **локальный**, не зависит от внешних языковых моделей. Устроен как **диспетчер**: понимает
запрос и вызывает нужный движок из реестра. Технологии и **зачем каждая**:
- **`rule_ai` (оркестратор)** — определяет намерение запроса и выбирает движок; собирает ответ из
  фактов схемы, BOM, результатов проверки и статей справочника.
- **`ai_algorithms` (реестр движков)** — расчёт напряжений (MNA), Monte-Carlo, РЧ-параметры (scikit-rf),
  подбор номиналов. *Зачем:* число в ответе берётся из **проверяемого расчёта**, а не «придумывается».
- **jsonschema** — проверяет, что структура схемы/данных корректна. *Зачем:* отсечь битые данные до расчёта.
- **rule-engine (правила)** — декларативные правила DRC/ERC: «нет земли», «висящий вывод», «перегрев».
  *Зачем:* объяснимые проверки схемы, которые легко дополнять без правки кода.
- **Pint (единицы измерения)** — считает в физических единицах (Ом, В, Ф, Гц). *Зачем:* не перепутать
  кило/милли и размерности — типичная инженерная ошибка.
- **Lark (парсер)** — разбирает SPICE/нетлисты и импортируемые форматы по грамматике. *Зачем:* надёжно
  читать внешние файлы (LTspice/KiCad/Lithium) и собственный netlist.
- **z3-solver (решатель ограничений)** — подбирает номиналы под условия (делитель на нужное
  напряжение, токоограничивающий резистор, времязадающая RC). *Зачем:* не перебор, а строгий подбор
  под заданные ограничения.
- **scikit-fuzzy (нечёткая логика)** — мягкая оценка «риска» проекта поверх чётких фактов. *Зачем:*
  свести разные сигналы (derating, BOM-риск) в понятную оценку.
- **GNN на PyTorch (перспектива)** — графовая нейросеть для предсказания напряжений в узлах; пока в
  работе по точности, поэтому идёт **надстройкой** над проверяемым расчётом, а не вместо него.
- **Порядок «сначала объяснимое»:** правила/факты → решатель ограничений → и только потом нейросеть.
  *Зачем:* советы остаются прозрачными и воспроизводимыми; вероятностные методы не подменяют проверку.

**Могут спросить:** «Это ChatGPT внутри?» → *Нет, ассистент локальный: правила + расчётные движки;
число всегда из проверяемого расчёта, внешняя LLM не нужна. Нейросеть (GNN) — перспективная надстройка
поверх проверяемого результата.*

## 7. 3D-инструменты и перспектива (отдельное направление)
- **Сейчас:** 3D-просмотр платы на **Three.js** — плата, слои, площадки, отверстия, дорожки, GND-зоны,
  процедурные модели корпусов компонентов; вращение (OrbitControls), экспорт PNG.
- **Зачем 3D:** увидеть плату и компоновку «вживую» до изготовления — это и наглядность для заказчика,
  и проверка габаритов/размещения.
- **Перспектива (сильное направление развития, можно подать как vision):** переход к **полноценному
  3D-CAD**. В идеале — **серверный/браузерный 3D** (без десктопного софта): геометрическое ядро через
  **pythonOCC / FreeCAD (headless) / CadQuery** в контейнере, экспорт в **STEP**, механические модели и
  корпуса (уровень КОМПАС-3D), сборки. Это превращает DOLG из «схема + плата» в полный маршрут
  «электроника + механика», что и есть следующий большой шаг комбайна.

**Могут спросить:** «Что с 3D и куда развивается?» → *Сейчас 3D-просмотр платы на Three.js; дальше —
полноценное параметрическое 3D через геометрическое ядро (pythonOCC/CadQuery) с экспортом STEP, чтобы
покрыть и механику, а не только электронику.*

## 8. Сколько всего реализовано (сервис-слой — на случай «а что ещё умеет?»)
Инженерная логика вынесена в **сервис-слой** (`Dolg_APP/services/`, свыше 30 модулей) — тонкие
вьюхи, толстые сервисы. Не нужно перечислять всё; держи в голове, что за фасадом «магазин + схема +
симуляция» стоит широкий набор готовых блоков. По группам:
- **Симуляция и расчёт:** `simulation_analysis` (метрики/замеры по результатам), `monte_carlo`
  (статистический разброс на NumPy), `rf_analysis` (РЧ-параметры через scikit-rf), `rule_ai` +
  `ai_algorithms` (диспетчер и реестр расчётных движков).
- **Проверки схемы (экспертный контур):** `expert_rules` + `expert_detectors` (DRC/ERC-правила и
  детекторы), `risk_scoring` (нечёткая оценка риска), `constraint_solver` (подбор номиналов через z3),
  `project_review` + `review_visualization` + `review_i18n` (сводный отчёт о здоровье проекта,
  визуализация, локализация), `protocol_report` (протокол/отчёт).
- **Схема и геометрия:** `schematic_graph` (граф цепей — основа netlist и BOM),
  `schematic_operations`, `schematic_layout_quality` (оценка качества расстановки), `autorouter`
  (A*-трассировщик платы), `engineering_units` (единицы через Pint).
- **Импорт/экспорт и интеграции:** `cad_import` + `cad_parsers` (чтение CAD-форматов),
  `lithium_import` (импорт формата Lithium ECAD), `circuit_python_export` (схема → код CircuitPython
  для плат RP2040/ESP32 — мост в железо), `artifact_ingestion` + `artifact_learning` (приём и
  обучение на загруженных артефактах).
- **AI-инфраструктура:** `ai_retrieval` (поиск/RAG как функция продукта), `ai_render`,
  `ai_toolkit`, `ai_training`, `ai_prompt_guard` (защита запросов), `learning_by_review`
  (обучение на разборах).
- **Эксплуатация и безопасность:** `ops_metrics` (метрики), `ssrf_guard` (защита от SSRF),
  `entitlements` (права/доступ к платным функциям).
- **Плюс прикладные домены:** магазин/каталог/корзина/заказы, база знаний и обучение (статьи,
  материалы, маршруты), аккаунты с **SSO (allauth: Google/MS/GitHub)** и 2FA.

**Могут спросить:** «А это всё работает или заглушки?» → *Ядро (каталог, редактор, симуляция, BOM,
проверки, импорт/экспорт) работает; часть (серверная симуляция, GNN, полноценный 3D-CAD) — задел и
перспектива, я честно их разделяю.*

## 9. Качество и проверки
Django check — 0 замечаний; ~130 автотестов; 16 браузерных e2e (canvas, модалки, CAD, экспорт); линтер
ruff + проверки безопасности на коммите. Экспертная проверка проекта: Design Health Score, DRC/ERC,
риск BOM, derating.

## 10. Как говорить про использование ИИ
Спокойно и честно: *ИИ — вспомогательный инструмент (черновики/редактура текста, помощь по коду,
перевод, поиск источников). Концепция, архитектура и проектные решения мои; код понимаю, проверял,
могу развивать. Использование задекларировано и согласовано с руководителем.* Дальше — готовность
объяснить любой модуль.

## 11. Чек-лист
- [ ] Понимаю разделы 2–7 и могу объяснить своими словами (особенно симуляция, BOM, AI, 3D-перспектива).
- [ ] Могу вживую: собрать делитель/мост, запустить DC/AC, показать BOM и выгрузку.
- [ ] Готов на вопросы: монолит + Postgres/JSONB; почему ngspice (альтернативы); серверная симуляция и
  «комбайн»; два слоя рендера (Canvas/Pixi); схема vs PCB (ортопровода vs A*); локальный AI и его движки; 3D-вектор.
- [ ] Декларация согласована с руководителем; уточнил сервис антиплагиата.

---
*Спрашивай по любому пункту — объясню глубже или устрою репетицию вопросов комиссии.*

---

## DIPLOMA GIA AI POLICY

Источник: `DIPLOMA_GIA_AI_POLICY.md`

# Разбор: Положение о ГИА + Положение о проверке на заимствования и ИИ (РГЭУ РИНХ, 2025/2026)

Анализ двух ЛНА применительно к твоей ВКР (бакалавриат, IT-проект DOLG), который **активно
редактировался/дополнялся с помощью ИИ**. Главный для тебя — второй документ (ИИ + Антиплагиат).

---

## 1. Положение о ГИА — что важно для бакалавра

- **Рецензия НЕ нужна.** §4.9: рецензированию подлежат только специалитет и магистратура.
  Для бакалавра — только **отзыв руководителя** (§4.8). (Это снимает пункт из старого чек-листа.)
- **Формы ГИА** (§2.1): госэкзамен и/или защита ВКР — смотри свою программу ГИА.
- **Оценки** (§4.14): отлично / хорошо / удовлетворительно / неуд.
- **Сроки** (жёсткие, заложи время):
  - расписание — за ≥30 дней до первого испытания (§4.7);
  - отзыв руководителя — после готовности ВКР (§4.8);
  - ознакомление с отзывом — за ≥5 дней до защиты (§4.10);
  - ВКР + отзыв в ГЭК — за ≥2 дня до защиты (§4.11);
  - **текст ВКР проверяется на заимствования И на использование генеративного ИИ** (§4.12) → см. документ 2.
- На защите ВКР выступление — обычно до ~10–15 мин; ГЭК задаёт вопросы, фиксирует уровень
  подготовленности (протокол, Приложение 3).

## 2. Положение о проверке на заимствования и ИИ — ГЛАВНОЕ (вступает в силу 01.05.2026)

### 2.1. Антиплагиат (оригинальность)
- §3.4: окончательный текст руководителю **за ≥14 дней** до защиты, форматы doc/docx/odt/rtf/txt,
  **имя файла**: `<год защиты>_<код профиля>_<ФИО>`.
- §3.2: на проверку грузится текст **без** титульного, оглавления, списка литературы и приложений.
- §3.5: **оригинальность (оригинальность + самоцитирование) ≥ 40 %** для бакалавриата.
  (Цитирование ≤10 % — требование для магистратуры; для бакалавра ключевое — ≥40 % оригинальности.)
- §3.7–3.8: если мало — доработка и повторная проверка за ≥7 дней до защиты.

### 2.2. Проверка на генеративный ИИ — НОВОЕ и прямо про твою ситуацию
- §4.2: **если ты использовал генеративный ИИ — ОБЯЗАН подать декларацию** (Приложение 1) с:
  частями работы, сделанными ИИ; названием и URL модели; целью и способом; степенью участия ИИ;
  (если был RAG для написания работы — источники базы).
- §4.4: автоматическая проверка помечает «потенциально ИИ-фрагменты» (предварительно, само по
  себе не повод для доработки).
- §4.5: руководитель делает **экспертный анализ**: полнота декларации, стиль/содержание, проверка
  фактов/цитат/источников на реальность, «аномалии уникальности» в визуале.
- §4.6 (⚠️ ДЛЯ ТЕХНАПРАВЛЕНИЙ): руководитель вправе провести **устный опрос, live-кодинг,
  тестирование на понимание** — чтобы убедиться, что ты реально владеешь материалом.
- §4.10 — решения руководителя:
  - **4.10.1**: ИИ использован легитимно **и задекларирован** → допускает, отключает ИИ-детекцию
    с формулировкой «Использование ИИ легитимно». ← **целевой сценарий для тебя**.
  - 4.10.2: ложное срабатывание (подтверждено экспертом ЦИИиТР) → допускает.
  - **4.10.3**: ИИ использован, **но НЕ задекларирован → доработка** (заставят составить декларацию).
  - 4.10.4: ИИ использован нелегитимно → доработка (убрать/переписать ИИ-фрагменты).
- §5: ВКР в ЭБС за ≥4 дня до защиты; грузится PDF с **отсканированным подписанным титульным**
  + отзыв с оригинальностью и инфо об ИИ; согласие на размещение (Приложение 3).

### 2.3. Что это значит конкретно для тебя
1. **Скрывать ИИ — худший вариант.** Детектор + экспертный анализ руководителя, скорее всего,
   подсветят ИИ-фрагменты. Нет декларации → п. 4.10.3 (доработка) и подозрение. Положение само
   **легитимизирует задекларированное использование ИИ как вспомогательного инструмента** —
   поэтому правильный путь: **задекларировать честно**.
2. **Текст должен стать твоим.** Декларация заканчивается гарантией: «основные выводы и положения
   — мой собственный интеллектуальный продукт, не сгенерированы ИИ». Значит ИИ-черновики (проза
   Главы 2, блоки Введения) надо **вычитать, переписать своими словами и понимать** — тогда гарантия
   правдива, и ИИ-детектор сработает слабее.
3. **Готовься к live-кодингу и вопросам по сути.** Это IT-ВКР → по §4.6 могут попросить вживую
   объяснить/написать код, разобрать архитектуру (MNA-солвер, модули, netlist, симуляция). Проект —
   твой (ты строил DOLG месяцами), но всё, что в тексте, ты должен уметь объяснить и показать.
4. **Прочитай «Политику использования генеративного ИИ»** (§4.1 ссылается на неё — её в этих файлах
   нет). Там заданы допустимые сферы, ограничения и, возможно, перечень допустимых моделей. Это
   определяет, что считается «легитимным» использованием. Возьми её на кафедре/сайте.

## 3. План действий (по шагам)

1. **Снизить ИИ-след в тексте**: вычитать и переписать своими словами ИИ-абзацы (Введение, проза
   Главы 2), убрать шаблонные обороты. Цель — текст читается как твой и ты его понимаешь.
2. **Заполнить декларацию об ИИ** (Приложение 1) — черновик: [DIPLOMA_AI_DECLARATION_DRAFT.md](DIPLOMA_AI_DECLARATION_DRAFT.md).
   Указать честно: что ИИ помогал с черновиками/редактурой текста, модель(и), степень участия,
   что код/архитектура/результаты — твои.
3. **Прогнать антиплагиат заранее** (если есть доступ к вузовской системе или бесплатной проверке):
   убедиться в ≥40 % оригинальности; где ИИ/шаблон — переписать.
4. **Подготовиться к устной защите и возможному live-кодингу**: уметь объяснить каждый модуль,
   формулы (MNA, делитель, мощность, fc, Monte-Carlo), показать работу симулятора/редактора вживую.
5. **Оформление под §3.4/§5**: имя файла `2026_<кодпрофиля>_Фамилия`, титульный по форме (Приложение 1
   Положения о ГИА), отсканированный подписанный титул для ЭБС, согласие на ЭБС (Приложение 3).
6. **Уточнить у руководителя**: какой антиплагиат-сервис у вуза, нужен ли госэкзамен, точные даты,
   и читал ли он/одобряет твою декларацию об ИИ (его виза легитимизирует использование — п. 4.10.1).

## 4. Честная оценка риска
Новое Положение прямо нацелено на ИИ-контент и даёт руководителю право на live-проверку. Твой плюс —
**проект реальный и твой** (большая кодовая база, которую ты вёл). Риск — в тексте ВКР, где много
ИИ-редактуры. Минимизируется: (а) честная декларация, (б) переписать/освоить текст, (в) уверенно
защищать вживую. Это и этично, и безопасно — Положение поощряет именно такой путь.

---

## DIPLOMA QUESTIONS FOR SUPERVISOR

Источник: `DIPLOMA_QUESTIONS_FOR_SUPERVISOR.md`

# Вопросы научруку и зав. кафедрой (взять на встречу)

Чеклист для личного разговора. Многое в Положениях о ГИА / проверке на ИИ и в Распоряжении №08
оставляет место для трактовки — это нужно подтвердить у руководителя и кафедры, чтобы не переделывать.
Сгруппировано по темам; отмечай ответы прямо здесь.

## A. Сроки и формат ГИА

- [ ] Точная **дата защиты** и дата предзащиты (если есть)?
- [ ] Какие **формы ГИА** у нашей группы: только защита ВКР или **ещё госэкзамен**?
- [ ] Жёсткие дедлайны сдачи (подтвердить из Положения): готовая работа руководителю **за 14 дней**,
      ознакомление с отзывом **за 5 дней**, передача в ГЭК **за 2 дня**, загрузка в ЭБС **за 4 дня** —
      это так для нас в этом году?
- [ ] Регламент выступления на защите — сколько минут доклад, нужны ли слайды/презентация?

## B. Антиплагиат и проверка на ИИ

- [ ] Какой **сервис антиплагиата** использует вуз (Антиплагиат.ВУЗ / другой)?
- [ ] Можно ли **прогнать работу заранее** самому (есть доступ для студентов) или только через кафедру?
- [ ] Подтвердить порог: **оригинальность ≥ 40%** для бакалавра — это актуальная цифра?
- [ ] Что именно грузится на проверку — **без** титульного, оглавления, списка литературы и приложений
      (как в Положении)?
- [ ] Положение о проверке на ИИ вступает в силу **01.05.2026** — оно **применяется к нашей защите**
      или мы ещё по старым правилам?

## C. Декларация об использовании ИИ (Приложение 1) — это первый год

- [ ] **Нужна ли декларация** в нашем случае и по какой форме (у нас это впервые, единого образца нет)?
- [ ] Где взять «**Политику использования генеративного ИИ**» вуза (§4.1 Положения ссылается на неё, но
      в открытом доступе и на ЭИОС её нет)? Какие модели/сферы там считаются допустимыми?
- [ ] Как **корректно задекларировать использование ИИ в написании кода** (для IT-направления это
      чувствительный момент) — что именно писать в графе про исходный код?
- [ ] Готов ли руководитель **завизировать декларацию** (его согласие легитимизирует использование —
      п. 4.10.1, «использование ИИ легитимно»)?
- [ ] RAG для написания текста работы **не применялся** — это указывать отдельно? (RAG есть как функция
      самого приложения, к тексту ВКР отношения не имеет.)

## D. Структура, объём, оформление

- [ ] Подтвердить: **2 главы** (теория + проектирование) достаточно, **3-я глава не нужна**
      (вы советовали укрупнить главы — мы свели Главу 2 к 3 параграфам)?
- [ ] Минимальный **объём основного текста ≥ 40 страниц** без приложений — это норма для нас?
- [ ] **Список литературы**: оставить группировку по типу источников (ГОСТы → доки → учебники →
      зарубежные → электронные) с алфавитом внутри групп, или нужен сплошной алфавит?
- [ ] **Приложения и рисунки/таблицы — везде цифрами** (вы это уже говорили) — подтверждаем, что
      буквенных обозначений нигде быть не должно?
- [ ] **Имя файла** для сдачи: формат `<год>_<код профиля>_Фамилия` — какой именно **код профиля** у
      09.03.03 Прикладная информатика подставлять?

## E. Защита и проверка на понимание (для IT-направления)

- [ ] Будет ли **устный опрос / live-coding / тест на понимание** (§4.6 даёт руководителю это право)?
      В каком формате готовиться — объяснить архитектуру, разобрать модуль, дописать кусок кода?
- [ ] Можно ли на защите **показать работу вживую** (демо редактора схем, симуляции, BOM) — есть ли
      проектор/интернет, или готовить запись?
- [ ] Нужна ли **презентация** и сколько слайдов; есть ли шаблон оформления?

## F. Документы и подписи

- [ ] Подтвердить, что **рецензия не нужна** (только отзыв руководителя — для бакалавра)?
- [ ] **Задание на ВКР** (отдельный лист с подписями зав. кафедрой/руководителя/студента) — кто и когда
      подписывает, есть ли актуальный бланк?
- [ ] **Последний лист** «работа выполнена мною самостоятельно…» + «пронумеровано ___ страниц» —
      нужен ли и по какому образцу?
- [ ] Для ЭБС: PDF с **отсканированным подписанным титульным** + отзыв + согласие на размещение
      (Приложение 3) — собрать заранее, какой порядок?

---

*Источник вопросов: открытые места в Положении о ГИА, Положении о проверке на заимствования и ИИ,
Распоряжении №08 и черновике декларации. Подробный разбор — в [DIPLOMA_GIA_AI_POLICY.md](DIPLOMA_GIA_AI_POLICY.md)
и [DIPLOMA_CHECKLIST.md](DIPLOMA_CHECKLIST.md).*

---

## DIPLOMA UPDATES

Источник: `DIPLOMA_UPDATES.md`

# Готовые правки для ВКР (вставлять в Word)

Дополняет [DIPLOMA_CHECKLIST.md](DIPLOMA_CHECKLIST.md). Здесь — готовый текст и данные для вставки.
Рисунки нумеруются **только цифрами** (указание научрука) — без букв приложений.

## 1. Актуальные цифры (заменить во всех местах: Введение, 2.1, Заключение, Приложение)

Сверено с БД проекта на 2026-06-08:

| Показатель | Было в дипломе | Стало (актуально) |
|---|---|---|
| Товаров в каталоге | 89 (+43 РЭБ) | **364** товара |
| Категорий | — | **23** категории |
| — потребительская электроника | — | ~47 (SSD, GPU, CPU, мониторы, ноутбуки и т.д.) |
| — радиоэлектронные компоненты | 43 | ~317 (резисторы 78, модули 35, микросхемы 34, конденсаторы 27, диоды 25, транзисторы 21, разъёмы 20 и др.) |
| Статей энциклопедии | 21 | **22** |
| Доп. материалов (ArticleMaterial) | 50 | **99** |
| Демонстрационных схем (is_demo) | 12 | **12** ✅ |
| Проектов схем всего | — | 28 |
| Учебных маршрутов / уроков / заданий | 4 / 13 / 29 | доверифицировать перед печатью |

> ⚠️ 364 — это НЕ дубли (имена уникальны, дублей part_number всего 3). Каталог реально вырос.
> Чистка не нужна — нужно обновить число. **Скриншоты каталога (Рис. в Приложении) переснять** —
> старые показывают «4 товаров» в категории, сейчас десятки.

## 2. Введение — готовые блоки (вставить недостающие элементы)

**Объект исследования** — процессы веб-ориентированного проектирования, симуляции и приобретения
радиоэлектронных компонентов в едином онлайн-контуре.

**Предмет исследования** — архитектура и программная реализация веб-платформы, объединяющей каталог
электронных компонентов, интерактивный редактор принципиальных схем и модуль SPICE-симуляции.

**Гипотеза** — объединение интернет-магазина компонентов, веб-САПР и SPICE-симуляции в одном
веб-приложении с привязкой графических элементов схемы к реальным товарам каталога позволяет
сократить время подбора и проверки компонентов и снизить число ошибок переноса данных между
разрозненными инструментами.

**Методология исследования** — анализ предметной области и рынка аналогов; сравнительный анализ
существующих онлайн-САПР и SPICE-сред; объектное проектирование базы данных и архитектуры на основе
Django ORM; прототипирование клиент-серверного взаимодействия; функциональное и браузерное
(smoke/e2e) тестирование реализованных модулей.

**Структура работы** — работа состоит из введения, двух глав, заключения, списка из 42 источников
и приложений. В первой главе выполнен анализ предметной области, рынка аналогов, сформированы
требования и обоснован выбор средств разработки. Во второй главе спроектированы и реализованы
технологический стек, база данных, серверная и клиентская части, модули проектирования и симуляции.

## 3. Формулы (методы расчёта) — для Главы 2.6 «Модуль симуляции»

Оформление по ГОСТ: формула на отдельной строке, номер «(2.N)» справа, после — «где …».
Это реальные методы, заложенные в движках проекта (`monte_carlo.solve_dc`, `ai_toolkit`).

**Узловой анализ (модифицированный, MNA)** — ядро DC-решателя:

    G · V = I,                                                         (2.1)

где G — матрица проводимостей узлов; V — вектор узловых потенциалов (искомый); I — вектор втекающих
токов источников. Система формируется из законов Кирхгофа и решается численно (NumPy `linalg.solve`).

**Делитель напряжения** (проверка узлов в DC):

    Vout = Vin · R2 / (R1 + R2),                                       (2.2)

где Vin — входное напряжение; R1, R2 — сопротивления плеч делителя; Vout — напряжение на R2.

**Рассеиваемая мощность на резисторе** (тепловая нагрузка, derating):

    P = ΔU² / R = I² · R,                                              (2.3)

где ΔU — падение напряжения на резисторе; R — сопротивление; I — ток через резистор.

**Частота среза RC-фильтра (−3 дБ)** — АЧХ-анализ:

    fc = 1 / (2π · R · C),                                             (2.4)

где R — сопротивление; C — ёмкость; fc — частота среза по уровню −3 дБ.

**Ток ограничительного резистора светодиода** (закон Ома):

    I_LED = (Vin − Vf) / R,                                           (2.5)

где Vin — напряжение питания; Vf — прямое падение на светодиоде; R — сопротивление резистора.

**Доверительный интервал Monte-Carlo** (анализ разброса номиналов):

    Δ = ±1,96 · σ,                                                     (2.6)

где σ — среднеквадратичное отклонение результата по выборке симуляций; Δ — полуширина 95-% интервала.
Применяется для оценки худшего случая (worst-case) при разбросе номиналов компонентов (±5 %).

## 4. Нумерация приложений и рисунков — ВЕЗДЕ ЦИФРАМИ, без букв (требование научрука)

- Приложения — **цифрами 1–6** (в версии 6 .docx уже так: Приложение 1…6 ✓). Буквы НЕ используем.
- Таблицы приложений — **цифрами** (Таблица 1.3 и т.п. — уже так в .docx).
- **Рисунки — сквозная числовая нумерация по всей работе: Рисунок 1, 2, 3 … N** (без букв и без «глава.номер»).
  Сейчас в работе ~13 рисунков — пронумеровать 1…13 по порядку появления.

  | Текущая подпись | → Новый номер |
  |---|---|
  | Рис. 2.1 Главная и верхний блок каталога | Рисунок 1 |
  | Рис. 2.2 Полки категорий | Рисунок 2 |
  | Рис. 2.3 Карточка товара | Рисунок 3 |
  | Рис. 2.4 Похожие товары | Рисунок 4 |
  | Рис. 2.5 Статья энциклопедии | Рисунок 5 |
  | Рис. 2.6 Редактор схем + симуляция | Рисунок 6 |
  | Рис. 2.7 АЧХ | Рисунок 7 |
  | Рис. 2.8 ФЧХ | Рисунок 8 |
  | Рис. 3.1 Диаграмма последовательности | Рисунок 9 |
  | Рис. 3.2 Диаграмма классов | Рисунок 10 |
  | Рис. 3.3 Диаграмма состояний | Рисунок 11 |
  | Рис. В.4 Диаграмма процесса покупки | Рисунок 12 |
  | Рис. В.5 Детализированная диаграмма последовательности | Рисунок 13 |

- **Таблицы** — внутри приложений по букве (Таблица А.1, А.2 … Б.1 …) ЛИБО тоже цифрами сквозь — уточнить
  у научрука (он сказал про рисунки; для таблиц правило ГОСТ допускает «А.1»). Сейчас в Приложениях
  таблицы пронумерованы вразнобой (А.1, 1.2, 1.3, А.4, 5.1, 5.2) — в любом случае унифицировать.
- На **каждый** рисунок/таблицу — ссылка в тексте («…показано на рисунке 1», «см. таблицу А.1»).

## 5. Что перенести в Word и что перепроверить

- [ ] Вставить блоки Введения (§2 выше) → довести введение до 3–5 страниц.
- [ ] Заменить цифры каталога/статей/материалов (§1) во всех местах.
- [ ] Добавить формулы (§3) в 2.6 + ссылки на них в тексте.
- [ ] Перенумеровать приложения (А–Е) и рисунки (1…13) (§4).
- [ ] Перенять скриншоты каталога (вырос до 364 товаров).
- [ ] Заменить длинное тире «—» → «–» по всему документу.
- [ ] Довести параграфы Главы 2 до ≥4 страниц (черновики прозы — отдельно).

---

## DOLG Diploma reworked 20260603

Источник: `DOLG_Diploma_reworked_20260603.md`

# Рабочая двухглавная редакция диплома DOLG

Дата сборки: 2026-06-03

Файл DOCX: `DOLG_Diploma_reworked_20260603.docx`

## Структура

- Введение
- Глава 1. Анализ предметной области и проектирование системы
- Глава 2. Реализация программной системы
- Заключение
- Источники
- Приложения

## Факты локальной БД

- Товары: 364
- Категории: 23
- Проекты схем: 28
- ProjectEvent: 33
- ProjectReview: 1
- Статьи: 22
- Материалы статей: 99
- Learning tracks: 5
- Learning lessons: 16
- Learning tasks: 38
- AITrainingExample: 72

## Вставленные изображения и графики

- Главная страница и каталог.
- Карточки компонентов.
- Карточка товара и связанные товары.
- CAD-редактор и шаблон схемы.
- Симуляция, AC-график, панель AC-анализа и фазовый график.
- Инженерная лаборатория.
- Engineering Review-график вместо устаревшей Pro-картинки.
- AI/ML pipeline.
- Knowledge materials.
- Admin/monitoring metrics.

## Что сделать дальше

1. Заменить черновые абзацы на полный академический текст.
2. Добавить ERD/UML/BPMN-диаграммы.
3. Захватить живой screenshot страницы Engineering Review `/projects/review/<id>/` и admin Ops Dashboard.
4. Перед финальной сборкой подтвердить цифры через `check_demo_ready --json` и `check_data_integrity --json`.
5. После диплома пересобрать презентацию и речь под эту же двухглавную структуру.

---

## ENGINES COMPARISON

Источник: `ENGINES_COMPARISON.md`

# Сравнение движков симуляции + compute-бэклог

Три живых движка в DOLG (+ NumPy MNA как эталон-учитель). Цель документа: зафиксировать
**различия с цифрами/фактами** и **список вычислений, которые уже можно реализовать** поверх
индустриальных движков.

## Кросс-валидация

Все три движка на линейном DC совпадают **точно** (max|Δ| = 0 на divider/series/ladder).
Значит выбор движка — про **масштаб, скорость и device-модели**, а не про правильность.

## Бенчмарки (резисторная сетка N×N, DC, эта машина)

| N | узлов | элементов | NumPy MNA (плотный) | Xyce (разреженный) |
|---|---|---|---|---|
| 40 | 1601 | 3122 | **0.56 с** | ~7 с (доминирует старт) |
| 60 | 3601 | 7082 | **4.2 с** | 7.65 с |
| 100 | 10001 | 19802 | **92.5 с** ⚠️ | **19.6 с** ✅ (×4.7) |

**Кроссовер между N=60 и N=100.** Плотная MNA — память `O(N²)`, время `O(N³)` → стена ~10k
узлов (92.5 с). Разреженный Xyce держится (19.6 с). Старт процесса Xyce (~1–2 с) проигрывает на
мелочи, но амортизируется на масштабе.

## Три движка

| | NumPy MNA | ngspice 46 (PySpice) | Xyce 7.10.0 |
|---|---|---|---|
| Метод | Modified Nodal Analysis | Berkeley SPICE | Sandia parallel SPICE |
| Solver | **плотный** numpy.linalg.solve | разреженный **KLU** | разреженный **KLU**/**ShyLU** |
| Параллелизм | нет | серийный | **параллельный** (ShyLU до ×20 на 200 ядрах) |
| Запуск | in-process, 0с старт | in-process (DLL) | shell-out (~1–2с старт) |
| Анализы | DC/tran(BE)/AC/MC | DC/tran/AC | DC (tran/AC — парсеры в работе) |
| Device-модели | упрощённые (Шокли) | реальные SPICE | реальные SPICE + HPC |
| Зависимости | только NumPy | PySpice + ngspice DLL | бинарь 128МБ (engines/xyce) |
| Масштаб | ≤ ~3k узлов | средний | **миллионы элементов** |

**Когда что:** мелкие/частые задачи → MNA (мгновенно, без зависимостей); реальные модели/
нелинейщина → ngspice; огромные схемы (10k+ узлов)/эталон → Xyce.

## Compute-бэклог: что уже можно реализовать

Индустриальные движки разблокируют анализы, которых у самодельной MNA нет. Сгруппировано;
P0 = дёшево и ценно, P1 = средне, P2 = продвинутое.

### A. Новые типы анализа (нативны в ngspice/Xyce)
| Анализ | SPICE | Что даёт инженеру | Движок | P |
|---|---|---|---|---|
| DC-свип (ВАХ) | `.DC src a b step` | I-V характеристики, передаточные кривые | все | **P0** |
| Передаточная функция | `.TF out src` | коэф. передачи по DC, входное/выходное сопротивление | ngspice/Xyce | **P0** |
| Параметрический свип | `.STEP`/`.DC` по параметру | семейство кривых по номиналу/температуре | Xyce/ngspice | P1 |
| Температурный | `.TEMP` / `.DC TEMP` | дрейф рабочей точки по температуре | все | P1 |
| Шум | `.NOISE` | спектр входного/выходного шума, noise figure | ngspice/Xyce | P1 |
| Чувствительность | `.SENS` | dOut/dParam по каждому элементу → что критично | ngspice/Xyce | P1 |
| Фурье / FFT | `.FOUR` / `.FFT` | гармоники, **THD** (нелинейные искажения) | ngspice/Xyce | P1 |
| Полюса-нули | `.PZ` | устойчивость, полоса по полюсам | ngspice | P2 |
| Искажения | `.DISTO` | интермодуляция, искажения | ngspice | P2 |
| Harmonic Balance | `.HB` | RF steady-state (усилители/смесители) | Xyce | P2 |

### B. Метрики из волн (post-processing над tran/AC/DC)
- **Из transient:** время нарастания/спада (10–90%), overshoot, settling time, slew rate,
  период/частота, скважность, задержка распространения, THD (через FFT). Нативно — `.MEASURE`
  в ngspice/Xyce (rise/fall/delay/trig-targ).
- **Из AC:** полоса −3 дБ, запас по усилению/фазе (**gain/phase margin** — устойчивость), Q,
  резонансная частота, Боде с авто-разметкой.
- **Из DC:** рабочая точка, **мощность на каждом элементе** (P=U·I) → нагрев/derating,
  запас по нагрузке.

### C. Масштабное (где Xyce окупается)
- **Power-grid / IR-drop карты:** наша сетка N×N → поле напряжений → 3D-поверхность падений.
- **Электротермика:** связка электрика+нагрев (Xyce поддерживает).
- **UQ / sensitivity на масштабе:** Монте-Карло и чувствительность на тысячах элементов.

### D. Надёжность / инженерия
- Monte-Carlo + worst-case **с реальными моделями** (не только разброс R/C).
- Ранжирование чувствительности → «какие 3 компонента решают исход».
- Derating-карта по мощности/току из реального операционного режима.

### Ближайшее (рекомендация)
1. **DC-свип (ВАХ)** + **`.TF`** — P0, дёшево, сразу полезно (диод/транзистор кривые, Rin/Rout).
2. **Авто-метрики из transient** (rise/overshoot/settling) + **AC gain/phase margin** — инженерный «вердикт».
3. **3D power-grid** (наша сетка → поле → 3D-поверхность) — вау-демо под Xyce.
4. Затем `.NOISE` / `.FOUR(THD)` / `.SENS`.

## Источники
- [Xyce: A Parallel Electronic Simulator — Overview](https://www.researchgate.net/publication/255268987_The_Xyce_Parallel_Electronic_Simulator_-_An_Overview)
- [A Fast Parallel Sparse Solver for SPICE (Tsinghua, DATE'15)](https://nicsefc.ee.tsinghua.edu.cn/nics_file/pdf/publications/2015/DATE15_23.pdf)
- [KLU sparse direct solver in ngspice](https://www.researchgate.net/publication/254041555_KLU_sparse_direct_linear_solver_implementation_into_NGSPICE)
- [Xyce vs ngspice (EDAboard)](https://www.edaboard.com/threads/xyce-circuit-simulator-vs-ngspice-circuit-simulator.315049/)

---

## GITHUB SECURITY SETUP

Источник: `GITHUB_SECURITY_SETUP.md`

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

---

## INSTRUMENTS PLAN

Источник: `INSTRUMENTS_PLAN.md`

# План: виртуальные приборы (ОБУЧАЮЩИЙ контекст)

> Скоуп уточнён (20260621): «Виртуальная лаборатория» используется **для обучения**, отдельной
> кнопкой из симулятора она убрана. Этот план — для учебной стороны (приборы как тренажёр). Фокус
> симулятора — 3D-визуализация графиков/схем + анимации, см. **VISUALIZATION_3D_PLAN.md**.

Решения по курсу (от 20260621):
- **Ток-по-проводам — НЕ делаем**: стрелки уже показывают направление/величину, дубль не нужен.
- **Фокус анимации — приборы**, а не декор. Анимация ценна, когда это *поведение прибора*
  (живая развёртка, показания, отрисовка трассы), а не украшение.
- Приборы живут в **существующей** «Виртуальной лаборатории» / Engineering Review — расширяем
  её, не плодим случайные кнопки.

## Что уже есть (инвентаризация)

| Прибор | Где | Состояние |
|---|---|---|
| Осциллограф (scope) | Лаб-док, таб 📺 | есть, с курсорами |
| Мультиметр | Лаб-док, таб 🔢 | есть, 7-сегмент + аналоговая стрелка на canvas |
| Генератор сигналов | Лаб-док, таб 〰️ | есть (таб) |
| FFT / спектр | Review-модал | есть |
| Боде (АЧХ/ФЧХ) | Review-модал | есть |
| Monte-Carlo | Review-модал | есть |
| Signal Quality | Review-модал | есть |
| Probes (кросс-проба схема↔прибор) | Лаб-панель | есть |

Вывод: база сильная. Не переписываем — **аудитим, оживляем, добавляем недостающее**.

## Что реально важно для анимации (а что нет)

**Важно (поведение прибора → ясность + вау):**
- **Живая развёртка осциллографа** — трасса «рисуется» пером слева-направо, луч бежит, триггер-
  маркер; курсоры плавные.
- **Плавная стрелка/показания** мультиметра (стрелка есть — довести демпфирование/easing; цифры
  tween, а не скачок).
- **Превью волны генератора** — выбранная форма (sine/square/pulse/sweep) анимированно «живёт».
- **Playback переходного** — слайдер времени → ВСЕ приборы (scope/mm) обновляются по кадрам.
- **Отрисовка кривой curve-tracer/Боде** по мере свипа.

**Не важно / отказ:** бегущие точки тока по проводам (стрелки достаточно), тяжёлые шейдеры/PBR
(прошлый откат), декоративные частицы без смысла.

## Целевой набор приборов (existing + gaps под compute-бэклог)

| Прибор | Источник данных (движок/анализ) | Состояние | Аним. | P |
|---|---|---|---|---|
| Осциллограф | transient waveforms | есть → **оживить развёртку** | живая трасса | **P0** |
| Мультиметр | DC op-point (V/I/R) | есть → отполировать стрелку/цифры | tween/демпфер | **P0** |
| Генератор сигналов | задаёт источник | есть → **превью волны** | анимация формы | P1 |
| **Curve tracer (ВАХ)** | **`.DC`-свип** (диод/транзистор I-V) | **НЕТ → добавить** | прорисовка кривой | **P0** |
| **Ваттметр / мощность** | DC op-point → P=U·I на элемент | **НЕТ → добавить** | живой бар/стрелка | P1 |
| Спектроанализатор (THD) | **`.FOUR`/FFT** | частично (FFT) → довести гармоники/THD | столбцы растут | P1 |
| Network analyzer (Боде) | AC sweep | есть → запас по усил./фазе + аним. свипа | кривая по свипу | P1 |
| Логический анализатор | digital tran | минимально → опц. | timing-диаграмма | P2 |
| Самописец (strip chart) | длинный transient | НЕТ → опц. | бегущая лента | P2 |

Новые приборы **идут в паре с compute-фичами** (curve tracer без `.DC`-свипа пуст, ваттметр без
расчёта мощности пуст) — см. [ENGINES_COMPARISON.md](ENGINES_COMPARISON.md) §compute-бэклог.

## Фазы работы

**Фаза 0 — аудит (до кода).** Пройтись по существующим приборам: какие реально питаются данными
симуляции, какие — заглушки/частичны. Зафиксировать факт. (Это уточнит, что «оживлять», а что
«доделывать».)

**Фаза 1 — оживить существующее (P0, без новых вычислений):**
- Осциллограф: живая развёртка/отрисовка трассы + триггер-маркер.
- Мультиметр: демпфирование стрелки + tween цифр.
- Эти — чистая фронт-анимация (Canvas/rAF), данные уже есть.

**Фаза 2 — новые приборы под compute (P0-P1, прибор+расчёт парой):**
- **Curve tracer** + `.DC`-свип (движки) → I-V диода/транзистора, прорисовка кривой.
- **Ваттметр** + расчёт мощности на элемент → нагрев/derating наглядно.

**Фаза 3 — продвинутое (P1-P2):**
- Спектроанализатор (THD из `.FOUR`), network analyzer с запасами устойчивости, playback
  переходного (слайдер → все приборы по кадрам), логический анализатор/самописец.

## Принципы
- Анимация = поведение прибора, не декор. Без бегущего тока по проводам.
- Новые приборы — в существующую лабораторию (табы/Review-модал), без случайных кнопок.
- 2D-анимация: Canvas + requestAnimationFrame, без либ. Тяжёлые шейдеры не тащим.
- Каждый новый прибор привязан к реальному вычислению движка (данные → визуализация).

## Рекомендованный старт
**Фаза 0 (аудит существующих приборов)** — 1 заход, чтобы план Фаз 1-2 был точным. Затем Фаза 1
(оживить scope+мультиметр — дёшево и заметно) параллельно с `.DC`-свипом под curve tracer.

---

## LEGAL RESOURCE MAP 20260526

Источник: `LEGAL_RESOURCE_MAP_20260526.md`

# Legal Resource Map для DOLG

Дата: 2026-05-26.

Источник первичного запроса: `https://vk.com/board51126445`, сообщество Physics.Math.Code. Прямой список тем VK без авторизации/динамического клиента не извлекается стабильно, поэтому использованы открытые поисковые сниппеты и публичные зеркала Telegram/VK как указатель на названия и темы, а не как источник скачивания файлов.

## Правило использования

- Пиратские архивы книг, ZIP/PDF/DJVU из постов и неофициальных зеркал не скачивать и не включать в репозиторий.
- Названия книг, темы постов и теги можно использовать как ориентиры для поиска легальных источников, библиографии и учебного плана.
- Для кода, диплома и обучения AI использовать официальную документацию, открытые учебники, datasheet, собственные схемы, demo-проекты и пользовательские схемы только с явным opt-in `allow_ai_training`.
- Если законной копии книги нет, фиксировать ее как "библиографический ориентир", но не использовать файл как обучающий корпус.

## Полезные сигналы из Physics.Math.Code

Эти пункты не являются разрешением на скачивание файлов из постов. Это только направления, которые стоит легально закрывать материалами и кодом:

- Схемотехника: Хоровиц/Хилл, справочники инженера-схемотехника, ТОЭ, ремонт и диагностика электроники.
- Электроника и физика: цепи постоянного/переменного тока, RC-цепи, диоды, транзисторы, операционные усилители, измерения.
- Python и backend: Django, CPython internals, структуры данных, алгоритмы, многопоточность.
- ML и PyTorch: базовое глубокое обучение, подготовка датасетов, классификация, explainability.
- Практика: задачи по электронике, разбор схем, подбор номиналов, диагностика неисправностей.

## Легальные источники, которые можно использовать

### Электроника и схемотехника

- All About Circuits Textbook - открытый учебник по DC, AC, semiconductors, digital circuits, RF и reference-разделам: https://www.allaboutcircuits.com/textbook/
- OpenStax University Physics Volume 2 - электричество, магнетизм, RC-цепи, измерительные приборы: https://openstax.org/details/books/university-physics-volume-2/
- Ngspice documentation - официальное руководство для SPICE-симуляции и netlist-логики: https://ngspice.sourceforge.io/docs.html
- LTspice от Analog Devices - официальная страница симулятора, schematic capture и waveform viewer: https://www.analog.com/en/resources/design-tools-and-calculators/ltspice-simulator.html
- KiCad documentation - проектный workflow, схема, PCB, ERC/DRC, SPICE и проектные файлы: https://docs.kicad.org/

### Python, Django и web-архитектура

- Django documentation - официальный источник по моделям, views, forms, auth, admin, tests: https://docs.djangoproject.com/
- Django Channels documentation - WebSocket/async слой для project-session уведомлений: https://channels.readthedocs.io/
- Python documentation - стандартная библиотека, typing, pathlib, csv/json, unittest: https://docs.python.org/

### Scientific stack и экспертный слой

- NumPy/SciPy/Matplotlib/Pandas docs - FFT, Bode, Monte Carlo, CSV/таблицы и графики.
- NetworkX algorithms - graph connectivity, paths, components, cycles, graph metrics: https://networkx.org/documentation/stable/reference/algorithms/index.html
- SymPy documentation - символьные формулы, эквивалентность выражений, вывод шагов: https://docs.sympy.org/
- Pint documentation - единицы измерения и unit-safe parsing номиналов: https://pint.readthedocs.io/
- Lark documentation - грамматики LTspice/SPICE/KiCad subset вместо ручного parsing: https://lark-parser.readthedocs.io/
- Z3 guide - constraint solving для подбора номиналов: https://microsoft.github.io/z3guide/
- scikit-fuzzy docs - мягкая оценка риска перегрева, слабого запаса и BOM-качества: https://scikit-fuzzy.github.io/scikit-fuzzy/

### PyTorch и будущий neural layer

- PyTorch Tutorials - официальный старт для datasets, training loop, inference и deployment: https://docs.pytorch.org/tutorials/
- Dive into Deep Learning - открытая книга с кодом, математикой и PyTorch/NumPy вариантами: https://d2l.ai/
- arXiv/IEEE Xplore - только для библиографии и research review по темам `GNN for circuit analysis`, `schematic DRC`, `graph embeddings`, `fault diagnosis`.

## Что это дает коду DOLG

1. `KnowledgeSource` roadmap: завести curated-список источников с полями `title`, `url`, `license_note`, `topics`, `usable_for_code`, `usable_for_ai_training`.
2. `LearningTask` seed: на основе открытых тем сделать задачи по закону Ома, делителю, RC, диодной ветви, транзисторному ключу, стабилизатору, фильтрам и диагностике.
3. `AITrainingExample` enrichment: добавлять не текст книг, а структурированные пары `scheme_data -> review finding -> expected action -> source topic`.
4. `Artifact ingestion` policy: внешние PDF/книги не скармливать нейронке целиком; извлекать только собственные конспекты, законные цитаты, формулы общего характера и созданные нами задания.
5. `Rule pack bibliography`: у каждого экспертного правила хранить ссылку на источник уровня "официальная документация/datasheet/open textbook", чтобы AI отвечал с evidence, а не "из воздуха".

## Ближайший план

1. Создать seed `knowledge_sources.json` с открытыми источниками выше.
2. Добавить management command `seed_knowledge_sources` или расширить существующий seed знаний.
3. Связать источники с learning tracks: "Основы цепей", "Диагностика", "SPICE/CAD import", "PyTorch deep hints".
4. Для нейронки собрать не тексты книг, а датасет из собственных схем, demo-проектов и легально созданных задач.
5. В диплом добавить подраздел "Источники инженерного корпуса данных и правовая политика обучения модели".

## Использованные открытые ориентиры

- Physics.Math.Code / Telegram mirror snippets: темы по схемотехнике, Python, PyTorch и подборкам ресурсов использованы только как указатель на направления.
- Официальные и открытые источники выше являются предпочтительными для диплома, документации, кода и AI-обучения.

---

## MODERATION ROLES

Источник: `MODERATION_ROLES.md`

# DOLG Moderation And Roles

Дата: 2026-05-26

## Что добавлено

- Новый app `moderation`: жалобы, moderation cases, действия модератора, ограничения пользователей и правила модерации.
- Глобальные группы Django:
  - `site_admin`
  - `site_moderator`
  - `catalog_editor`
  - `knowledge_editor`
  - `support_agent`
- Локальная роль команды: `moderator` с правом `org.moderation.manage`.
- Soft moderation для `Comment`, `ChatTopic`, `ChatReply`, `OrgConversationMessage`.
- API:
  - `POST /api/moderation/report/`
  - `GET /api/moderation/queue/`
  - `POST /api/moderation/cases/<id>/action/`
- Внутренняя очередь: `/moderation/`.

## Поведение V1

- Обычные пользователи видят только `moderation_status="visible"`.
- Staff, superuser и глобальные модераторы могут видеть очередь и выполнять действия.
- Org-модератор работает только с объектами своей команды.
- Удаление комментария теперь soft-delete: статус `removed`; физический purge доступен только superuser.
- `UserRestriction` с типом `mute`, `ban` или `read_only` блокирует создание Q&A-топиков, ответов и комментариев.

## Проверки

```bash
python manage.py check
python manage.py test moderation.tests --verbosity 2
python manage.py check_demo_ready --json
```

`check_demo_ready` содержит блок `moderation_stack`: роли, soft-fields, URL API и модели moderation core.

---

## NEURAL UPGRADE PLAN

Источник: `NEURAL_UPGRADE_PLAN.md`

# План усиления нейронки DOLG

Грунтовано на фактическом коде: `Dolg_APP/ml/neural.py` (TinyCircuitNet) и
`Dolg_APP/ml/gnn_simulator.py` (GNNCircuitNet). Цель — не «добавить слоёв», а снять реальные
потолки качества.

## Главный вывод: две нейросети, разный потолок

| | TinyCircuitNet (`neural.py`) | GNNCircuitNet (`gnn_simulator.py`) |
|---|---|---|
| Что предсказывает | topology(5) / risk(1) / next(7) | напряжения узлов (регрессия) |
| Вход | агрегаты-счётчики (30 фич), **не граф** | настоящий граф + message passing |
| **Метки (ground truth)** | **правила-учитель** (`_risk_teacher`, `_detect_teacher_topology`, `_next_component_teacher`) | **физика** (`solve_dc` MNA) |
| Потолок | **≤ учителя** — это дистилляция хардкод-правил | **физика**, потолок высокий |

**Следствие.** TinyCircuitNet учится воспроизводить рукописные правила. Подгрузка 6000 реальных
схем диверсифицирует только *распределение фич* — метки всё равно генерит тот же учитель, новых
знаний нет.

## Правка курса: не выбрасывать учителя, а сделать его сильнее (+ единая основа)

Учитель-ученик — правильная схема, выбрасывать не надо. Слабое место не в самом подходе, а в том,
что **учитель примитивный** (`_risk_teacher` и т.п. — игрушечные эвристики). Решение: **учитель =
ядро движков**, а не хардкод-правила.

- **Сильный учитель = движки.** Метки для нейронок берём из реальных движков: `solve_dc`/`solve_ac`
  (напряжения/токи), `analyze_pcb_drc` (нарушения), `expert_rules` (риски с rule_id). Тогда сеть
  дистиллирует *всё знание движкового ядра* и учится его **адаптировать** (обобщать на не виденные
  топологии, давать мягкие оценки, считать в 10×+ быстрее), а не зубрить срабатывание правил.
  GNN уже так делает (учитель = `solve_dc`); TinyCircuitNet надо перевести с игрушечного учителя на
  то же ядро.
- **Единая основа для нейронок — как «основной движок» у серверной части.** У движков есть ядро
  (MNA `monte_carlo`) + реестр `ai_algorithms`. У нейронок нужна симметричная основа:
  1. **`neural_teacher`** — один модуль, превращающий схему в богатые метки через движковое ядро
     (единый источник правды для всех нейромоделей). Физику берёт через движковую абстракцию с
     fallback-порядком серверной части (`server_engines`: **Xyce → PySpice → GnuCap → ngspice-wasm
     → NumPy MNA**). Сейчас живой движок один — NumPy MNA; **Xyce/PySpice** (индустриальный SPICE:
     нелинейщина/transient/AC/реальные device-модели) — золотой эталон-учитель: когда воркеры
     подключат, учитель усилится сам, без правок нейромоделей. Пока не установлены (PySpice/Xyce
     нет в окружении) — seam готов в `dc_labels`;
  2. **общий граф/фич-билдер** — `build_graph`/`scheme_to_features` свести в одну основу, которую
     используют ОБЕ модели;
  3. **реестр нейромоделей** (зеркало `ai_algorithms`): `NeuralModel{key,title,task,build,train,
     predict,benchmark}` — TinyCircuitNet, GNN и будущие головы регистрируются в одном месте;
  4. единый **train/predict/benchmark** + версионированный стор моделей (`.pt` + meta).

Так «намного мощнее» достигается не заменой подхода, а **усилением учителя до уровня движков** и
**единой основой**, на которой растут все нейромодели.

## Трек 1 — Снять потолок данных (самый сильный рычаг)

- **GNN: данные из 65k реального корпуса.** Сейчас обучается на 200 процедурных резисторных схемах
  (`generate_resistive_schemes`: divider/ladder/series). Прогнать реальные схемы через
  `scheme_to_circuit` → отфильтровать MNA-решаемые → метки из `solve_dc`. Реальная топологическая
  вариативность + точные физические метки = качественный скачок. (Нужен стрим-лоадер из Трека 5,
  иначе OOM — кап `--max-schemes` уже добавлен.)
- **GNN: богаче процедурный генератор.** Добавить несколько источников, источники тока, мосты,
  П/Т-образные цепи, рандомные планарные топологии, разброс номиналов по log-шкале. Чем шире
  распределение топологий — тем лучше обобщение.
- **TinyCircuitNet: метки-золото вместо/поверх учителя.** Подмешать human-validated
  `AITrainingExample (is_validated)` как gold-метки и взвесить их выше teacher-меток; risk учить
  не от эвристики, а от фактического DRC/ERC (`analyze_pcb_drc`) и сходимости MNA. Provenance-вес:
  gold > физика > учитель.

## Трек 2 — Архитектура и обучение

- **GNN: минибатчи.** Сейчас per-sample SGD (цикл по train_set) — медленно и шумно. Батчить графы
  блочно-диагональной склейкой (один большой разреженный граф на батч) → быстрее, стабильнее
  градиент, можно учить на десятках тысяч.
- **GNN: сильнее сообщение.** LayerNorm между GraphConv; edge-conditioned/attention-агрегация
  (взвешивать соседей, а не суммировать); 4–6 слоёв с residual (уже есть anti-over-smoothing skip).
  Больше node-фич: R-до-земли, расстояние до источника (hops), log-degree, Лапласиан-PE.
- **TinyCircuitNet → общий графовый энкодер.** Заменить bag-of-features MLP на тот же GraphConv-
  backbone, что у GNN (shared encoder), а topology/risk/next — лёгкие головы поверх. Тогда даже
  эти задачи видят структуру, а не только счётчики.
- **Оба: честный сплит train/val/test** (сейчас только train/val), метрики сверх loss — accuracy/F1
  для классов, MAE/rel-err для напряжений; multitask-веса loss-ов настроить (сейчас простая сумма).

## Трек 3 — Расширить, ЧТО предсказывает GNN (новая ценность)

- **Переходный анализ:** предсказывать V(t)-кривые (суррогат `solve_transient`). Здесь нейро-суррогат
  даёт 10×+ ускорение, которого MNA не даст на масштабе.
- **AC:** предсказывать |H(f)|/фазу по частоте (суррогат `solve_ac`) — мгновенные Боде-диаграммы.
- **Ток и мощность по рёбрам** (доп. головы), не только напряжения узлов → сразу derating/нагрев.
- **Нелинейщина:** диод/LED (Шокли), транзистор — режим, где Newton-итерации MNA медленные и
  суррогат окупается максимально. Это и оживляет «реалистичные» модели из библиотеки idea-листа.
- **Monte-Carlo на суррогате:** 10k итераций разброса номиналов через GNN вместо MNA → секунды
  вместо минут (бьётся с `monte_carlo`).

## Трек 4 — Калибровка, доверие, оценка (под защиту)

- **Бенч-отчёт.** `benchmark_against_mna` уже считает mean_abs_err/rel_err/speedup — собрать в
  команду/страницу: «GNN vs MNA на held-out test: rel-err X%, ускорение Y×». Это цифры для защиты.
- **Неопределённость.** MC-dropout или мини-ансамбль → доверительные интервалы; «использовать
  нейро в одиночку» гейтить по калиброванной уверенности (`compare_prediction_to_teacher` уже даёт
  agreement-policy — расширить реальной test-калибровкой).
- **Regression-guard в CI:** новая модель не хуже старой на фиксированном test-наборе, иначе не
  публикуем. Сохранять manifest датасета + метрики рядом с `.pt` (meta уже частично пишется).

## Трек 5 — Масштаб и инфраструктура

- **Стрим-лоадер датасетов** вместо «весь список в память» (причина OOM, кап уже стоит): итерировать
  файлы, строить графы порциями, кэшировать тензоры на диск. Тогда доступны все 65k для GNN.
- **Device-aware** (`cpu`/`cuda`) — сейчас всё на CPU; на GPU обучение в разы быстрее.
- **ONNX-экспорт** обученной GNN → быстрый инференс и возможность вынести на клиент (бьётся с
  Transformers.js-направлением: предсказание прямо в браузере, без сервера).

## Baseline (первый замер на реальном корпусе)

Трек 1+5 запущен: `train_gnn_simulator` обучил GNN на 2000 сэмплах (500 процедурных + 1500
MNA-решаемых из корпуса; просмотрено 1743 схемы → **86% решаемы MNA**). Held-out test (200):

- **abs-err ≈ 0.125 В** (мало в абсолюте), **best_val_loss ≈ 0.0004**;
- **rel-err ≈ 114%** — далеко от цели <5%: ошибку в относительных раздувают низковольтные узлы
  (0.12 В на узле 0.1 В = >100%);
- **speedup ≈ 0.04** (×25 *медленнее* MNA на мелких DC-схемах) — суррогат окупается на крупных/
  нелинейных/Monte-Carlo, не на делителях в микросекунды.

Вывод: пайплайн работает end-to-end, но точность/ценность — впереди (треки 2-3). Метрику rel-err
стоит дополнить порогом по |V| (не считать узлы ~0 В) и per-node MAE — abs-err честнее на смеси
больших/малых потенциалов.

## Порядок действий (ближайшее)

1. Стрим-лоадер + сбор MNA-решаемых схем из 65k → датасет с физ-метками (Трек 5+1).
2. Минибатчинг GNN + held-out test + бенч-отчёт rel-err/speedup (Трек 2+4) — получить базовую цифру.
3. Расширить генератор и node/edge-фичи, дотюнить до целевого <5% rel-err на DC (Трек 1+2).
4. Доп. головы: ток/мощность; затем переходный режим (Трек 3) — главный прирост ценности.
5. Калибровка + CI-guard + ONNX (Трек 4+5).

## Чего НЕ делать

- TinyCircuitNet остаётся быстрым дистиллятором — но **учителя ему сменить на движковое ядро**
  (не игрушечные эвристики); «умнеть сверх учителя» не нужно, нужен сильный учитель.
- Без новых библиотек: GraphConv from-scratch уже есть и сам по себе — аргумент на защите
  (понимаем математику message passing, а не зовём `torch_geometric`).
- Не менять слой движков (MNA/MC/RF) — он эталон-учитель для меток, его трогать незачем.

---

## OPENSOURCE GEMS BACKLOG

Источник: `OPENSOURCE_GEMS_BACKLOG.md`

# Open-source «жемчужины» — анализ на будущее (2026-06-22)

Список от юзера (андеграунд open-source для диплома) + честный анализ: релевантность нашему стеку
(Django + аналоговый SPICE-симулятор + PCB + локальный AI), реализуемость (Windows/py3.14!),
приоритет. ⚠️ Часть пунктов — из «другого домена» (цифровой RTL/ASIC) или требует проверки
существования; формулировки юзера местами шуточно-гиперболичны — отделяю реальное от позиционного.

## ТОП-фит для НАШЕГО проекта (аналог/SPICE/PCB/AI)

| # | Гем | Почему фит | Реализуемость | Приоритет |
|---|---|---|---|---|
| 6 | **KAN SPICE-нейросеть** (Kolmogorov-Arnold Networks, 2024) | Прямо в наш AI-трек: уже есть GNN-предсказатель напряжений. KAN — свежая (2024) архитектура, точнее MLP. Сильная новизна для защиты | pykan/efficient-kan (torch) — но **Windows+py3.14 torch-wheel боль** (см. semantic_search memory). Возможно CPU-only/малые сети | **HIGH** (модуль AI) |
| 4 | **OpenVAF** (Verilog-A → быстрые SPICE-модели, OSDI) | Прямо в наш engines-трек (MNA/ngspice/Xyce). Свои модели транзисторов → компилируемые быстрые модели | Нужен бинарь OpenVAF + ngspice с OSDI. Средне | MEDIUM |
| 3 | **SNAPPY** (ADC→стрим в реальном времени) | Фит к live-симуляции + приборам: спектроанализатор (FFT уже есть в scheme-netlist), «графики как в кино» | Средне (стрим + FFT-вью) | MEDIUM |
| 9 | **Sigil** (форк KiCad с AI-трассировщиком) | Фит к нашему A*-автороутеру + PCB. AI-разводка = шаг вперёд | ⚠️ **Проверить существование** (возможно аспирационно). Если есть — изучить подход | MEDIUM (verify) |
| 8 | **OSHW / OSHWA** (open-source hardware + значок) | Не код — позиционирование: опубликовать проект (лицензия) + заявка OSHWA. Нарратив «член int. open-source сообщества» | Легко (лицензия + публикация) | EASY WIN |

## Другой домен (цифровой RTL/ASIC) — отдельный трек, большой объём

| # | Гем | Замечание |
|---|---|---|
| 1 | **OpenLane** (RTL→GDSII ASIC, sky130) | «Спроектировал чип дома» — мощный нарратив, НО: цифровой RTL→кремний, Linux/Docker, у нас нет RTL. Можно лишь ПРОДЕМОНСТРировать готовый sky130-пример. Огромный scope-creep |
| 2 | **Migen + LiteX** (Python→Verilog) | Цифровой FPGA/SoC. «Плата самособирается по коду» — круто, но тангенциально аналоговому фокусу. Отдельный digital-трек |
| 7 | **NMigen / Amaranth** (Migen + формальная верификация) | «Математически доказал корректность» — для ЦИФРОВЫХ схем (не аналог). Отдельный трек |

## Новизна/тангенциальное

| # | Гем | Замечание |
|---|---|---|
| 5 | **MODBUS-over-SSH** | Туннель промышленного протокола. К EDA тангенциально; мелкое демо (pymodbus+paramiko «читаем симулированный датчик») как novelty |
| 10 | **EDP** (Emacs-режимы для схем в тексте) | У нас веб-редактор; ценность низкая, чисто «хакерский» антураж |

## Вывод / рекомендация

- **До защиты** (если время): #8 OSHW (легко, нарратив) + изучить #6 KAN как улучшение AI-предсказателя (если torch заведётся).
- **Engines-трек:** #4 OpenVAF — естественное продолжение мульти-движкового SPICE.
- **PCB-трек:** проверить #9 Sigil; идеи AI-разводки поверх нашего A*.
- **Real-time/приборы:** #3 SNAPPY-подход для спектроанализатора (FFT уже есть).
- **Отложить/отдельный трек:** #1/#2/#7 (цифровой RTL/ASIC — другой домен, большой объём), #5/#10 (novelty).
- ⚠️ Перед интеграцией любого — **проверить существование/лицензию/Windows-совместимость** (часть может быть аспирационной).

Связано: [[project_post_defense_ai_roadmap]], [[project_sim_engines_backlog]], [[project_astar_block_c1]].

---

## OPS ALERTING

Источник: `OPS_ALERTING.md`

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

---

## PRODUCT DATA 3D SOURCES

Источник: `PRODUCT_DATA_3D_SOURCES.md`

# Источники данных/фото/3D компонентов + CV/3D-тулчейн (анализ, 2026-06-22)

Два списка от юзера: (A) ресурсы компонентных данных/фото/3D-моделей, (B) CV/3D-библиотеки для их
обработки. Привязка к текущему фото-пайплайну (commit b78f1ac: official-CDN/Nexar/LCSC + гейт
качества) и к вектору «design + 3D». Caveat: Windows/py3.14 (torch-wheel боль), лицензии, API-ключи.

## A. Источники данных компонентов (фото / datasheet / 3D)

| Ресурс | Что даёт | Фит | Замечание |
|---|---|---|---|
| **Octopart** (octopart.com) | фото, datasheet, параметры, аналоги; JSON-API (Nexar) | ✅ **уже подключён** в photo_sources (nexar) | нужен бесплатный Nexar-ключ |
| **DigiKey API** | фото, datasheet, 3D-модели большинства позиций | ⭐ добавить как источник в photo_sources | нужен API-ключ (бесплатный dev) |
| **SnapEDA** (snapeda.com) | символы, посадочные места, **3D-модели** (KiCad/Altium/Eagle), API | ⭐ для **3D-вектора** (модели корпусов) + footprint | регистрация/API |
| **Alldatasheet** | архив datasheet → парсить фото корпусов + габаритные чертежи | medium (для фото корпусов как доп.источник) | парсинг, ToS |
| **SamacSys** (Component Search Engine) | бесплатные EDA-библиотеки + 3D, плагины | ⭐ 3D-модели + footprint | прямые ссылки/плагин |
| **3D ContentCentral** | крупнейшая база 3D (разъёмы/корпуса/вентиляторы), STEP/IGES/SAT | ⭐ 3D-вектор (механика/корпуса) | от производителей |
| **GrabCAD** | инженерные 3D-модели (теги PCB/connector/sensor) | medium 3D | лицензии разные |
| **Element14 Community** | CAD-модели, привязка к каталогу | medium | |
| **Library.io** | посадочные места/символы, пакетный экспорт | medium (footprint) | |
| **Open CASCADE** (OCCT) | **генерация** параметрических 3D-моделей по характеристикам | ⭐⭐ для «модель из параметров» (а не скачать) — фит к нашему generate-fallback, но в 3D | C++/pythonocc, Docker; см. [[project_next_vector_design_3d]] |

## B. CV / 3D-тулчейн для обработки

| Либа | Что | Фит |
|---|---|---|
| **RemBG** (rembg) | нейро-удаление фона за секунды | ⭐⭐ **прямо в фото-пайплайн**: нормализовать фон скачанных фото → единый белый фон каталога |
| **ImageMagick + Wand** | пакетная обрезка/нормализация освещения/маски | ⭐⭐ пост-обработка датасета фото (однородность) — маст-хэв для каталога |
| **SAM (Segment Anything)** | сегментация деталей из фото | ⭐ вырезать компонент из «фото на столе»; + гибридный датасет (текстура→примитив) |
| **PyTorch3D** | рендер/трансформации мешей, сравнение 3D↔фото | 3D-вектор: сопоставлять фото с 3D-моделью корпуса (torch — Windows-риск) |
| **Open3D** | ICP-регистрация, вокселизация, поза 3D↔фото | 3D-вектор (совмещение модели с фото платы) |
| **COLMAP** | 3D-реконструкция по серии фото (10 ракурсов → меш+текстура) | 3D-вектор (фото→меш), тяжёлый |
| **Trimesh** | загрузка/конвертация/анализ STL/OBJ/PLY | ⭐ лёгкий — конвертация скачанных STEP/3D в наш web-3D (pipeline схема→PCB→3D) |
| **MeshLab** (CLI) | чистка/упрощение/выравнивание мешей, автоматизация | medium (батч-обработка 3D перед web-показом) |

## Привязка к проекту + рекомендации

- **Фото-пайплайн (сейчас, b78f1ac):** добавить **DigiKey** как источник (рядом с Nexar); прикрутить
  **RemBG + ImageMagick/Wand** как пост-обработку (единый белый фон + нормализация) — прямо бьёт в
  «фото были некачественными». SAM — опционально для «фото на столе».
- **3D-вектор (design+3D, [[project_next_vector_design_3d]]):** SnapEDA / 3D ContentCentral / SamacSys /
  GrabCAD — скачивать STEP-модели корпусов; **Trimesh** — конвертация в web-3D; **Open CASCADE** —
  параметрическая генерация (3D-аналог нашего UGO-fallback). Связано с pipeline схема→PCB→3D.
- **Caveat:** torch-зависимые (PyTorch3D, RemBG-нейро, SAM) — проверить Windows/py3.14 wheel; COLMAP/
  PyTorch3D тяжёлые (отдельный трек/Docker). Лицензии скачанных моделей/фото — проверять перед показом.

Связано: [[project_opensource_gems]], [[project_next_vector_design_3d]], [[project_sim_engines_backlog]].

---

## SCHEMATIC EDITOR FIXES

Источник: `SCHEMATIC_EDITOR_FIXES.md`

# План фиксов схематического редактора

## 0. Wire interaction баги (2026-05-30 от юзера)

### 0.1. Hit-detection: «не все участки провода можно выбрать»

**Симптом:** клик по сегменту провода → выделяется не он, а соседний компонент/провод/ничего.

**Гипотезы:**
- `getConnectionAtPosition` (или аналог) — пороговое расстояние слишком маленькое (tolerance ~2-3px), мизерное на zoom < 1.0.
- Hit-priority: компоненты тестируются ДО проводов, и bbox компонента «съедает» близкий wire-сегмент.
- Сегменты построенные через `buildOrthogonalPath` хранятся как edge-list, а hit-test делается по серединам — крайние пиксели сегмента невыделяемы.

**Фикс (когда возьмёмся за router):**
- Расширить tolerance до `max(4, 6 / zoom)` — на мелком zoom больше padding.
- Делать hit-test проводов **раньше** компонентов, если клик НЕ внутри bbox компонента.
- Логировать выбранный сегмент в `console.debug` при `window._dolgDebugSelect = true`.

### 0.2. Wire не двигается drag'ом

**Симптом:** провод можно только редактировать через waypoints (Ctrl+Drag), а перетягивать целиком — нельзя. Юзер: «перемещение проводов осуществляется только через элементы».

**Фикс:**
- В onCanvasMouseDown — если попали в wire-сегмент и нет Ctrl: начать `draggedConnection = conn`, запомнить offset.
- В onMouseMove с draggedConnection — сдвигать **все waypoints + endpoints** (если они не привязаны к pad'у). Endpoints на pad'ах должны быть **resnap'нуты** к ближайшему porty компонента в drop-зоне.
- В onMouseUp — pre-snap к grid, snapshot для undo.

**Acceptance:** клик на середину провода → drag → весь провод перемещается; endpoints резинятся к pad'ам ближайших компонентов.

---



**Создано:** 2026-05-30 (до защиты ~3 недели).
**Цель:** убрать визуальные баги и шум в консоли, расширить набор правил рисования схем без новой ambition.
**Скоуп:** только `simulation.html` редактор. PCB-view, 3D, CAD — не трогаем.

---

## 1. Router проводов (`buildOrthogonalPath`)

### 1.1. Симптом

На скриншоте 2026-05-30: путь C6 → R9 получает 3-4 поворота вместо одного-двух. Лишний «step» — линия идёт вниз, потом вправо, потом коротко вверх, потом снова вправо.

### 1.2. Гипотезы причин

| # | Гипотеза | Файл / функция | Как проверить |
|---|---|---|---|
| 1 | `pickFreeAxisY` обходит препятствие слишком близко, создавая S-петлю | `simulation.html:5478` | Логировать `(initialY, midY)` для конкретного wire'а |
| 2 | `getPortExitDirection` для C6 возвращает «вниз» вместо «вверх» (порт у конденсатора рисуется снизу, а exit — направление от тела к pad) | `simulation.html:5385` | Проверить port-meta для capacitor.SVG |
| 3 | Один из portов уже имеет `waypoints` от перетаскивания — но waypoints не пересчитываются после move компонента | `simulation.html:~4772` | Логировать `conn.waypoints.length` |
| 4 | STUB (20px) слишком большой относительно расстояния до угла, создаёт «вторую полку» | `simulation.html:5501` | Уменьшить до 12 или сделать адаптивным |

### 1.3. Фиксы

- **A.** Логирование (включить через `window._dolgDebugRoute = true`) — добавить `console.debug` в `buildOrthogonalPath` с дампом `pts` массива. Без юзерского репро невозможно угадать конкретную ветку.
- **B.** ✅ Симплификация пост-фактум сделана: collinear-HV + micro-segments < 8px (см. `buildOrthogonalPath` финальный блок 2026-05-30). **НО ЮЗЕР ЗАМЕТИЛ:** правило может быть слишком жёстким — оно «съедает» wp(1470,420) при R9.y=430 и тем самым меняет геометрию проводов так, что они выглядят неестественно. **Решение:** при следующей итерации router'а понизить агрессивность — `MICRO_EPS` сделать настраиваемой (8 → 4 или 0 по флагу), или симплифицировать только если все waypoints внутри тонкого коридора. Заодно: показывать кастомные waypoints как dots на канвасе, чтобы юзер понимал что он «съел» grid-snap'ом.
- **C.** Уменьшить STUB до **12px** для коротких сегментов (если `|fromPos - toPos| < 60px`).
- **D.** Если waypoints пустой И сегмент имеет ровно один поворот — никогда не вставлять промежуточные точки (это L-роут, не Z).

### 1.4. Acceptance

- Сценарий из скриншота: C6 (тело сверху-слева) → R9 (тело снизу-справа) должен дать **2 поворота, 3 сегмента**, а не 4.
- Не сломать существующие положительные кейсы (curated demo-схемы из `collect_ai_training_examples --source curated`).

---

## 2. Правила рисования схем (DRC расширение)

Сейчас в `Dolg_APP/expert_rules/default_rules.json` ~8 правил. Добавить минимум 5 «школьных» правил которые должен ловить любой schematic editor.

### 2.1. Список

| # | Правило | Severity | Detector |
|---|---|---|---|
| 1 | Wire не должен пересекать тело компонента (overlap) | error | Geometry: для каждого wire-сегмента проверить пересечение с bbox каждого компонента (кроме endpoints) |
| 2 | T-junction (3+ проводов в точке) должен иметь видимый dot | warning | `_renderRouteJoints` уже строит joints — проверить что их 100% покрытие |
| 3 | Два провода не должны пересекаться без junction-dot (crossing != connection) | warning | Сегменты которые пересекаются под 90° без зарегистрированного net-merge |
| 4 | Wire-сегмент длиной < 5px — лишний (микро-стаб от плохого роутинга) | warning | Простая проверка длины |
| 5 | Параллельные провода с расстоянием < 4px (визуально сливаются) | warning | Проход по парам wire'ов с одинаковой ориентацией |
| 6 | Open-end wire (один конец не подключён к компоненту/junction) | error | Уже частично ловится netlist'ом, но не визуализируется на канвасе |
| 7 | Порт компонента используется в 0 wire'ов (висячий пин) | warning | Каждый port должен иметь хотя бы один wire (кроме no-connect маркера) |

### 2.2. Где живёт

- Backend detector: `Dolg_APP/services/expert_detectors.py` (если файл существует, иначе создать).
- Каждое правило — функция `detect_<name>(scheme_data, graph)` возвращает `list[finding]`.
- Frontend визуализация: красные кружки на `_renderRouteJoints` для error, жёлтые для warning.

### 2.3. Acceptance

- Каждое правило срабатывает на минимальной test-схеме (1 баг → 1 finding).
- Чистая демо-схема делителя напряжения — 0 findings.
- В `default_rules.json` все 5 новых правил с russian title/recommendation.

---

## 3. ngspice WASM — `incomplete result` warning

### 3.1. Симптом

В консоли при каждой симуляции схемы с транзистором Q1/Q2 (BJT):
```
[ngspice.wasm returned incomplete result, falling back to JS MNA]
Error: DC-анализ не вернул напряжения узлов: stdout ngspice
не содержит таблицу Node/Voltage.
```

### 3.2. Корень

Наш ngspice.wasm build (см. `shop/static/simulation/ngspice.wasm`) **не содержит BJT-модели** (Q1/Q2 транзисторы из скриншота). Когда netlist имеет `.MODEL QNPN NPN`, WASM пишет ошибку парсинга в stdout, **не печатает таблицу `.op`** — наш `parseDcOutput` (`ngspice-worker.js:173`) возвращает пустой `nodeVoltages`. Дальше `getSimulationResultProblem` ловит `nonGroundNodes.length === 0` и формирует warning. JS-MNA подхватывает.

### 3.3. Фиксы (по приоритету)

| # | Фикс | Трудозатраты |
|---|---|---|
| **A** ✅ Сделано | Снизить severity `console.warn` → `console.info`, убрать `showNotification('⚠')` | 5 мин |
| B | Перед вызовом `runOnNgspice` проверить, есть ли в netlist BJT/MOSFET/JFET — если да, **сразу идти JS-MNA** минуя WASM | 20 мин |
| C | Перекомпилировать ngspice.wasm с включёнными BJT-моделями (требует ngspice 38 + Emscripten setup) | 1-2 дня, риск |
| D | В `parseDcOutput` принимать **именованные узлы** (`out`, `vcc`) — не только цифровые | 30 мин |

### 3.4. Acceptance

После фикса B: схема с Q1/Q2 — **0 warnings в консоли**, симуляция идёт через JS-MNA, результат отображается.

---

## 4. Прочие визуальные фиксы редактора

### 4.1. Engineering Review кнопка

✅ Уже сделано 2026-05-30: «🔍 Анализ» из top-toolbar убрана, теперь «🔍 Review» в analysis-bottom-header рядом с Monte Carlo.

### 4.2. Border-рамки 2-3px

✅ Уже сделано 2026-05-30 (v4 layout): 4 неоновые рамки → одна общая на outer wrapper. Inner-секции разделяются gap'ом и subtle 1px-divider'ами.

### 4.3. Analysis-bottom panel высота по умолчанию

✅ Уже сделано 2026-05-30: дефолт `36px` (только title) → `clamp(180px, 22vh, 260px)`.

### 4.4. Open: «hover-glow» компонентов

Сейчас при hover компонент получает яркую cyan-подсветку через filter. Это контрастирует с новым lightweight стилем. Рассмотреть: subtle outline + scale 1.02 вместо glow.

### 4.5. Open: курсор в режиме «Провод»

Сейчас стандартный crosshair. Хорошо бы — кастомный SVG с иконкой провода (как в KiCad/Eagle).

---

## 5. Порядок работ (предложение)

| Этап | Что | Размер | Acceptance |
|---|---|---|---|
| ✅ Done | Убрать «🔍 Анализ» из top-toolbar, перенести вниз | S | Кнопка ниже |
| ✅ Done | Понизить severity ngspice warning'а до info | S | Консоль чистая на типовых сценариях |
| 1 | Router debug-логирование + сценарий C6→R9 → найти ветку | S | Воспроизведение в коде |
| 2 | Router фикс по выявленной ветке (probably STUB или pickFreeAxisY) | M | Acceptance §1.4 |
| 3 | Detector skip для BJT в netlist → JS-MNA сразу (фикс 3.3.B) | S | Acceptance §3.4 |
| 4 | 5 новых DRC-правил (§2.1 №1, 4, 6, 7 — простые; №2, 3, 5 — посложнее) | M | Acceptance §2.3 |
| 5 | hover-glow refactor (§4.4) — если есть время после остального | S | Subjective |

---

## 6. Что НЕ делаем

- ❌ Не перекомпилируем ngspice.wasm с BJT (риск 1-2 дня, мало profit'а).
- ❌ Не вводим новые компоненты (op-amp, multiplexer и т.д.) — фокус на router/DRC.
- ❌ Не меняем общую тему/цвета — только проблемные места.
- ❌ Не делаем undo/redo переработку — это уже Phase 2.

---

## 7. Связано

- `Dolg_APP/templates/tools/simulation.html` — основной файл редактора (~14000 строк)
- `shop/static/simulation/ngspice-worker.js` — парсер ngspice stdout
- `Dolg_APP/services/expert_rules.py` — runtime для DRC правил
- `Dolg_APP/expert_rules/default_rules.json` — конфиг 8 базовых правил
- `Dolg_APP/services/schematic_graph.py` — graph-validation, T-junction поиск

---

## SCREENSHOT GUIDE

Источник: `SCREENSHOT_GUIDE.md`

# Гайд по скриншотам для защиты диплома

Список страниц и состояний, которые желательно зафиксировать перед защитой
для слайдов и приложений к диплому. Положите файлы в `docs/screenshots/<group>/`.

## Подготовка

```bash
# 1. Очистить и заполнить демо-данными
python manage.py migrate
python manage.py populate_reb_products
python manage.py populate_demo_projects
python manage.py seed_announcements
python manage.py apply_curated_product_photos

# 2. Создать админа
python manage.py createsuperuser   # admin / любой надёжный пароль

# 3. Создать demo-org для Enterprise-скриншотов
python manage.py shell -c "
from Dolg_APP.models import Organization, OrganizationMember, Subscription
from django.contrib.auth import get_user_model
from datetime import timedelta
from django.utils import timezone

U = get_user_model()
admin = U.objects.get(username='admin')
org, _ = Organization.objects.get_or_create(
    slug='dolg-demo',
    defaults={'name':'DOLG Demo Inc.', 'owner':admin, 'billing_email':'demo@dolg.local', 'plan':'business', 'seats_max':25}
)
OrganizationMember.objects.get_or_create(organization=org, user=admin, defaults={'role':'owner'})
Subscription.objects.update_or_create(
    organization=org,
    defaults={'tier':'pro','status':'active','provider':'manual','period_end':timezone.now()+timedelta(days=365)},
)
print('Demo org готова:', org.slug)
"

# 4. Запустить сервер
python manage.py runserver 0.0.0.0:8000
```

## 1. Каталог и shop

| Файл | Что захватить |
|---|---|
| `01-index-main.png` | Главная `/` без фильтров — категорий и полки товаров |
| `02-index-filtered.png` | Главная с активным фильтром (например, `?manufacturer=vishay`) |
| `03-category.png` | Страница категории (резисторы) с боковыми фильтрами |
| `04-product-detail.png` | Карточка товара с параметрами + datasheet |
| `05-compare.png` | `/compare/` с 3 товарами и автоанализом «лучше/хуже» |
| `06-cart.png` | Корзина с парой товаров |
| `07-checkout.png` | Оформление заказа |

## 2. Редактор схем и симулятор

| Файл | Что захватить |
|---|---|
| `10-simulator-blank.png` | Симулятор без схемы — toolbar и сетка |
| `11-simulator-rc-filter.png` | Загружен RC-фильтр (демо), показаны компоненты с подписями |
| `12-simulator-tran.png` | Запущен TRAN — графики напряжений и токов |
| `13-simulator-ac.png` | AC-анализ — Bode plot (мага + фаза) |
| `14-fft.png` | Pro-аналитика: FFT spectrum через SciPy |
| `15-thermal.png` | Тепловой анализ с цветовой аурой компонентов |
| `16-what-if-slider.png` | What-if слайдер на номинале R/C |
| `17-bom.png` | Модалка BOM с матчингом каталога |
| `18-3d-pcb.png` | 3D PCB viewer (Three.js) |
| `19-virtual-lab.png` | Виртуальная лаборатория (осциллограф/мультиметр/генератор) |
| `20-ai-fab.png` | AI-ассистент: чат с Claude (одна из вкладок) |
| `21-ai-pipeline.png` | AI-ассистент: pipeline strip с DRC++/След.компонент/Объясни |

## 3. CAD и проекты

| Файл | Что захватить |
|---|---|
| `30-cad-blank.png` | CAD с ГОСТ-рамкой А4 |
| `31-cad-with-blocks.png` | CAD с компонентами (DIP-8, делитель) и штриховкой |
| `32-projects-list.png` | `/projects/` со списком пользовательских проектов |
| `33-project-versions.png` | Боковая панель версий проекта |

## 4. Энциклопедия и обучение

| Файл | Что захватить |
|---|---|
| `40-knowledge-index.png` | `/knowledge/` — 6 категорий |
| `41-article.png` | Открытая статья с фото/datasheet/материалами |
| `42-engineering-lab.png` | `/knowledge/lab/` — калькулятор узла (например, NE555) |
| `43-learning-task.png` | Учебная задача с автопроверкой |

## 5. Чат и Enterprise (новое в 2026-05-19)

| Файл | Что захватить |
|---|---|
| `50-chat-list.png` | `/chat/` — список топиков + сайдбар «📢 Информационный канал» |
| `51-chat-topic-detail.png` | Открытый топик с ответами + реакции |
| `52-chat-new-topic.png` | Форма создания топика (для авторизованного) |
| `53-org-dashboard.png` | `/orgs/<slug>/` — карточки members/projects |
| `54-org-members.png` | `/orgs/<slug>/members/` — таблица с ролями |
| `55-org-audit.png` | `/orgs/<slug>/audit/` — лог действий |
| `56-org-conversation-list.png` | `/orgs/<slug>/conversations/` |
| `57-org-conversation-chat.png` | Открытый канал команды с парой сообщений |
| `58-org-approval.png` | `/orgs/<slug>/approval/` — очередь approval |
| `59-org-settings-branding.png` | Org-настройки: логотип, цвет, SSO toggle |
| `60-org-api-tokens.png` | API tokens management |

## 6. Биллинг и подписки

| Файл | Что захватить |
|---|---|
| `70-billing-plans.png` | `/billing/` — таблица tier'ов с ценами |
| `71-pro-trial-active.png` | Профиль с активной Pro-подпиской |
| `72-quota-banner.png` | Баннер «лимит исчерпан» в симуляторе для Free |

## 7. Админ-панель

| Файл | Что захватить |
|---|---|
| `80-admin-index.png` | `/admin/` — все зарегистрированные модели |
| `81-admin-organization.png` | Список Organization с фильтрами |
| `82-admin-announcement.png` | Форма редактирования Announcement |
| `83-admin-auditlog.png` | AuditLog с примером записей |

## 8. Тесты и метрики (для слайда «качество»)

| Файл | Что захватить |
|---|---|
| `90-pytest-passed.png` | Терминал с `pytest --cov` финальным выводом (263 passed, 71%) |
| `91-ruff-clean.png` | Терминал с `ruff check . — All checks passed!` |
| `92-coverage-html.png` | `htmlcov/index.html` — HTML отчёт по покрытию |

## Технические советы по съёмке

1. **Браузер**: Chrome / Firefox с DevTools закрытым.
2. **Разрешение**: минимум 1920×1080 (для печатных версий желательно 2560×1440).
3. **Тёмная тема DOLG** — на скриншотах смотрится профессиональнее печатной чёрно-белой.
4. **Чтобы не было блика на курсоре** — `Ctrl+Shift+P → "Capture full size screenshot"` в DevTools (для длинных страниц).
5. **Для PDF-приложений к диплому** — экспортируйте в PNG, не JPEG (текст резче).
6. **Расширение названий файлов** — придерживайтесь предложенной схемы `<NN>-<group>-<state>.png`, потом проще ссылаться из текста ВКР.

## Где использовать

- Глава 2 (Архитектура и компоненты) — 01-09, 30-31
- Глава 3 (Симулятор и аналитика) — 10-21
- Глава 4 (Энциклопедия) — 40-43
- Глава 5 (Enterprise и коллаборация) — 50-60
- Приложение А (Скриншоты) — все
- Презентация / речь — 4-5 самых эффектных (например, 13 + 18 + 21 + 51 + 57)

---

## SECURITY BACKLOG

Источник: `SECURITY_BACKLOG.md`

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

---

## SERVER ENGINES INSTALL

Источник: `SERVER_ENGINES_INSTALL.md`

# Установка серверных SPICE-движков

Цель: поднять внешние движки из fallback-цепи `server_engines.py`
(`xyce → pyspice → gnucap → ngspice-wasm → numpy-mna`), чтобы учитель нейронок и тяжёлые
симуляции могли опираться на индустриальный SPICE, а не только на NumPy MNA.

Окружение: Windows 10, Python **3.14.3**, `.venv`, pip 26. Доступны пакет-менеджеры **winget**,
**choco**.

## ⚠️ Ещё НЕ установлено — нужно поставить

Готов только PySpice+ngspice (DLL). Остальные движки fallback-цепи **ещё предстоит установить**:

- [ ] **ngspice (standalone CLI)** — `choco install ngspice` упал на занятом lock-файле; повторить в
  **elevated** shell (при необходимости удалить stale-lock `C:\ProgramData\chocolatey\lib\*`).
- [ ] **Xyce** — primary external engine по конфигу. Нет в пакет-менеджерах → скачать Windows-
  инсталлятор с <https://xyce.sandia.gov/downloads/> (бесплатная регистрация), поставить, добавить в PATH.
- [ ] **GnuCap** — нет в пакет-менеджерах → бинарь/сборка с <http://www.gnucap.org/>, добавить в PATH.

Без них fallback-цепь опирается на PySpice→NumPy MNA; Xyce/GnuCap нужны для tier-0 SPICE-нагрузок
и как золотой эталон-учитель нейронок.

## Статус

| Движок | Способ | Статус |
|---|---|---|
| **PySpice** 1.5 | `pip install PySpice` | ✅ установлен (py3.14 ОК), импортируется |
| **ngspice** (DLL для PySpice) | `pyspice-post-installation --install-ngspice-dll` | ✅ DLL + codemodels в `.venv/.../PySpice/Spice/NgSpice/Spice64_dll/` |
| **ngspice** (standalone CLI) | `choco install ngspice` (46.0.0, нужен admin) | ⏳ опционально — PySpice уже несёт DLL |
| **Xyce** | нет в choco/winget → ручная загрузка | 📥 manual: https://xyce.sandia.gov/ (Windows installer) |
| **GnuCap** | нет в choco/winget → ручная загрузка | 📥 manual: http://www.gnucap.org/ |

## Команды (воспроизведение)

```bash
# 1) PySpice (pip) — сделано
.venv/Scripts/python.exe -m pip install PySpice

# 2) ngspice DLL для PySpice — сделано
.venv/Scripts/pyspice-post-installation.exe --install-ngspice-dll

# 3) (опц.) standalone ngspice CLI — нужен elevated shell
choco install ngspice -y
```

## Xyce / GnuCap — ручная установка (разбираться отдельно)
- **Xyce**: скачать Windows-инсталлятор с https://xyce.sandia.gov/downloads/ (требует
  бесплатной регистрации), поставить, добавить `Xyce.exe` в PATH. Это primary external engine
  по конфигу `server_engines.py`.
- **GnuCap**: бинарь/сборка с http://www.gnucap.org/ ; добавить в PATH.

## Интеграция (следующий шаг, не сделано)
- `engine_jobs.py` сейчас делегирует в NumPy MNA. Подключить **PySpice-воркер**: scheme → SPICE-
  netlist (`ai_tools.py` уже умеет экспорт `.cir`) → PySpice DC/tran/AC → нормализовать вывод под
  `engine_jobs` adapter-формат (там уже есть заглушка «for future Xyce/PySpice/GnuCap workers»).
- `neural_teacher.dc_labels` seam: когда PySpice-воркер готов — переключить физ-метки учителя на
  него (золотой SPICE-эталон вместо NumPy MNA), без правок нейромоделей.

---

## STARTUP RELIABILITY AUDIT

Источник: `STARTUP_RELIABILITY_AUDIT.md`

# Startup reliability audit

Дата: 2026-06-09

Цель: вернуть локальный запуск DOLG к предсказуемому сценарию "нажал `start_local.bat`, получил `http://127.0.0.1:8000/`", без зависания на hot-reload, пустых логов и ложных OK-статусов.

## Симптом

Текущий сбой:

- `manage.py migrate --check` иногда не успевает за 30 секунд.
- Launcher продолжает старт, но печатает ложное `[OK] Миграции применены`.
- `start_local.bat` запускает `start_server.py --local --hot`.
- Hot-mode через `jurigged` на Windows выводит терминальные capability-запросы вида `ESC P + q ... ESC \` и `ESC[6n`.
- Django не становится готовым за 90 секунд, fallback уходит в plain, но `.tmp_django.log` иногда уже пустой или перезаписан.

## Подтвержденные подозреваемые

1. **Hot/jurigged как дефолт локальной кнопки.**
   `start_local.bat` запускал `--hot`, хотя для ежедневной работы нужен стабильный plain `runserver --noreload`. Hot полезен как ручной эксперимент, но не как default.

2. **Терминальные control-sequences от hot-stack.**
   Строки `ESC P + q...` и `ESC[6n` похожи на запросы терминальных capabilities. В обычном Django plain-mode они не нужны и не должны попадать в окно launcher-а.

3. **Ложный статус миграций.**
   После `timeout/error` код продолжал идти в общий `else` и писал `[OK] Миграции применены`. Это маскировало реальное состояние preflight.

4. **Лог Django перезаписывался при fallback.**
   Hot-попытка и plain-fallback писали в один файл через `w`, поэтому хвост лога мог потерять первопричину.

5. **Django autoreloader под внешним launcher-ом.**
   Уже исправлено ранее: plain-mode стартует с `--noreload`, чтобы не плодить parent/child процессы и не оставлять старый код на порту.

6. **Daphne/ASGI runserver запускал system checks.**
   Даже plain-команда `runserver --skip-checks --noreload` может уходить в `Performing system checks...`, если активен `daphne` runserver. One-click launcher теперь ставит `DOLG_SKIP_ASGI=1` и использует обычный WSGI runserver.

7. **Healthz зависел от URLConf.**
   `/healthz` был зарегистрирован первым URL, но импорт корневого `urlpatterns` всё равно тянул все `include(...)`. Добавлен ранний `HealthzMiddleware`, чтобы readiness/liveness отвечали до тяжелой маршрутизации.

8. **Тяжелые импорты на старте.**
   Уже исправлено ранее для `openpyxl`: импорт перенесен внутрь XLSX-export handler. Иначе `openpyxl -> numpy` мог добавлять секунды к любому `manage.py`.

9. **`migrate --check` запускал system checks и management-command слой.**
   Для preflight это лишнее: system checks импортируют URLConf, `Dolg_APP.views`, `reportlab`, rule-AI сервисы и читают шаблоны. Launcher теперь использует fast migration probe через `MigrationExecutor`, а `manage.py migrate --noinput --skip-checks` запускает только когда реально есть pending migrations.

10. **Eager Celery import.**
   Уже исправлено ранее: `Dolg_PR.__init__` больше не импортирует Celery app при простом `import Dolg_PR.settings`.

11. **Системная нагрузка Windows.**
   Docker Desktop, Defender, VS Code/Jedi и браузер могут временно раздувать 10-15 секунд до 30+ секунд. Это не главный баг launcher-а, но влияет на таймауты.

12. **Optional app probes не нужны для one-click локального запуска.**
   `django_prometheus`, `axes`, `csp`, `silk` остаются доступны для обычных/prod-команд, но launcher ставит `DOLG_SKIP_OPTIONAL_APP_PROBES=1`, чтобы не тратить старт на лишние probe-импорты.

## Кто может накосячить дальше

- Любые module-level импорты тяжелых библиотек в `views.py`, `urls.py`, `admin.py`, `apps.py`: `numpy`, `pandas`, `scipy`, `matplotlib`, `openpyxl`, `reportlab`, `qrcode`, `playwright`.
- `AppConfig.ready()` с дорогими side effects. Сейчас там только signals/checks, но это место нужно держать легким.
- Новые URL imports, которые подтянут ML/CAD/simulation stack при `manage.py check`, `migrate --check` или `runserver`.
- Docker Desktop/WSL во время локального Python-startup: хорошо для контейнеров, но может съедать CPU/RAM на Windows-хосте.
- Windows Defender, сканирующий `.venv`, `db.sqlite3`, `media`, generated reports и Docker layers.
- Любой launcher, который снова включит `--hot` или Django autoreload по умолчанию.
- Shell/IDE вывод, случайно записанный в config-файлы. Такое уже случалось с `pyproject.toml`, и это ломает инструменты до старта Django.

## Новая политика запуска

- `start_local.bat`: только стабильный `start_server.py --local --no-hot`.
- Hot-mode: ручной режим для точечной разработки:
  `.\.venv\Scripts\python.exe start_server.py --local --hot`
- Plain-mode: всегда `manage.py runserver 127.0.0.1:8000 --skip-checks --noreload`.
- One-click launcher: `DOLG_SKIP_ASGI=1`, чтобы `daphne` не подменял runserver и не запускал дорогие checks.
- One-click launcher: `DOLG_SKIP_OPTIONAL_APP_PROBES=1`, чтобы optional observability/security/dev apps не импортировались без явной необходимости.
- Migration preflight: fast `MigrationExecutor` probe, короткий timeout по умолчанию 10 секунд, timeout/error предупреждает и продолжает только в non-strict режиме, но больше не печатает ложный OK.
- Readiness: `/healthz` отвечает через ранний middleware до URLConf, поэтому Docker/K8s/launcher smoke не ждут импорт всех views.
- `.tmp_django.log`: очищается один раз перед стартом, затем обе попытки `hot/plain` пишутся append-ом с заголовком команды.
- При hot-fallback launcher чистит orphan-процессы и порт перед plain-попыткой.
- Окружение launcher-а гасит цвет и terminal-probes через `TERM=dumb`, `NO_COLOR=1`, `PY_COLORS=0`, `CLICOLOR=0`.

## Быстрые проверки после правок

```powershell
.\.venv\Scripts\python.exe -m py_compile start_server.py
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe scripts\profile_django_checks.py
.\.venv\Scripts\python.exe start_server.py --local --no-hot --no-browser
```

Ожидаемое поведение: порт 8000 освобождается, миграции проверяются мягко, Django поднимается в plain-mode, `/healthz` отвечает, `.tmp_django.log` содержит команду запуска и реальный хвост при ошибке.

## Замеры после оптимизации

Локальный замер на Windows-хосте 2026-06-09:

- `manage.py check`: 9-16 секунд вместо наблюдавшихся ~50 секунд.
- `scripts/profile_django_checks.py`: `django.setup` ~6-8 секунд, сами registered checks ~3-4 секунды.
- Fast migration probe в launcher-е: ~6-7 секунд вместо плавающего `manage.py migrate --check --skip-checks` до 29+ секунд и occasional timeout.
- Launcher smoke `start_server.py --local --no-hot --no-browser`: TCP ready за ~13.6 секунды, `/healthz` вернул `200` с `database/cache: ok`.

Оставшийся главный источник разброса: Windows filesystem / Defender / VS Code Jedi / Docker Desktop background load. Кодовый hot path теперь не зависит от `jurigged`, `daphne runserver`, тяжелого URLConf для healthz и медленного management-command migration check.

---

## TESTS AND REPORTS

Источник: `TESTS_AND_REPORTS.md`

# DOLG — Тесты, отчёты, рекомендации

## 2026-06-03: Admin Monitoring Center P0/P1 baseline

- Закрыт публичный `/metrics` на nginx-границе: Prometheus внутри Docker продолжает scrape `web:8000/metrics/`, но внешний reverse proxy возвращает `403`.
- Добавлен `psutil==7.2.2` для runtime-снимка процесса: RSS/CPU/threads/uptime, disk usage, размеры `media`, `staticfiles`, `Dolg_APP/ml/dataset`, stale search marker и `.incomplete` downloads.
- Добавлен `Dolg_APP/services/ops_metrics.py`: единый snapshot service для runtime, catalog, business, project, AI/ML, moderation и security metrics.
- `/staff/ops/` пересобран как читаемый dashboard с health status, alerts, runtime/disk/business/AI-ML блоками.
- Добавлен staff-only endpoint `GET /staff/ops/api/snapshot/`.
- Главная Django admin `/admin/` получила компактный мониторинговый блок над списком моделей. Он открывается быстро и догружает snapshot через AJAX, чтобы не тормозить админку тяжелой валидацией и обходом storage.
- `check_demo_ready --json` теперь содержит блок `admin_monitoring_stack`.
- Checks: `FAST_TESTS=1 .\.venv\Scripts\python.exe manage.py test Dolg_APP.tests_ml_admin --keepdb -v 1` — **9/9 OK**; `manage.py check` и `makemigrations --check --dry-run` — OK.

## 2026-06-02: MLJob и staff ops dashboard

- Добавлена модель `Dolg_APP.MLJob` и миграция `0018_mljob`: постоянная история ML-задач (`dataset_import`, `training`, `validation`, `export`, `promotion`) со статусом, прогрессом, heartbeat, counters, stdout/error tail и параметрами запуска.
- `/staff/ml-training/` теперь создает `MLJob` для обучения tiny PyTorch backend; `/staff/ml-training/status/` возвращает `latest_job`, а reset помечает активные training/import jobs как `cancelled`.
- `/staff/ml-training/import/` теперь создает `MLJob` для импорта датасетов; `/staff/ml-training/import/status/` синхронизирует cache progress с persistent job и отдает `latest_job`.
- Добавлен staff cockpit `/staff/ops/`: счетчики каталога, проектов, review, AITrainingExample, artifacts, moderation, ML status/type counters, live cache snapshot и последние MLJob.
- Django admin получил `MLJobAdmin`: фильтры по типу/статусу/source, counters, heartbeat/finished timestamps и bulk actions `cancelled/stale/success`.
- Checks: `FAST_TESTS=1 .\.venv\Scripts\python.exe manage.py test Dolg_APP.tests_ml_admin --keepdb -v 2` — **6/6 OK**; `.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` — **No changes detected**; `.\.venv\Scripts\python.exe manage.py check` — **0 issues**; `.\.venv\Scripts\python.exe manage.py migrate Dolg_APP 0018 --noinput` — **OK**.

## 2026-06-02: AI dataset metadata split

- `AITrainingExample.features` стандартизирован без новой таблицы: добавлены `dataset_kind`, `graph_training_ready` и `training_role`.
- Классы корпуса: `scheme_backed`, `review_backed`, `artifact_backed`, `text_only`. PyTorch graph-training берет только graph-ready примеры; text-only learning/source-backed examples остаются для retrieval и объяснений AI.
- Добавлена команда `python manage.py normalize_ai_dataset_metadata --validated-only`: текущая локальная БД обновлена, `scanned=72`, `changed=72`, `graph_training_ready=36`, распределение `text_only=36`, `review_backed=28`, `scheme_backed=8`.
- `/staff/ml-dataset/` показывает `graph-ready` и распределение `Dataset kind`; `AITrainingExampleAdmin` показывает `dataset_kind` и `graph_ready` в списке.
- `AITrainingExampleAdmin` получил первые review-queue actions: `Normalize dataset metadata` и `Exclude selected from graph training`.
- `curated_training_schemes()` теперь фильтрует graph-ready примеры и добавляет `dataset_kind/training_role` в `__training_metadata`.
- Checks: `FAST_TESTS=1 .\.venv\Scripts\python.exe manage.py test Dolg_APP.tests_ml_admin Dolg_APP.tests_ai_dataset_metadata --keepdb -v 1` — **12/12 OK**; `validate_ai_dataset --validated-only --limit 120 --json` — **0 errors, 0 warnings**; `manage.py check`, `makemigrations --check --dry-run`, `check_demo_ready --json`, `check_data_integrity --json` — **OK**.

## 2026-06-01: catalog card hotfix and official photo allowlist

- 2026-06-02: Catalog V3 расширен на расходники, инструменты и модули:
  - `enrich_product_parameters` нормализует витринные названия и `package_type` для consumables/tools/modules;
  - добавлены прямые фильтры `material`, `size`, `wire`, `configuration`, `temperature_range`, `compatibility`, `mode`, `safety`;
  - все preview-чипы карточек остаются кликабельными (`nonclickable preview chips = 0`);
  - allowlist official/supplier photos расширен для `breadboard-400`, `breadboard-830`, `breadboard-2x830`, `pcb-protoboard-7x9`, `pcb-protoboard-9x15`, `jumper-mm-65pcs`.
  - фактические метрики после применения команд: 364 товара, raw package types `0`, verified images `79`, generated fallback `285`.
- Скрыты служебные `Product.parameters` из карточек и деталки: `catalog_quality`, `image_source*`, `image_verified_from` больше не попадают в chips и таблицу характеристик.
- Добавлены широкие chips для длинных значений (`type`, `resolution`, `chip`, `connectivity`), чтобы названия не вылезали и не резались в узкой колонке.
- Добавлена allowlist-команда `import_official_product_photos`; обновлены реальные фото для `solder-paste-138`, `solder-lead-free-100g`, `solder-60-40-100g`, `ao3400`, `irlz44n`, `irf9540n` без Wikimedia/Commons.
- Карточки РЭБ выровнены под более полный «диодный» формат: расширены ключевые параметры (`Imax`, `Iout`, `Vz`, `trr`, `DCR`, `SRF`, `GBW`, `Контакт`), сигнал-теги упрощены до `PDF` / `Данные` / `SPICE`.
- Active SVG fallback отключен: при отсутствии хорошего raster-фото генерируется аккуратный UGO-style PNG без названий товара, неоновой рамки и декоративных дуг.
- Checks: `manage.py check`, `makemigrations --check --dry-run`, `test shop.tests.ProductCardHelperTests shop.tests.ProductImagePolicyTests shop.tests.DatasheetIntelligenceTests` — **15/15 OK**; browser smoke desktop/mobile для `diodes/resistors/transistors/ics/capacitors/inductors/connectors/relays` — no overflow, no active SVG, no service-field leakage; `check_demo_ready --json` и `check_data_integrity --json` — OK, без warnings.

## 2026-05-31: neural curation and dataset import gate

- Added explainable PyTorch `deep_hint`: prediction is checked against expert baseline and returns `agreement_score`, `calibrated_confidence`, `confidence_policy`, similar validated cases and final-control policy.
- Added automatic scheme curation: `collect_good_schemes_for_ai` writes validated `AITrainingExample` rows from demo/opt-in projects with `scheme_family`, `complexity_score/label` and `quality_score/label`.
- Expanded AI dataset from 58 to 72 validated examples, including 14 auto-quality schemes; family/complexity/quality distribution is visible in `/staff/ml-dataset/`.
- Fixed external dataset import: `--persist` no longer writes to a missing model field; added `--local-only`, `--as-projects`, `--project-min-quality` so good imported schemes can also become demo `SchematicProject` rows.
- Hardened Open Schematics download path: direct `requests` streaming writes to `Dolg_APP/ml/dataset/external/hf_cache/`, `--local-only` now exits on cache miss without network retries, and `--download-deadline` skips a slow shard instead of leaving the admin import looking frozen.
- Added controlled project promotion for curated schemes: `promote_ai_examples_to_projects` can create private/team/public `SchematicProject` records from validated `AITrainingExample` rows, and `AITrainingExampleAdmin` exposes private/demo promotion actions. Current DB: 14 AI-curated private draft projects linked back to examples.
- Retrained `media/ml/tiny_circuit_ai.pt`: dataset_size=216, curated_size=36, best_val_loss=0.061056. Evaluation: topology_accuracy=0.9716, next_component_accuracy=0.9602, risk_mae=0.0461.
- Checks: `manage.py check`, `makemigrations --check --dry-run`, `validate_ai_dataset --validated-only --limit 120 --json`, `test Dolg_APP.tests.LightweightLibraryIntegrationTests`, `evaluate_circuit_ai --include-curated`, `promote_ai_examples_to_projects --dry-run --json`, `check_demo_ready --json`, `check_data_integrity --json` - OK.

## 2026-05-31: admin/shop security gate

- Подробный отчет: [AUDIT_ADMIN_SHOP_20260531.md](AUDIT_ADMIN_SHOP_20260531.md).
- Закрыто: POST-only для корзины/сравнения, auth-cart bug в `repeat_order`, локальный `SECRET_KEY`, opt-in `ManifestStaticFilesStorage`, миграции Decimal-валидаторов, media-policy error `t1-ok`, неизвестные `legal_sources` в expert rules.
- Админка усилена как data-control слой: Product quality summary/actions, Order bulk audit, optimized `select_related/prefetch_related`, smoke 14/14 admin pages = 200.
- Проверки: `manage.py check`, `makemigrations --check --dry-run`, targeted tests, `check_data_integrity --json`, `check_demo_ready --json` — OK.

Сводный документ по тестированию и состоянию проекта.

---

## 1. Текущий статус

- `python manage.py check` — **0 ошибок** (включая 0 silenced).
- `python manage.py makemigrations --check --dry-run` — **No changes detected** после добавления scientific simulation stack и миграции `Dolg_APP.0010`.
- `python manage.py migrate` — локальная SQLite применяет `Dolg_APP.0010_schematicproject_approval_state_and_more`.
- Targeted regression нового этапа — **20/20 OK**:
  `python manage.py test Dolg_APP.tests.EngineeringReviewTests knowledge.tests.EngineeringLabTests knowledge.tests.PopulateKnowledgeLearningTests shop.tests.GlobalSearchAndDemoRouteTests --keepdb -v 2`.
- Targeted regression scientific stack — **13/13 OK**:
  `python manage.py test Dolg_APP.tests.SimulationAnalysisLibraryTests --keepdb -v 2`.
- Targeted regression scientific stack + lab — **16/16 OK**:
  `python manage.py test Dolg_APP.tests.SimulationAnalysisLibraryTests knowledge.tests.EngineeringLabTests --keepdb -v 1`.
- Search regression scientific stack — **7/7 OK**:
  `python manage.py test shop.tests.GlobalSearchAndDemoRouteTests --keepdb -v 2`.
- Demo-ready scientific stack smoke — **1/1 OK**:
  `python manage.py test shop.tests.DemoReadyCommandScientificStackTests --keepdb -v 2`.
- Targeted regression lightweight graph/formula/SVG stack — **11/11 OK**:
  `python manage.py test Dolg_APP.tests.LightweightLibraryIntegrationTests Dolg_APP.tests.EngineeringReviewTests --keepdb -v 2`.
- Targeted regression learning formula/SVG stack — **16/16 OK**:
  `python manage.py test knowledge.tests.LightweightLearningLibraryTests knowledge.tests.LearningModelAndGraderTests --keepdb -v 2`.
- Targeted regression expert-first stack — **18/18 OK**:
  `python manage.py test Dolg_APP.tests.ExpertSystemLibraryTests Dolg_APP.tests.EngineeringReviewTests Dolg_APP.tests.LightweightLibraryIntegrationTests shop.tests.DemoReadyCommandScientificStackTests --keepdb -v 2`.
- Targeted regression import preview + Learning-by-review — **11/11 OK**:
  `python manage.py test Dolg_APP.tests.EngineeringReviewTests --keepdb -v 2`.
- Demo-ready smoke после import-preview обновления — **1/1 OK**:
  `python manage.py test shop.tests.DemoReadyCommandScientificStackTests --keepdb -v 2`.
- Media Quality Gate regression — **10/10 OK**:
  `python manage.py test shop.tests.ProductImagePolicyTests --keepdb -v 1`.
- Datasheet Intelligence V1 regression — **3/3 OK**:
  `python manage.py test shop.tests.DatasheetIntelligenceTests --keepdb -v 2`.
- Browser smoke harness import -> review -> learning — **1 skipped без RUN_BROWSER_E2E**:
  `python manage.py test Dolg_APP.tests_browser --verbosity 1 --keepdb`.
- Search regression expert topics — **8/8 OK**:
  `python manage.py test shop.tests.GlobalSearchAndDemoRouteTests --keepdb -v 2`.
- Server regression затронутых приложений — **123/123 OK**:
  `python manage.py test Dolg_APP.tests knowledge.tests shop.tests --keepdb -v 1`.
- `python manage.py check_demo_ready --json` после `migrate`, `populate_knowledge` и `seed_legal_sources` — **OK**; текущие счетчики: 5 learning tracks, 16 lessons, 38 tasks, 12 demo projects; `scientific_stack` показывает версии NumPy/SciPy/Matplotlib/Pandas/python-engineering и service-smoke `fft_svg/bode_svg/monte_carlo_svg/signal_quality_svg/parameter_sweep_svg/dc_fallback`, `graph_stack`, `formula_stack`, `circuit_svg_stack` проверяют NetworkX/SymPy/Schemdraw, `expert_stack` проверяет jsonschema/rule-engine/Pint/Lark/Z3/scikit-fuzzy, а `legal_sources_stack` проверяет source retrieval, rule bibliography, search smoke, source-backed learning и AI training metadata.
- Новые проверки покрывают `ProjectReview`, `ProjectMeasurement`, LTspice/SPICE import subset, visual/server-side import preview, сохранение импортированной схемы в проект с review, Learning-by-review suggestions, self-hosted rule AI fallback, lab sweep, сравнение измерений, diagnostics learning track и поиск по `LTspice/derating`.
- Новые проверки scientific stack покрывают FFT peak detection, Bode plot для RC, Monte Carlo tolerance, THD/SINAD/ENOB signal quality, parameter sweep, NumPy DC fallback, Bode/Monte Carlo/Signal/Sweep Pro-only API, non-Pro fallback API, Pro toolbar в шаблоне, сохранение Pro-метрики в `ProjectMeasurement`, Pandas-статистику запусков и demo-ready service-smoke.
- Новые проверки lightweight stack покрывают NetworkX-топологию схем, предупреждения о схеме без GND, floating nodes, определение делителя, SymPy-формулы и эквивалентные выражения, Schemdraw SVG для учебных схем и lazy import тяжелой scientific-аналитики.
- Новые проверки expert-first stack покрывают rule pack validation через `jsonschema`, `rule-engine` predicates, Pint parsing русских и ASCII-единиц, Lark SPICE/LTspice import subset, Z3-подбор делителя, scikit-fuzzy risk score, expert findings в `ProjectReview`, `Expert trace` в `rule_ai` и поиск по `rule-engine/jsonschema/pint/z3/fuzzy`.
- `python manage.py check_demo_ready --json` — **OK**, URL smoke, no-Wikimedia media-policy, Media Quality Gate, scientific stack smoke, lightweight stack smoke, expert stack smoke, `cad_import_preview_details` и Learning-by-review smoke проходят.
- `python manage.py check_data_integrity --json` — аудит БД/данных: **0 ошибок, 0 предупреждений**; пустых, битых, Commons/curated и неподконтрольных активных изображений нет; `missing_datasheet_extracted=[]` для РЭБ-товаров; `catalog.media_quality` показывает 364 проверенных изображения, `average_score=100`, `error_count=0`, `warning_count=0`, `imagehash_available=true`.
- Тарифный слой Free/Pro/Enterprise проверяется через `Dolg_APP.services.entitlements`: Pro-аналитика и расширенный AI возвращают `plan_required` для Free, Pro получает scientific/AI features, Enterprise получает командные AI/org features. `check_demo_ready --json` содержит блок `entitlement_stack`.
- Datasheet Intelligence V1 заполняет `Product.parameters.datasheet_extracted` даже без live-доступа к PDF: fallback берет package, ratings, operating conditions, thermal/application hints из нормализованных параметров товара, а деталка товара показывает compact DI summary вместо сырого JSON.
- Каталог-медиа: 364 товара; 79 активных реальных фото перенесены в `products/verified/`, остальные позиции получают generated PNG fallback. Активные карточки не ссылаются на `products/commons/`, `products/curated/` или неподконтрольные внешние изображения; качество контролируется `shop.services.media_quality` через Pillow/ImageHash.
- Обучение и лаборатория: 5 опубликованных маршрутов, 16 уроков, 38 заданий; `/knowledge/lab/` входит в demo-ready URL smoke.
- `python manage.py test --keepdb -v 1` — для полного discovery-прогона в текущем окружении уперся в 15-минутный таймаут; актуальный проверенный gate пока разбит по приложениям.
- `.\scripts\run_browser_e2e.ps1` — **3/3 OK** для browser-smoke сценариев `/simulation/ → BOM → XLSX → cart`, `/cad/` и `/projects/`.
- ngspice.wasm подключён, AC/TRAN/DC анализы работают через Web Worker.
- JS-MNA fallback покрывает DC, если WASM недоступен.

---

## 2. Покрытие тестами по приложениям

| Приложение | Файл | Тестов | Что покрыто |
|---|---|---:|---|
| `accounts` | [accounts/tests.py](accounts/tests.py) | 8  | Модель `UserProfile`, автосоздание через сигнал, `full_address`, регистрация, логин, профиль, команда `setup_roles` и роль менеджера |
| `shop`     | [shop/tests.py](shop/tests.py)         | 64 | Модели `Category`/`Product`, view-страницы, `_apply_filters`, `search_suggest`, глобальный поиск по товарам/статьям/проектам/learning/tool topics включая FFT/Bode/Monte Carlo и expert topics, Datasheet Intelligence V1, demo-ready scientific/lightweight/expert stack smoke, `api_component_search`, анализатор «лучше/хуже» в сравнении, `api_bom_match`, server-side XLSX-экспорт BOM, `api_bom_add_all`, `compare_toggle`/`compare_clear` |
| `orders`   | [orders/tests.py](orders/tests.py)     | 16 | Модель `Order`, генерация `order_number`, полный flow checkout (создание Order+OrderItem, списание stock, очистка корзины, email-уведомление, отказ при нехватке stock, требование адреса, пустая корзина → редирект), отмена заказа (возврат stock, статус, защита от чужих), повтор заказа |
| `Dolg_APP` | [Dolg_APP/tests.py](Dolg_APP/tests.py), `Dolg_APP/tests_*.py` | 58 + 101 role-matrix | Модели проектов, `ProjectReview`, expert findings, rule pack validation, Pint unit parsing, Lark import, Z3 solver, fuzzy risk, NetworkX topology metrics, `ProjectMeasurement`, CAD import, self-hosted AI, Pro FFT/Bode/Monte Carlo, signal quality THD/SINAD/ENOB, parameter sweep, NumPy fallback, Pandas simulation stats, Pro toolbar smoke, сохранение Pro-метрик, PCB layout, share-token, demo populate, role/plan regression suites |
| `knowledge` | [knowledge/tests.py](knowledge/tests.py) | 29 | Энциклопедия, связанные товары и контекстные расчеты в статьях, модели обучения, grader `math/circuit/simulation`, SymPy formula grading, Schemdraw учебные SVG, инженерная лаборатория, `python-engineering` validation backend, API `/knowledge/lab/api/`, seed `populate_knowledge` для learning tracks |

**Итого по серверным тест-файлам: текущий счетчик по обнаруженным `test_` — 247 тестов в `shop/Dolg_APP/knowledge`, включая role-matrix suites в `Dolg_APP/tests_*.py`. Последний полный gate до lightweight/expert stack был разбит по targeted-прогонам; новый слой закрыт targeted-прогонами 18/18, 16/16 и 8/8 OK. Полный стандартный прогон лучше запускать разбивкой по приложениям или с большим таймаутом.**

---

## 3. Как запускать

```bash
# Активировать venv (Windows)
.\.venv\Scripts\activate

# Проверка конфигурации
python manage.py check

# Полная проверка с coverage (Windows PowerShell)
.\scripts\run_checks.ps1

# Все тесты вручную
python manage.py test accounts shop orders Dolg_APP

# Отдельное приложение
python manage.py test shop
python manage.py test orders
python manage.py test accounts
python manage.py test Dolg_APP

# Browser/e2e smoke (требует Microsoft Edge и Playwright)
.\scripts\run_browser_e2e.ps1

# Вердикт стандартного запуска: "Ran 124 tests ..." → OK (skipped=6).
# Вердикт browser-smoke: "Ran 3 tests ..." → OK.

# Аудит данных перед демонстрацией
python manage.py check_demo_ready --json
python manage.py check_data_integrity --json
```

Тесты используют `--keepdb` стратегию косвенно: SQLite in-memory через `Dolg_PR/settings.py` (DATABASES.default использует `:memory:` под `test`-командой).

---

## 4. История ключевых изменений тестового слоя

1. **2026-04-23:** свернуты ~30 мелких `*.txt`/`*.md`-отчётов в этот документ.
2. **2026-04-24:** добавлен `Dolg_APP/tests.py` с 17 тестами на `SchematicProject`, API проектов и `populate_demo_projects`. К 2026-04 — 34 теста.
3. **2026-04-26:** включены тесты квот симуляции (`SimulationQuota`).
4. **2026-04-27:** расширены `shop/tests.py` (31 тест: `_apply_filters`, `search_suggest`, BOM-API, compare-сессия) и `orders/tests.py` (14 тестов: полный checkout flow, отмена заказа, генерация `order_number`). Итог — 66 тестов.
5. **2026-05-03:** добавлены тесты повторного заказа и email-уведомления checkout, настроены `.coveragerc`, `scripts/run_checks.ps1` и GitHub Actions. Итог — 68 тестов.
6. **2026-05-03:** добавлены роли менеджера, история версий схем, журнал результатов симуляции, гостевой demo-режим `/simulation/`, DRC-проверка и PDF-экспорт схемы; расширены тесты `accounts` и `Dolg_APP`. Итог — 74 теста.
7. **2026-05-03:** добавлены `api_component_search`, поиск товара каталога из панели свойств компонента, учёт явного `catalog_ref` в BOM и маппинг NPN/PNP на категорию транзисторов. Итог — 78 тестов.
8. **2026-05-03:** добавлен server-side XLSX-экспорт BOM через `openpyxl`, общий helper расчёта BOM и проверка структуры Excel-книги в тестах. Итог — 79 тестов.
9. **2026-05-03:** добавлены Playwright browser-smoke для `/simulation/`, DRC/BOM-проверки номиналов и SPICE-моделей, helper `ensureComponentPorts` для старых схем без `ports`. Стандартный итог — 83 OK + 1 skipped, browser-smoke отдельно — 1/1 OK.
10. **2026-05-03:** расширены browser-smoke сценарии для `/cad/` и `/projects/`, добавлена `normalizeSchemeData()` и единая нормализация схем при загрузке/сохранении. Стандартный итог — 83 OK + 3 skipped, browser-smoke отдельно — 3/3 OK.
11. **2026-05-17:** добавлен `check_data_integrity`: проверка изображений товаров, hash-дублей, запрета Wikimedia/Commons, параметров РЭБ, материалов энциклопедии, внутренних ссылок и структуры demo-схем. Seed demo-схем теперь назначает позиционные обозначения и ортогональные маршруты.
12. **2026-05-18:** media-слой каталога переведён на выборочную no-Wikimedia policy: точные локальные assets сохраняются, а для неподтверждённых/проблемных позиций `apply_curated_product_photos` генерирует technical placeholder PNG через `Pillow`. `import_commons_product_photos` отключён, `check_demo_ready` и `check_data_integrity` блокируют `products/commons/*`, `products/curated/*` и Wikimedia URL.
13. **2026-05-25:** добавлен `apply_verified_product_photos`: проверенные реальные фото из старого локального кеша копируются в `products/verified/`; denylist оставляет супы, еду, воду, разбитые экраны и неверные товарные кадры на generated fallback.
13. **2026-05-17:** добавлен практикум `knowledge`: модели `LearningTrack/Lesson/Task/Attempt/Progress`, автопроверка math/circuit/simulation задач и redirect старого `/learn/`.
14. **2026-05-17:** добавлена инженерная лаборатория `/knowledge/lab/`: расчеты транзисторного ключа, NE555, стабилизатора, RC-антидребезга и теплового запаса; второй learning track использует общий service-layer лаборатории. Итог — 146 тестов.
15. **2026-05-17:** добавлен scientific simulation stack: NumPy/SciPy/Matplotlib/Pandas для FFT, Bode plot, Monte Carlo tolerance, THD/SINAD/ENOB signal quality, parameter sweep, server-side DC fallback и статистики запусков; `python-engineering` подключен как validation backend лаборатории. Pro-метрики сохраняются в `ProjectMeasurement`, глобальный поиск находит FFT/Bode/Monte Carlo/SciPy/THD/sweep, а `check_demo_ready` проверяет scientific stack service-smoke. Целевой прогон затронутых приложений — 123/123 OK.
16. **2026-05-18:** добавлен lightweight graph/formula/SVG stack перед нейронным sprint: `networkx` в `Dolg_APP/services/schematic_graph.py`, `sympy` в `knowledge/services/formula_steps.py`, `schemdraw` в `knowledge/services/circuit_svg.py`. Review, rule AI и learning grader используют общий service-layer; `check_demo_ready` проверяет `graph_stack/formula_stack/circuit_svg_stack`; PyTorch/GOLEM не входят в основной runtime.
17. **2026-05-18:** добавлен expert-first stack: `jsonschema` + `rule-engine` для rule packs, Pint для unit-safe номиналов, Lark для SPICE/LTspice subset, Z3 для constraint-подбора, scikit-fuzzy для мягкой оценки риска. `ProjectReview` получает `expert_findings` и fuzzy-risk, `rule_ai` отвечает по `Expert trace`, `check_demo_ready` проверяет `expert_stack`; OR-Tools/RDFLib/PyTorch/GOLEM остаются roadmap.
18. **2026-05-19:** добавлен Media Quality Gate: `ImageHash` + `PyWavelets` поверх Pillow, сервис `shop/services/media_quality.py`, проверки читаемости, размера, пустоты, aspect ratio, edge density и perceptual hash. `check_data_integrity` и `check_demo_ready` выводят media-quality блок; generated placeholders не считаются perceptual-дублями.
19. **2026-05-25:** расширен self-hosted AI-помощник: `rule_ai` различает intent-режимы GND, measurement, BOM, import, learning, derating, recommend и fix-plan; API возвращает `intent`, `confidence`, `quick_actions`, а UI показывает режим и быстрые действия. Добавлены regression-тесты на GND-вопрос и ответ по сохраненному измерению.
20. **2026-05-25:** добавлен Self AI V2 и tiny PyTorch backend: `/api/ai/context/`, карточка "Разбор схемы" в AI-панели, 20 сообщений истории + `session_summary`, structured quick actions, `context_sources`, lazy neural backend `Dolg_APP/ml/neural.py`, optional `requirements-ai.txt`, команда `train_tiny_circuit_ai`. Targeted tests `EngineeringReviewTests + LightweightLibraryIntegrationTests` — **25/25 OK**; `check_demo_ready --json` показывает `neural_stack` OK.
21. **2026-05-26:** добавлен entitlement-layer для Free/Pro/Enterprise: Pro endpoints, AI chat/context/pipeline и org-level Enterprise функции проверяются через общий feature matrix; API возвращает `plan_required`, `token_usage`, `entitlements`, а `/api/usage/today/` возвращает `plan/features/feature_flags`.
22. **2026-05-26:** добавлен безопасный opt-in контур AI-обучения пользовательских схем: поле профиля `allow_ai_training`, команда `collect_ai_training_examples`, поддержка curated schemes в `train_tiny_circuit_ai --include-curated`. Обучение остается пакетным, не во время ответа ассистента.
23. **2026-05-26:** добавлена карта легальных источников `docs/LEGAL_RESOURCE_MAP_20260526.md`: внешние подборки используются только как список тем/названий, а AI/diploma/code corpus строится на официальной документации, открытых учебниках, datasheet, demo-проектах и opt-in пользовательских схемах.
24. **2026-05-26:** `legal_sources.json` превращен в active evidence-layer: `find_legal_sources`, `sources_for_rule`, `sources_for_learning_topic`, source-aware retrieval в Self AI, компактные источники в review HTML/PDF, группа `Источники и документация` в глобальном поиске/autocomplete, source-backed learning seed и metadata для `AITrainingExample`. Проверки: `LegalSourcesTests` — **3/3 OK**, `GlobalSearchAndDemoRouteTests + DemoReadyCommandScientificStackTests` — **12/12 OK**, `DataIntegrityLegalSourcesTests` — **1/1 OK**, AI GND/retrieval regression — **2/2 OK**.

---

## 5. Что осталось из рекомендаций

- **`coverage.py`** — настроен через `.coveragerc`; локальный запуск: `.\scripts\run_checks.ps1`.
  Текущий отчёт по прикладному коду после исключения служебных entrypoint/management-файлов — **77 %** строк.
- **CI** — добавлен GitHub Actions workflow `.github/workflows/django.yml` с `python manage.py check`, тестами и coverage-отчётом.
- **Front-end-тесты:** Playwright smoke реализован для `/simulation/ → BOM → XLSX → cart`, `/cad/` и `/projects/`. Остаются сценарии: «расчет в лаборатории -> схема -> измерение -> обучающее задание», «нарисовать делитель → запустить DC», «открыть демо RC-фильтр → AC → −3 дБ-маркер виден», «экспортировать SVG/PDF», visual regression desktop/mobile.
- **Media-аудит:** текущий базовый слой закрыт локальными assets + generated-заглушками и Media Quality Gate. Следующий шаг — optional allowlist официальных изображений производителей/дистрибьюторов, если есть права/ключи API; неподтвержденные product-shot и Wikimedia не включать.

---

## 6. Что было удалено при консолидации (2026-04-23)

`FINAL_REPORT.txt`, `FINAL_STATUS.txt`, `FINAL_TEST_REPORT.md`, `TEST_FINAL.md`, `TEST_FINAL.txt`, `TEST_FINAL_REPORT.md`, `TEST_RESULT.txt`, `TEST_RESULT_SUMMARY.txt`, `check.txt`, `check_final.txt`, `conclusion.txt`, `done.txt`, `end.txt`, `final.txt`, `final_check.txt`, `final_output.txt`, `final_result.txt`, `final_test.txt`, `report.txt`, `result.txt`, `result_final.txt`, `status.txt`, `status_final.txt`, `test.txt`, `test_completion.txt`, `test_done.txt`, `test_final_status.txt`, `test_report.md`, `test_status.txt`.

Все 29 файлов содержали либо одинаковый текст «Тестирование завершено. Результат: OK», либо обрывки старых пробных запусков.

## 2026-05-25: review i18n

- Добавлен `Dolg_APP/services/review_i18n.py`: перевод пользовательских сообщений проверки схемы, fault library, expert findings, статусов и рекомендаций на русский язык.
- HTML/PDF review-отчет усилен демонстрационными блоками: русские метрики, expert findings, evidence, fault-сценарии и сохраненные измерения.
- `EngineeringReviewTests` проверяет, что отсутствующий GND, severity label, self-hosted AI reply, GND-intent и measurement-intent выводятся по-русски.
- `check_demo_ready --json` расширен smoke-проверками `review_russian_i18n` и `review_metric_rows_ru`.
- `check_demo_ready --json` также проверяет optional neural stack: наличие PyTorch и обученной tiny-модели `media/ml/tiny_circuit_ai.pt`.

## 2026-05-25: engineering artifact ingestion

- Добавлены модели `EngineeringArtifact` и `AITrainingExample`, миграция `Dolg_APP.0015_engineeringartifact_aitrainingexample`.
- Добавлен сервис `Dolg_APP/services/artifact_ingestion.py` и команда `python manage.py ingest_engineering_artifacts`: DOCX/PDF/PPTX/DXF, P-CAD NET/DRC/ERC, OLE metadata; DWG/MS14 сохраняются как metadata-only артефакты с предупреждением о конвертации.
- `ProjectReview` теперь учитывает внешние CAD-проверки, readiness к сборке и reliability summary; review i18n добавляет `title_ru`, `evidence_ru`, `recommendation_ru` для findings.
- `rule_ai` получает artifact memory и learning-by-artifact подсказки, но финальный инженерный verdict остается за expert rules + человеком.
- Проверки: `python manage.py test Dolg_APP.tests.ArtifactIngestionTests Dolg_APP.tests.EngineeringReviewTests Dolg_APP.tests.LightweightLibraryIntegrationTests --verbosity 2` -> **29/29 OK**.
- `python manage.py check_demo_ready --json` -> **OK**, новый блок `artifact_stack` проверяет `pypdf/python-docx/python-pptx/ezdxf/olefile`, P-CAD DRC/NET, DXF, DWG/MS14 stubs, learning-by-artifact и AI training examples.

## 2026-05-31: Self AI / PyTorch dataset sprint

- Расширен `Dolg_APP/services/ai_training.py`: сбор AI examples теперь поддерживает opt-in/demo-схемы, опубликованные learning tasks, сохраненные `ProjectReview` snapshots и `EngineeringArtifact`.
- Добавлены dataset-команды:
  - `python manage.py collect_ai_training_examples --source all --limit N`;
  - `python manage.py validate_ai_dataset --json`;
  - `python manage.py export_ai_dataset --output ...jsonl`;
  - `python manage.py evaluate_circuit_ai --include-curated`.
- `AITrainingExampleAdmin` получил dashboard: total/validated/unvalidated, scheme_data coverage, source_ids, teacher_rules, evidence_kind, topology/source distribution и результат быстрой валидации.
- Self AI теперь возвращает `skills` как структурированный список возможностей: diagnose scheme, explain review, suggest measurement, choose nominal, compare variants, learning task from error, artifact summary, defense demo script.
- Pro/Enterprise deep-hint подключен к `/api/ai/chat/` и `/api/ai/context/`: PyTorch дает вероятностную подсказку по topology/risk/next component, но финальный инженерный verdict остается за expert rules + человеком.
- `api_ai_pipeline_info` возвращает summary AI dataset вместе с neural backend metadata.

Проверки:

- `python manage.py check` -> OK.
- `python manage.py makemigrations --check --dry-run` -> OK, No changes detected.
- `python manage.py validate_ai_dataset --validated-only --limit 20` -> OK, scanned=12, errors=0, warnings=0.
- `python manage.py collect_ai_training_examples --source all --limit 5 --dry-run --json` -> OK.
- `python manage.py export_ai_dataset --limit 5 --output Dolg_APP/ml/dataset/exports/ai_training_dataset_smoke.jsonl --json` -> OK; smoke-файлы после проверки удалены.
- Admin/API smoke: `/admin/Dolg_APP/aitrainingexample/`, `/staff/ml-training/`, `/api/ai/pipeline/info/` -> 200.
- Targeted tests: `Dolg_APP.tests.AIAssistantModuleTests` + `Dolg_APP.tests_premium.AIPipelineTests` -> **9/9 OK**.

## 2026-05-31: Self AI graph-feature upgrade

- Добавлен curated baseline для нейробалабола: `collect_ai_training_examples --source curated` создает 8 идемпотентных примеров по делителю, GND, LED, RC, floating fragment, source-short и BOM/model binding.
- `collect_ai_training_examples --source all --limit 50` собрал корпус из 58 валидированных записей: 14 review/demo/opt-in схем, 8 curated cases и 36 learning tasks.
- `Dolg_APP/ml/neural.py` обновлен до `0.3.0-tiny-graph-pytorch`: feature vector расширен до 30 признаков, добавлены 10 NetworkX-derived признаков связности, floating/isolated components, циклов, output node, topology one-hot и coverage путей до GND.
- Старые несовместимые модели теперь не ломают AI: при несовпадении `state_dict` backend откатывается на fresh baseline и просит переобучение.
- Добавлена staff-страница `/staff/ml-dataset/`: сводка корпуса, ошибки/предупреждения валидации, evidence kind, topology, teacher rules, legal sources и metadata tiny model.
- AI-панель `/simulation/` показывает PyTorch deep hint отдельным компактным блоком в карточке “Разбор схемы” и добавляет краткую neural-сводку в ответ чата.

Проверки:

- `python manage.py collect_ai_training_examples --source curated --json` -> OK, created=8.
- `python manage.py collect_ai_training_examples --source all --limit 50 --json` -> OK, total=58, validated=58.
- `python manage.py validate_ai_dataset --validated-only --limit 100 --json` -> OK, scanned=58, errors=0, warnings=0.
- `python manage.py train_tiny_circuit_ai --include-curated --max-curated 300 --size 180 --epochs 80 --json` -> OK, model version `0.3.0-tiny-graph-pytorch`, dataset_size=202, curated_size=22, best_val_loss=0.312815.
- `python manage.py evaluate_circuit_ai --include-curated --max-curated 100 --size 120 --json` -> OK, topology_accuracy=0.9648, next_component_accuracy=0.9577, risk_mae=0.0636.
- Staff/API smoke: `/staff/ml-training/`, `/staff/ml-dataset/`, `/admin/Dolg_APP/aitrainingexample/`, `/api/ai/pipeline/info/` -> 200.
- Deep-hint smoke: `build_rule_based_reply(... include_deep_hint=True)` -> trained=True, model `0.3.0-tiny-graph-pytorch`.
- Targeted tests: `Dolg_APP.tests.AIAssistantModuleTests` + `Dolg_APP.tests_premium.AIPipelineTests` -> **9/9 OK**.

## 2026-06-01: REB catalog quality normalization

- Добавлен service-layer `shop/services/reb_catalog_quality.py`: нормализация РЭБ-каталога после сидов `populate_reb_products` / `populate_catalog_v2`.
- Добавлена команда `python manage.py normalize_reb_catalog`: восстанавливает `part_number`, уточняет `package_type`, выводит `mounting`, добавляет rating-поля (`max_voltage`, `current`, `power`, `supply_voltage`) и `datasheet_url`/family reference для REB-карточек.
- После нормализации выполнен `python manage.py enrich_datasheets --all --missing-only --json`: заполнены metadata fallback records `Product.parameters.datasheet_extracted` для новых datasheet URL.
- Исправлен постоянный Django warning в `Dolg_APP/templates/tools/simulation.html`: многострочный `{# ... #}` заменен на `{% comment %}...{% endcomment %}`.

Проверки:

- `python manage.py normalize_reb_catalog --json` -> OK, changed=201; затем повторный запуск -> changed=4 для добивки `XL6009`, `TOR-220uH`, `HL-1U-5V`, `JQX-105F-12V`.
- `python manage.py enrich_datasheets --all --missing-only --json` -> OK, processed=184, metadata_fallback.
- `python manage.py check` -> OK, 0 warnings.
- `python manage.py makemigrations --check --dry-run` -> OK, No changes detected.
- `python manage.py test shop.tests.RebCatalogQualityTests shop.tests.DatasheetIntelligenceTests --keepdb -v 2` -> **6/6 OK**.
- `python manage.py check_data_integrity --json` -> OK, 0 errors, 0 warnings; `invalid_reb=0`, `missing_datasheets=0`, `missing_datasheet_extracted=0`, `missing_rating_limits=0`.
- `python manage.py check_demo_ready --json` -> OK, 0 errors, 0 warnings.

---

## UX FRONTEND AUDIT

Источник: `UX_FRONTEND_AUDIT.md`

# UX / Frontend аудит проекта DOLG (2026-06-22)

Глубокий разбор фронтенда по всему проекту: системные проблемы, приоритеты, роадмап 4 батчей.
База: 19 каталогов шаблонов, главные поверхности — симулятор (20.5k строк), CAD (6.4k), магазин,
проекты, knowledge, orgs (13 шаблонов). Тема — `cosmic_theme.css` (2879 строк).

## Системные находки (приоритет — затрагивают весь продукт)

### P0. Фрагментированный фидбек — 4 разных механизма, единого нет

| Механизм | Где | Проблема |
|---|---|---|
| Нативные `alert()/confirm()` | **37 вызовов** в 15 файлах (CAD 13, sim 9, профиль, проекты, orgs, billing, orders) | Блокирующие, уродливые, вне темы, не стилизуются, не для мобилы |
| Django messages `.alert` | shop/base, orgs | Server-render, только при перезагрузке страницы |
| `showNotification` | только simulation.html (✅ уже апгрейжен в тосты) | Симулятор-онли |
| `chat-toast.js` | чат | Свой отдельный тост |

→ **Нужен единый `window.DolgToast`** в общей статике: тосты (готовый код из симулятора), мост
Django messages → тост, замена нативных alert/confirm на тему. Один механизм на весь продукт.

### P0. Главный `Dolg_APP/base.html` не показывает Django messages

В базовом шаблоне инструментов/проектов/аккаунта **нет блока `{% if messages %}`** → серверный
фидбек (`messages.success('Сохранено')`) **молча теряется**. shop/base.html сообщения показывает —
поведение непоследовательно. → Добавить мост messages → DolgToast в base.html.

### P1. `prefers-reduced-motion` почти не уважается (4 упоминания на весь проект)

Анимаций много (и я добавляю новые). Пользователи с чувствительностью к движению / `reduce` в ОС
их получают всё равно. → Глобальный guard `@media (prefers-reduced-motion: reduce)` в теме.

### P2. Два разошедшихся base.html (Dolg_APP + shop)

Дублируют навигацию/футер/тему, расходятся в поведении (messages, обёртки). → На будущее —
консолидация в один каркас или общий include шапки/подвала.

### P2. Доступность и фокус

Модалки без trap-фокуса и возврата фокуса; нативные alert «случайно» дают a11y, кастомные — нет.
aria-атрибуты местами есть, системно — нет. → При работе над модалками добавить focus-trap + Esc.

## Роадмап батчей (выбраны юзером)

### A. Приборы живые (симулятор) — физичные анимации

- Осциллограф: бегущая линия развёртки / постепенная отрисовка трассы (уже есть reveal `936c364` —
  расширить на «живой» режим).
- Мультиметр: анимация смены показаний (есть `mmDisplayPulse` — задействовать на обновлении).
- Статусные индикаторы движка: «бьётся» во время счёта.

### B. Плавные модалки/переходы (весь проект)

Модалки открываются/закрываются рывком. → Единый fade+scale переход (класс-обёртка), Esc-закрытие,
focus-trap. Применить к 3D/поверхности/экспорту/импорту/auth-модалкам.

### C. Горячие клавиши + подсказка

Esc=закрыть верхнюю модалку, запуск симуляции с клавиатуры, Ctrl+Z/Y (где есть), `?`=overlay-шпаргалка
со списком. Аккуратно с конфликтами (Space=пан в CAD).

### D. Пустые состояния / скелетоны

Дружелюбные подсказки вместо пустых панелей (результаты симуляции до запуска, список проектов,
каталог) + loading-скелетоны вместо «мигания».

## Уже сделано в этой сессии (фундамент батчей)

- ✅ Тосты в симуляторе: типы/цвета (вкл. красный error), стекинг, иконки, прогресс-бар (`2a0ee8d`).
- ✅ Индикатор загрузки на кнопке запуска (`bd0751e`).
- ✅ Анимация прорисовки графика результата (clip-path reveal) (`936c364`).

## Предлагаемый порядок

1. **P0 единый DolgToast + мост Django messages + reduced-motion guard** (фундамент, чинит 2 системных бага).
2. Батч A (приборы) и D (пустые состояния) — самые «вау» для защиты.
3. Батч B (модалки) + C (клавиши) — общий лоск.
4. Постепенная замена 37 нативных alert/confirm на тему.

---

## VISUALIZATION 3D PLAN

Источник: `VISUALIZATION_3D_PLAN.md`

# План: 3D-визуализация (графики + схемы) + анимации

Фокус (20260621): 3D-визуализация **графиков результатов** и **схем**, параллельно с анимациями.
Приборы/виртуальная лаборатория — обучающая сторона (см. INSTRUMENTS_PLAN.md), не сюда.

## Что есть (инвентаризация — по аудиту 20260621)

`scheme-3d.js` (84КБ, Three.js, API `window.DolgScheme3D`) оказался **зрелым**, многое из
«как в реальности» УЖЕ готово:
- **Реалистичная плата:** материалы FR-4/soldermask/silkscreen/pad-finish (EDA-пресеты из
  `scheme-3d-materials.js`), env-map, реальные модели корпусов (`scheme-3d-components.js`).
- **Реальная разводка:** трассы автороутера в 3D (`_axisAlignedSegments`, `routeJoints`,
  `_renderRouteJoints`) — ✅ уже есть.
- **Данные на плате:** `setThermalOverlay(powerMap)` — тепловая/мощностная карта по компонентам ✅.
- **Слои:** `setLayerOpacity`/`setSoloLayer`/`setExplodeFactor` (explode-вид) ✅.
- **Камера/прочее:** `setAutoRotate` (облёт), `highlightComponent`, измерение, GLB/PNG-экспорт.

**Реальные пробелы (а не «всё с нуля»):**
1. **3D-поверхность данных** (поле напряжений как рельеф) — нет; это отдельный тип графика.
2. **Overlay по напряжению/току** — есть только power/thermal; расширить тем же механизмом.
3. **Анимация overlay/поверхности по transient** (морфинг по времени) — авто-вращение есть,
   а время-морфинга данных нет.

Данные готовы: движки (U/I/волны/AC) + `large_circuits.voltage_field` (поле сетки для поверхности).

## Что строим

### Графики результатов в 3D (новое — главный вектор)
| Визуализация | Данные | Что показывает | Вес | P |
|---|---|---|---|---|
| **3D-поверхность поля напряжений** | `large_circuits` сетка → `voltage_field` | рельеф U по сетке (z=U, x/y=позиция) — тяжёлый вау-график | средне | **P0** |
| **Тепловая 3D-карта на схеме/плате** | node U → цвет узлов/компонентов | где «горячо» по напряжению/мощности прямо на 3D-геометрии | средне | **P0** |
| **3D-стек осциллограмм** | transient (узлы × время × U) | ленты-волны в глубину: видно все узлы разом | средне | P1 |
| **3D AC/Боде-поверхность** | AC sweep (частота × узел × \|H\|) | АЧХ как рельеф по узлам | средне | P2 |
| **3D Monte-Carlo облако** | MC (разброс) | облако точек исходов в параметрическом пространстве | низко | P2 |

### Реалистичная 3D-плата: графика + разводка + данные (20260621)
«Как в реальности» — отдельный реалистичный 3D-вид платы (это НЕ откаченный PBR-шум на 2D-сцене,
а выделенный 3D-режим, где реализм уместен; уже есть env-map + модели корпусов).
| Слой | Что | Данные | P |
|---|---|---|---|
| **Реалистичная плата** | FR-4 текстура, soldermask, silkscreen, медь, контактные площадки | board/layout | P1 |
| **Реальная разводка (трассы)** | медные дорожки по путям автороутера (A*) в 3D, ширина/слой/via | `pcb_layout`/autorouter | **P0** |
| **Данные на плате** | ток/напряжение/нагрев по трассам и компонентам (цвет/толщина/свечение) | движок (I/U/P) | **P0** |
| **Слои/Stack-up** | multi-layer, переходные отверстия, explode-вид | layout | P1 |
| **DRC на 3D** | нарушения подсвечены прямо на плате (пульс) | `pcb_drc` | P1 |

Принцип реализма: чистая, осмысленная реалистичность (текстуры + env-map уже есть), без шумных
теней/тяжёлых шейдеров. Разводка и данные — приоритетнее косметики (P0): дорожки по реальным
путям + ток/нагрев на них = «настоящая плата, которая работает».

### Анимации (параллельно — поведение, не декор)
- **Морфинг поверхности по времени** — transient playback: 3D-рельеф U «дышит» по кадрам
  (слайдер времени → поверхность/цвета анимируются). Главная связка 3D+анимация.
- **Облёт камеры / орбита** — кинематографичный осмотр поверхности и платы.
- **Плавные цветовые переходы** при смене кадра/режима (lerp цветов, без скачков).
- **Прорисовка** новой поверхности/кривой при пересчёте (build-in анимация).

## Архитектура
- Переиспользуем существующий Three-стек (`scheme-3d.js`) — добавляем слой **data-viz**
  (поверхности/цвета), не плодим второй рендерер.
- Поток: движок → результат (поле/ряд/AC) → нормализация → Three.js mesh (PlaneGeometry с
  per-vertex z+color по полю; для тепло-карты — vertex colors на геометрии платы).
- Цвет: colormap (viridis/turbo) по нормированному U; легенда-шкала.
- Анимация: requestAnimationFrame + lerp по кадрам transient; камера — orbit controls (уже есть).
- Без тяжёлых шейдеров/PBR (прошлый откат) — vertex colors + простой материал.

## Фазы
**Фаза 0 — аудит точки входа (до кода):** как `scheme-3d.js` строит сцену/камеру, куда воткнуть
data-слой; формат результата на фронте (есть ли уже node U в JS после симуляции).

**Фаза 1 — статичные 3D-графики (P0):**
- 3D-поверхность поля сетки (`large_circuits` → field → PlaneGeometry + colormap + легенда).
- Тепло-карта U на 3D-схеме/плате (vertex colors по узлам).

**Фаза 2 — анимация (P0-P1):**
- Морфинг поверхности/цветов по кадрам transient (playback-слайдер).
- Облёт камеры + плавные переходы.

**Фаза 3 — расширение (P1-P2):**
- 3D-стек осциллограмм, AC/Боде-поверхность, MC-облако.

## Принципы
- 3D показывает **данные движков**, не только геометрию.
- Анимация = процесс/физика (морфинг по времени), не украшение.
- Один Three-рендерер (расширяем scheme-3d.js), vertex colors вместо тяжёлых шейдеров.
- Без новых случайных кнопок — в существующий 3D-режим симулятора.

## Рекомендованный старт
**Фаза 1: 3D-поверхность поля напряжений** большой сетки (данные `large_circuits` уже готовы) —
самый яркий вау и прямая связка с индустриальными движками (Xyce считает тяжёлую сетку → 3D-рельеф).
Затем тепло-карта на схеме и морфинг по времени.

---

## WORK FRONT 20260619

Источник: `WORK_FRONT_20260619.md`

# DOLG - фронт работ на 2026-06-19

Единый живой список проектных задач после ревизии кода, документации и последних
коммитов. Дипломная защита, допуск и организационные материалы остаются отдельно
в `docs/DEFENSE_PROJECT.md` и сейчас не управляют очередью разработки.

## Срез проекта

- Рабочее дерево проекта чистое; вне коммита остаётся только локальный файл
  `.claude/settings.local.json`.
- Последние ключевые коммиты:
  - `22c3fb3` - расширены админские действия, добавлен Data Console, профиль
    рабочей среды и локальный PostgreSQL dev-профиль.
  - `afa8c77` - улучшены CAD/simulation workspace.
  - `14fc898` - связан маршрут simulation -> PCB -> 3D.
- Django ORM использует SQL всегда; локально по умолчанию SQLite, PostgreSQL
  включается через `DATABASE_URL`. Для dev Postgres добавлены
  `scripts/postgres_dev.ps1` и `deploy/docker-compose.postgres-dev.yml`.
- Server engine gateway уже имеет каталог движков, API `/api/sim/server-engines/`,
  `/api/sim/jobs/`, модель `EngineJob`, первый server-side router
  `dolg-engine-router`, локальный worker `dolg-numpy-mna` и VS Code tasks
  `Engine worker: once/watch`.
- Внешние SPICE/моделирующие движки пока adapter-ready: Xyce primary-candidate,
  PySpice bridge, GnuCap/OpenModelica/Sigrok и остальные ждут Docker/worker
  контура.
- Админка получила больше контроля: bulk-действия по проектам, jobs, reviews,
  товарам, заказам, модерации; Data Console даёт read-only обзор БД, моделей,
  таблиц, FileField и media.
- Профиль пользователя теперь хранит настройки рабочей среды: density, layout,
  AI backend, preferred sim engine, render mode, animations/reduced motion,
  advanced tools.
- `simulation.html` остаётся самым тяжёлым местом: около 982 KB. `cad.html` -
  около 315 KB. Это главный риск для будущих UX-правок.
- Static source of truth для симулятора сейчас находится в `shop/static/simulation`
  и `shop/static/lib`, хотя часть документации ещё говорит просто
  `static/simulation`.

## Проверки на момент ревизии

- `ruff check Dolg_APP accounts shop orders moderation` - OK.
- `manage.py check` - OK, но холодный запуск занял около 159 секунд.
- `manage.py makemigrations --check --dry-run` - `No changes detected`, но занял
  около 193 секунд.
- `scripts/profile_django_checks.py`:
  - `django.setup`: 167.0 s.
  - `check_url_namespaces_unique`: 52.1 s.
  - `Dolg_APP.checks.check_multi_line_django_comments`: 12.7 s.
  - `check_templates`: 2.4 s.

Вывод: функционально проект живой, но dev-loop уже слишком тяжёлый. Ускорение
старта теперь P0, потому что оно влияет на каждую следующую задачу. После
повторяющихся системных прерываний, таймаутов и перегруза памяти/процессора
стабильность рабочей машины поднимается выше P0.

## P-1 - аварийная стабилизация системы

Это приоритет выше любых продуктовых задач. Если память, CPU, диск, VS Code,
Docker/WSL, Python, Node или фоновые службы забивают машину так, что команды
зависают и работа прерывается, все P0/P1 задачи временно считаются
заблокированными.

1. Снять честный baseline нагрузки.
   - Зафиксировать RAM/CPU/Disk usage, top processes, количество Python/Node/Git
     процессов, состояние Docker Desktop/WSL, VS Code extension host и фоновых
     watchers.
   - Отдельно проверить тяжёлые процессы: Docker Desktop backend, WSL, VS Code,
     language servers, antivirus/indexer, npm/vite watchers, Django/test runs.
   - Сохранять снимки в `logs/`, чтобы видеть не ощущения, а конкретные причины.

2. Ввести "тихий режим разработки".
   - Перед тяжёлыми задачами останавливать Docker Desktop, лишние dev servers,
     Node watchers, старые Python/test processes и зависшие Git/pre-commit
     процессы.
   - Запускать проверки последовательно и точечно, пока машина не стабилизирована.
   - Для VS Code держать минимальный профиль расширений: Python/Pylance, Ruff,
     Django/templates, SQL, Docker/K8s только когда реально нужен этот слой.

3. Добавить системные helper-скрипты.
   - `scripts/diagnose_system_load.ps1`: top CPU/RAM/Disk processes, свободная RAM,
     процессы Python/Node/Git/Docker/WSL/VS Code, краткий verdict.
   - `scripts/stop_heavy_dev_services.ps1`: мягко останавливает только dev-heavy
     процессы, которые безопасно завершать; без удаления данных и без reset.
   - VS Code task `System: diagnose load`, чтобы проверка была одним действием.

4. Радикально снизить нагрузку проекта.
   - Сначала ускорить `django.setup` и `manage.py check`, потому что они сейчас
     сами держат машину занятой минутами.
   - Разобрать тяжелые imports/URLConf до того, как снова запускать широкие тесты,
     Docker, K8s или Playwright.
   - Не запускать полный `pytest`, frontend build и Docker одновременно.

5. Критерий выхода из P-1.
   - `git status`, `ruff check` по изменённым файлам и лёгкие Django-команды
     проходят без зависаний.
   - После закрытия тяжёлых фоновых процессов остаётся заметный запас RAM/CPU.
   - Новые задачи снова можно делать без постоянных таймаутов и ручных рестартов.

## P0 - ближайший фронт после стабилизации системы

1. Ускорить Django/dev-loop.
   - Профилировать `django.setup`, а не только checks: найти тяжёлые imports в
     `views.py`, `admin.py`, URLConf, optional integrations и ML/scientific stack.
   - Вынести тяжёлые импорты из URL-level import path в lazy helpers.
   - Оптимизировать или сделать opt-in проверку `check_multi_line_django_comments`,
     чтобы она не сканировала проект на каждом обычном `manage.py check`.
   - Проверить, почему `check_url_namespaces_unique` занимает 52 s: вероятно,
     слишком тяжёлый URLConf из-за импортов views/templates.
   - Цель: `manage.py check` до 20-30 секунд на текущей машине, затем ниже.

2. [x] Сделать быстрый asset-smoke для simulation/CAD.
   - Добавлен `Dolg_APP/tests_tool_asset_smoke.py`: `/simulation/` и `/cad/`
     рендерятся через Django test client без Playwright-heavy прогона.
   - Smoke проверяет HTML static refs, `shop/static/simulation/*`,
     `shop/static/lib/*`, `shop/static/ai/*`, worker/wasm assets, базовые DOM
     markers и API `/api/sim/server-engines/`.
   - Источник static зафиксирован как `shop/static/simulation` и
     `shop/static/lib`; missing static теперь ловится до ручной проверки
     браузером.

3. Начать декомпозицию `simulation.html` без большого переписывания.
   - [x] Вынести один самодостаточный блок: server-engine UI render helpers
     переехали в `shop/static/simulation/server-engine-ui.js`.
   - [x] Оставить обратную совместимость через `window.*` namespace и
     существующие inline handlers: старые функции в `simulation.html` остались
     адаптерами вокруг `window.DolgServerEngineUI`.
   - [x] Добавить минимум coverage на вынесенный контракт:
     `Dolg_APP/tests_tool_asset_smoke.py` гоняет Node VM contract smoke.
   - Не делать полную TS-миграцию одним прыжком.

4. Проверить Docker/PostgreSQL после стабилизации dev-loop.
   - Запустить `powershell -ExecutionPolicy Bypass -File scripts/postgres_dev.ps1 up`.
   - Получить `DATABASE_URL`, применить миграции, открыть Data Console на Postgres.
   - Если Docker снова зависает, фиксировать точный статус в `logs/` и продолжать
     без него через SQLite/local worker.

5. Обновить API/docs по факту новых функций.
   - `docs/API.md`: server engine jobs, Data Console/staff ops, profile workspace
     settings, local Postgres dev profile.
   - README: заменить устаревшие ссылки на новый фронт и уточнить static paths.
   - `docs/TESTS_AND_REPORTS.md`: добавить свежий срез проверок и заметку о
     медленном старте.

## P1 - продуктовый слой, который можно делать без Docker

1. [x] CAD/simulation UX polish - Session 6 baseline.
   - Исправлять проблемы интерфейса через маленькие, проверяемые блоки:
     overflow, панели, пустые состояния, ошибки, tooltips, mobile/tablet.
   - Довести настройки профиля до реального влияния на рабочие страницы:
     density/layout/render mode/animations должны менять CAD/simulation UI, а не
     только лежать в `body[data-*]`.
   - Сформировать стабильный contract для будущих приборов: scope, generator,
     multimeter, probes, state badges, reduced motion.
   - [x] Added shared `shop/static/shop/workspace-preferences.{css,js}`.
   - [x] CAD and simulation now consume profile density/layout/render/motion settings through stable body classes and datasets.
   - [x] Added `window.DolgWorkspaceInstrumentContract` for future oscilloscope/generator/multimeter/probe animations.
   - Remaining UX work stays incremental: split the huge templates, then polish specific panels with screenshots.

2. [x] Server engine gateway MVP-2.
   - [x] Добавить нормальный stale/retry flow для `EngineJob`: heartbeat, retry count,
     reason, audit log.
   - [x] Сохранить единый result contract для всех будущих workers:
     `nodes`, `branches`, `waveforms`, `metrics`, `warnings`, `artifacts`.
   - [ ] Подготовить Xyce adapter interface без обязательного Docker runtime:
     command builder, parser contract, fixtures, tests.

3. PCB/3D pipeline.
   - Укрепить one-click route scheme -> PCB -> 3D: понятные состояния, возврат,
     сохранение проекта, ошибки.
   - Расширить PCB DRC: net classes, keep-out zones, pours/via stitching,
     отдельный DRC export artifact.
   - Полировать 3D визуал: soldermask/copper/silkscreen, realistic board,
     стабильное framing на desktop/mobile.

4. [x] Admin/Data Console v2.
   - [x] Добавить безопасные фильтры/поиск по моделям и таблицам.
   - [x] Добавить read-only preview для JSONField/project artifacts.
   - [x] Добавить быстрые ссылки из Data Console в связанные admin changelist/change
      pages.
   - [x] Не превращать Data Console в write-инструмент до отдельного permission audit.

5. [x] Доклад: комплексная защита данных от целевых атак.
   - [x] Не ограничиваться базовыми токенами и "защитой от случайных ошибок".
     Сформировать defense-in-depth доклад по модели целевого атакующего:
     credential stuffing, кража сессии, IDOR/tenant escape, supply-chain,
     SSRF/cloud metadata, вредные ECAD/SPICE/архивы, prompt injection, RCE через
     парсеры/воркеры, exfiltration из БД/media/logs/backups, CI/CD secrets,
     Docker/K8s lateral movement и insider/stolen laptop scenarios.
   - [x] Структура доклада: активы и секреты; модель угроз; текущие защиты в коде;
     gaps; приоритетные меры; сценарии обнаружения и реагирования; что сказать
     комиссии простыми словами.
   - [x] Каркас контроля: OWASP ASVS 5.0 как проверяемые требования,
     OWASP Top 10/Cheat Sheets как карта web/appsec атак, NIST CSF 2.0 как цикл
     Govern/Identify/Protect/Detect/Respond/Recover.
   - [x] Привязать к проекту: `SECURITY.md`, `docs/SECURITY_BACKLOG.md`,
     `ssrf_guard.py`, webhook signatures, 2FA/SSO, RBAC/org isolation,
     `AuditLog`/`ProjectEvent`, CSP split-plan, gitleaks/pre-commit, Docker/K8s
     hardening и future Vault/Postgres/backup encryption.
   - [x] Итоговый формат: один аккуратный раздел/доклад в
     `docs/SECURITY_BACKLOG.md`, без россыпи новых файлов.

## P2 - данные, AI и каталог

1. AI/ML curation.
   - ML curation UI lite: queue, quality flags, promote/exclude, soft-delete.
   - GNN train+bench на уже собранных датасетах.
   - RAG Phase A: расширить TF-IDF/hybrid retrieval на knowledge, expert rules,
     glossary и проекты; pgvector только после стабильного Postgres.

2. Catalog/product data.
   - Проверить текущие `catalog_schema.py`, audit/enrich commands и тесты перед
     новыми изменениями.
   - Дотянуть параметры по категориям до уровня demo-эталона.
   - Уменьшить N+1 в каталоге: prefetch/cache для `parameter_preview`,
     `brand_badge`, `delivery_hint`.
   - Связать project cart с BOM/схемой.

3. RF/front.
   - Если backend scikit-rf уже стабилен, вывести видимый front:
     S-параметры, Smith chart, matching hints.

## Later - крупные слои

- Полная TypeScript/Vite миграция `simulation.html` и `cad.html`.
- CSP без `unsafe-inline`.
- Redis/Celery для PDF, AI async, batch simulation.
- Docker/Kubernetes engine gateway: Xyce, PySpice/ngspice, GnuCap, OpenModelica,
  GNU Radio, Sigrok, OpenROAD/OpenFPGA.
- K8s Deployments/Services/Ingress, resource limits, HPA, Helm/Vault/monitoring.
- Production PCB exports: Gerber, NC drill, PnP, fab notes.
- Full PCB editor: placement, manual routing, pours, hierarchy, buses,
  bidirectional schematic<->PCB sync.
- Mechanical/3D workers: GLB library first, IDF/STEP/CadQuery/OpenCASCADE later.
- pgvector, GraphRAG, reranker, multimodal photo-to-schematic, voice/TTS.

## Рекомендуемый порядок ближайших сессий

0. Сессия 0: P-1/P0 стабилизация закрыта до безопасного минимума:
   лишние dev-процессы вынесены в helper-скрипты, Django URLConf переведены
   на lazy imports, HTML-check стал opt-in, VS Code Python tasks получили
   быстрые CLI env-флаги. Текущий ориентир: `django.setup` около 8 секунд,
   `manage.py check` около 3-4 секунд в fast-режиме.
1. Сессия 1: закрыта - asset-smoke `/simulation/` и `/cad/` добавлен в
   `Dolg_APP/tests_tool_asset_smoke.py`; verified ruff + focused pytest.
2. Сессия 2: закрыта - первый малый вынос из `simulation.html` сделан:
   `server-engine-ui.js` в `shop/static/simulation`, сохранён `window.*`
   контракт, добавлен focused Node VM smoke.
3. Сессия 3: закрыта - добавлен первый реальный server-side engine
   `dolg-engine-router`, который уже проходит через `EngineJob` и локальный
   worker, делегируя MVP-маршрут в NumPy MNA. `EngineJob` получил
   stale/retry/heartbeat/reason/audit и единый `dolg.engine.result` contract v1
   для будущих Xyce/PySpice/GnuCap workers.
4. Сессия 4: закрыта - доклад по защите данных от целевых атак добавлен в
   `docs/SECURITY_BACKLOG.md`: OWASP ASVS/Top 10, NIST CSF 2.0, реальные
   активы DOLG, threat model, gaps, меры и текст для защиты.
5. Сессия 5: закрыта - Admin/Data Console v2: безопасный поиск/фильтры,
   JSONField preview, bounded media scan и быстрые ссылки в admin
   changelist/change.
6. Сессия 6: закрыта - CAD/simulation UX baseline применяет профильные
   настройки density/layout/render/animations к рабочим страницам и фиксирует
   contract для будущих приборных анимаций.
7. Сессия 7: in progress - security/token limits. Первый срез закрывает
   password hashing check, cache-backed login lockout и server-side policy для
   organization API tokens. Следом: body-size guard, upload sniff/quarantine,
   AI/CAD import throttles и incident alerts.
8. Сессия 8: Docker/Postgres после защиты/после BIOS virtualization: не
   блокировать продукт, держать SQLite + local worker как основной dev-flow.

## Правила работы

- Не смешивать `.claude/settings.local.json`, secrets, generated env и unrelated
  local files с проектными коммитами.
- Перед крупной правкой UI сначала проверять размеры/границы `simulation.html` и
  `cad.html`, затем двигаться маленькими контрактами.
- Внешние движки запускать через worker/job, не внутри Django request.
- Docker/K8s не должны блокировать работу над продуктом: если daemon снова
  зависает, продолжаем SQLite + local worker и фиксируем blocker отдельно.
- Если система снова уходит в перегруз памяти/CPU и команды начинают зависать,
  возвращаться к P-1 без обсуждения: сначала стабилизировать машину, потом код.
- После завершения этапа кратко переносить итог в `docs/DEVELOPMENT_HISTORY.md`,
  а активные незакрытые задачи держать только здесь.

---

## WOW ANIMATIONS BACKLOG

Источник: `WOW_ANIMATIONS_BACKLOG.md`

# Бэклог: анимации и вау-детали (симулятор + CAD)

Принцип: анимация должна **показывать физику/процесс**, а не быть декором. Прошлый урок —
тяжёлый PBR на 2D-сцене дал шум на FR-4 и был откачен; берём только то, что добавляет ясность
и «вау» одновременно. Ограничение: **не плодим новые кнопки без спроса** — улучшаем
существующие виды.

Связка с движками: compute-бэклог (см. [ENGINES_COMPARISON.md](ENGINES_COMPARISON.md)) даёт
**данные** (токи по рёбрам, напряжения узлов, мощность, поле, волны) → эти анимации их
**визуализируют**. Без новых вычислений нечего анимировать, поэтому идут парой.

## Симулятор

| Идея | Что показывает | Нужные данные (движок) | Вес | P |
|---|---|---|---|---|
| **Анимированный ток по проводам** | направление+величина тока (бегущие точки/штрихи, скорость ∝ I) | branch currents (DC/tran) | средне | **P0** |
| **Тепловая карта напряжений** | цвет узлов/проводов по потенциалу, live | node voltages | низко | **P0** |
| **Живая отрисовка осциллограммы** | перо «рисует» кривую (а не мгновенный график) | tran waveforms | низко | P1 |
| **Свечение активных компонентов** | LED светится, источник пульсирует, нагрев краснеет | DC op-point + power/элемент | средне | P1 |
| **Playback переходного** | слайдер времени → вся схема анимирует U/I по кадрам | tran (time series) | средне | P1 |
| **3D-поверхность поля** (power-grid) | сетка N×N → 3D-рельеф напряжений, морфит по времени/свипу | large_circuits + tran/sweep | высоко | P1 |
| **Tween значений** | числа результата плавно «доезжают» (counters) | любые | низко | P0 |
| **Спарк/искра на отказе** | КЗ → искра, перегруз → дымок (ERC/DRC-триггер) | fault/derating findings | средне | P2 |
| **Боде-свип анимацией** | АЧХ «вырастает» по мере свипа частоты | AC (mag/phase) | низко | P2 |
| **Индикатор движка** | при тяжёлом Xyce — «считаю» прогресс/пульс | job status | низко | P1 |

## CAD

| Идея | Что показывает | Вес | P |
|---|---|---|---|
| **Анимация трассировки (A*)** | путь дорожки прорисовывается по мере поиска | средне | **P0** |
| **Плавная установка компонента** | drop + easing + «щелчок» снапа | низко | **P0** |
| **3D-облёт платы** | орбита/пролёт камеры по PCB в 3D | высоко | P1 |
| **Explode-вид слоёв** | слои PCB разъезжаются в 3D | средне | P1 |
| **Заливка полигона земли** | copper pour заливается анимированно | низко | P2 |
| **Пульс DRC-нарушений** | нарушения мигают/светятся, привлекая внимание | низко | **P0** |
| **Хайлайт пина/цепи на hover** | подсветка связанной цепи + tooltip | низко | P1 |
| **Плавные transform** | rotate/move/scale с easing (не рывками) | низко | P1 |
| **Снап-индикаторы** | анимированная привязка к сетке/объекту | низко | P1 |

## Общие (обе среды)
- **Easing/spring-переходы** вместо мгновенных скачков (открытие панелей, смена режимов).
- **Cross-highlight схема↔PCB↔3D** уже есть — усилить плавной подсветкой.
- **Micro-feedback:** мягкие тени фокуса, плавные hover, прогресс вместо «зависа».

## Ресёрч вау-приёмов (20260621)

Из обзора 3D-симуляторов (CircuiTry3D, Falstad, VR-EDA):
- **Live W.I.R.E.-показания** — Watts/I/R/V обновляются «каждый тик» прямо на элементе/в HUD.
  Дёшево и эффектно; данные у нас есть (DC/tran). **(P0-кандидат)**
- **Вращаемая 3D-поверхность поля** — смотришь рельеф распределения и крутишь в реальном времени
  (подтверждает наш `DolgSurface3D`). Surface current/voltage visualization — «интуитивно понятно».
- **VR-режим** распределения напряжения/тока — далёкий, **post-defense** (WebXR поверх Three).
- Токи-точки (Falstad) — у нас **отказ** (стрелки достаточно, см. выше).

## Рекомендация (порядок)
1. **P0 быстрые победы:** ток по проводам + тепловая карта (симулятор), пульс DRC + плавная
   установка (CAD), tween значений. Дёшево, заметно, не требуют новых кнопок.
2. **3D-поверхность поля** (power-grid) — главный вау под защиту, стыкуется с Xyce.
3. **3D-облёт платы** + playback переходного — кинематографичность.

Реализация: предпочтительно CSS/Canvas/requestAnimationFrame для 2D (легко, без либ); для 3D —
существующий three-стек (scheme-3d.js). Тяжёлые шейдеры/PBR — НЕ тащим (прошлый откат).

---

## YC DEPLOY

Источник: `YC_DEPLOY.md`

# DOLG на Яндекс Compute Cloud — пошаговая инструкция

2026-06-01 — production VM deployment для дипломной защиты.

## Что получишь в итоге

- Публичный URL `http://<VM-IP>/` (или `https://<your-domain>/` если есть)
- Django + Postgres + nginx в Docker
- Auto-restart при перезагрузке VM (systemd)
- 60 дней триал-кредитов от Яндекса (~4000₽)
- После триала — ~600-1500₽/мес (можно отключить)

## Стоимость

| Конфигурация | Цена | Подходит для |
|---|---|---|
| 2 vCPU / 2 GB RAM / 20 GB SSD | ~600₽/мес | защита диплома (минимум) |
| 2 vCPU / 4 GB RAM / 30 GB SSD | ~1100₽/мес | комфортно с playwright |
| Прерываемая (preemptible) | -70% | НЕ для prod (VM выключается раз в 24ч) |

Триал даёт 4000₽ грантов на 60 дней — хватит на 4-6 месяцев работы базовой конфигурации.

---

## Шаг 1. Аккаунт Яндекса (5 мин)

1. https://yandex.cloud → Войти/Регистрация
2. Логин через ЯндексID (без отдельной почты-верификации, если у тебя уже есть Яндекс-почта)
3. Принять условия → **Активировать триальный период**:
   - Привязать карту (любая дебетовая, **списания не будет** в триале)
   - Получишь 4000₽ грантов на 60 дней

## Шаг 2. Создать SSH ключ (1 мин, на твоём Windows)

```cmd
ssh-keygen -t ed25519 -C "dolg-yc"
```

Жми Enter три раза (default путь, без пароля).

Скопируй **публичный** ключ — пригодится:
```cmd
type %USERPROFILE%\.ssh\id_ed25519.pub
```

## Шаг 3. Создать VM (3 мин)

1. https://console.cloud.yandex.ru → **Compute Cloud** → **Виртуальные машины** → **Создать ВМ**
2. **Имя:** `dolg-prod`
3. **Зона доступности:** любая (`ru-central1-a` обычно дешевле)
4. **Образ:** Ubuntu 22.04 LTS
5. **Вычислительные ресурсы:**
   - Платформа: Intel Cascade Lake
   - vCPU: **2**, гарантированная доля **100%**
   - RAM: **2 ГБ** (или 4, если хочешь playwright)
6. **Хранилище:** 20 ГБ SSD (network-ssd)
7. **Сеть:**
   - Подсеть: default
   - Публичный IP: **Автоматически** (зарезервированный лучше платный)
8. **Доступ:**
   - Логин: `ubuntu`
   - SSH-ключ: вставь содержимое `id_ed25519.pub` из Шага 2
9. **Создать ВМ** → 30 сек ждёшь → копируешь публичный IP

## Шаг 4. Подключиться по SSH (10 сек)

```cmd
ssh ubuntu@<VM-PUBLIC-IP>
```

Принять fingerprint (yes), готово.

## Шаг 5. Запустить bootstrap (5-10 мин на установку Docker и зависимостей)

В SSH-сессии VM выполни:

```bash
curl -fsSL https://raw.githubusercontent.com/zlodey2077/Dolg/main/deploy/yc-bootstrap.sh -o bootstrap.sh
chmod +x bootstrap.sh
./bootstrap.sh
```

Скрипт сам:
- Установит Docker + Compose + Git + UFW + Certbot
- Откроет порты 22, 80, 443
- Клонирует репо в `/opt/dolg/`
- Сгенерирует `.env` со случайными `SECRET_KEY` и паролем Postgres
- Запустит `docker compose up` (~5 мин на сборку образа)
- Создаст systemd unit `dolg.service` для auto-restart

### Если нужно указать домен заранее

```bash
DOMAIN=mydolg.example.com ./bootstrap.sh
```

## Шаг 6. Проверить что работает

```bash
docker ps
# Должно быть 3 контейнера: dolg_db, dolg_web, dolg_nginx

curl -i http://localhost/
# Должно вернуть 200 OK + HTML с DOLG

docker logs dolg_web --tail 50
# Логи Django
```

На своём компе в браузере открой: **http://<VM-PUBLIC-IP>/**

## Шаг 7. Дополнить .env секретами

```bash
cd /opt/dolg
nano .env
```

Добавь свои значения (если нужны):
- `HF_TOKEN` — для загрузки моделей с HuggingFace
- `STRIPE_PUBLIC_KEY` / `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET`
- `ANTHROPIC_API_KEY` — для AI чата
- `SENTRY_DSN` — для error tracking

После изменений:
```bash
sudo systemctl restart dolg.service
# или
sudo docker compose -f deploy/docker-compose.yml --env-file .env up -d
```

## Шаг 8. Создать superuser

```bash
sudo docker compose -f /opt/dolg/deploy/docker-compose.yml --env-file /opt/dolg/.env exec web python manage.py createsuperuser
```

Зайти в админку: **http://<VM-PUBLIC-IP>/admin/**

---

## Шаг 9 (опционально). Свой домен + HTTPS (15 мин)

### 9.1. Купить домен

- https://timeweb.com (от 199₽/год для .ru)
- https://reg.ru
- Cloudflare Registrar (без накруток)

### 9.2. Привязать к VM

В DNS-настройках домена:
- A-запись `@` → `<VM-PUBLIC-IP>`
- A-запись `www` → `<VM-PUBLIC-IP>`

Подождать 5-30 мин пока DNS прокатится.

### 9.3. SSL через Let's Encrypt

```bash
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com \
    --non-interactive --agree-tos -m your-email@mail.ru
```

Certbot автоматически перенастроит nginx, поставит cron для авто-обновления сертификата.

### 9.4. Обновить ALLOWED_HOSTS

```bash
nano /opt/dolg/.env
# ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com,<VM-IP>,localhost
# CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
sudo systemctl restart dolg.service
```

---

## Обновление кода после push в GitHub

```bash
ssh ubuntu@<VM-IP>
cd /opt/dolg
./deploy/yc-update.sh
```

Сам сделает:
- `git pull`
- rebuild docker image
- run migrations
- zero-downtime restart web-контейнера

## Логи и мониторинг

```bash
# Все логи web
docker logs dolg_web -f

# Логи только за последний час
docker logs dolg_web --since 1h

# Логи nginx
docker logs dolg_nginx -f

# Использование ресурсов
htop  # CPU/RAM
df -h  # диск
docker stats  # по контейнерам
```

## Backup БД (раз в день — рекомендуется)

```bash
crontab -e
# Добавить строку:
0 3 * * * docker exec dolg_db pg_dump -U dolg dolg | gzip > /home/ubuntu/backup-$(date +\%Y\%m\%d).sql.gz
```

---

## Что делать после защиты

1. Если деньги триала ещё есть — оставь VM работать
2. После триала Яндекс начнёт списывать (предупредит за 7 дней)
3. **Чтобы не платить:**
   - Выключи VM (Console → ВМ → Остановить) — диск всё равно тарифицируется ~50₽/мес
   - Удали VM полностью + диск, GitHub + локальный snapshot всё сохранят

---

## Troubleshooting

### `docker compose` падает на сборке
RAM 2GB мало — VM может OOM. Увеличь до 4GB в Console → ВМ → **Изменить конфигурацию**.

### 502 Bad Gateway в браузере
```bash
docker logs dolg_web --tail 100
# Чаще всего: ALLOWED_HOSTS не включает IP VM. Поправь .env и restart.
```

### Postgres не стартует
```bash
docker logs dolg_db --tail 50
# Возможно неправильный пароль в .env. Удали volume и пересоздай:
docker compose down -v  # ОСТОРОЖНО — удаляет БД!
docker compose up -d
```

### Хочу удалить всё и начать заново
```bash
cd /opt/dolg
sudo systemctl stop dolg
sudo docker compose -f deploy/docker-compose.yml --env-file .env down -v
sudo rm -rf /opt/dolg
./bootstrap.sh  # из home directory
```

---

## Связано

- [deploy/yc-bootstrap.sh](../deploy/yc-bootstrap.sh) — установочный скрипт
- [deploy/yc-update.sh](../deploy/yc-update.sh) — скрипт обновления
- [deploy/docker-compose.yml](../deploy/docker-compose.yml) — production stack
- [deploy/Dockerfile](../deploy/Dockerfile) — Django образ
- [docs/DEPLOY.md](DEPLOY.md) — общая стратегия бэкапов
