# DOLG Architecture

Высокоуровневая карта системы. Подробности по конкретным модулям — в их
исходниках (см. ссылки в конце).

## Topology

```
                    ┌────────────────────────────────┐
                    │   Browser (Chrome / Firefox)   │
                    │  • simulation.html (~7700 LOC) │
                    │  • Pixi.js + Canvas2D рендер   │
                    │  • Three.js 3D-viewer          │
                    │  • ngspice.wasm Worker         │
                    └──────────────┬─────────────────┘
                                   │ HTTPS
                                   ▼
                    ┌────────────────────────────────┐
                    │     ngrok tunnel / nginx       │
                    │  proxy_pass → 127.0.0.1:8000   │
                    │  + статика /static/, /media/   │
                    └──────────────┬─────────────────┘
                                   │ HTTP X-Forwarded-Proto: https
                                   ▼
                    ┌────────────────────────────────┐
                    │  Django (gunicorn 4 workers)   │
                    │  ┌──────────┬───────────────┐  │
                    │  │ shop     │ Dolg_APP      │  │
                    │  │ accounts │ orders        │  │
                    │  │ knowledge│               │  │
                    │  └──────────┴───────────────┘  │
                    └─────┬───────────────────┬──────┘
                          │                   │
                          ▼                   ▼
                ┌───────────────┐   ┌────────────────────┐
                │  PostgreSQL   │   │  Local AI runtime  │
                │  (data + JSON │   │  Ollama + PyTorch  │
                │   schemes)    │   │  + rule fallback   │
                └───────────────┘   └────────────────────┘
```

## Apps & responsibilities

| App | Где | Что отвечает |
|---|---|---|
| **shop** | [`shop/`](../shop/) | Каталог компонентов, корзина, поиск, breadcrumbs, related |
| **accounts** | [`accounts/`](../accounts/) | Регистрация, login, email verify, профиль, адреса |
| **orders** | [`orders/`](../orders/) | Оформление заказа, статусы, история, доставка |
| **knowledge** | [`knowledge/`](../knowledge/) | Статьи-туториалы по электронике, привязка к товарам |
| **Dolg_APP** | [`Dolg_APP/`](../Dolg_APP/) | **Ядро инструментов:** симулятор + CAD + 3D + AI + PCB + share-link |

### Dolg_APP — глубже
- [`views.py`](../Dolg_APP/views.py): /projects/, /tools/cad/, /tools/simulation/, /healthz/, /s/<token>/, AI-chat
- [`ai_assistant.py`](../Dolg_APP/ai_assistant.py): Claude API клиент с prompt-caching, 3 агента (recommend/explain/replace)
- [`services/project_review.py`](../Dolg_APP/services/project_review.py): Engineering Review core, DRC/ERC aggregation, BOM risk, derating, fault library, `Design Health Score`
- [`services/review_visualization.py`](../Dolg_APP/services/review_visualization.py): JSON-payload for the Engineering Review 3D analysis map (`score`, DRC/ERC, BOM, derating, measurements, CAD/ERC findings)
- [`services/review_i18n.py`](../Dolg_APP/services/review_i18n.py): Russian user-facing translation layer for schematic checks, fault scenarios, expert findings, review UI/PDF and self-hosted AI replies
- [`services/schematic_graph.py`](../Dolg_APP/services/schematic_graph.py): NetworkX topology analysis for connectivity, floating nodes, paths to GND, cycles and reusable review/AI/learning metrics
- [`services/cad_import.py`](../Dolg_APP/services/cad_import.py): LTspice/SPICE and KiCad subset import into internal `scheme_data`
- [`services/expert_rules.py`](../Dolg_APP/services/expert_rules.py) + [`expert_rules/default_rules.json`](../Dolg_APP/expert_rules/default_rules.json): expert-first rule packs with `jsonschema` validation, `rule-engine` predicates, evidence and recommendations
- [`services/engineering_units.py`](../Dolg_APP/services/engineering_units.py): Pint-backed unit parsing for lab/review/learning values and engineering suffixes
- [`services/constraint_solver.py`](../Dolg_APP/services/constraint_solver.py): Z3 constraint scenarios for LED/divider/RC/NE555/regulator/thermal margin
- [`services/cad_parsers.py`](../Dolg_APP/services/cad_parsers.py): Lark grammar layer for SPICE/LTspice subset before normalization into `scheme_data`
- [`services/risk_scoring.py`](../Dolg_APP/services/risk_scoring.py): scikit-fuzzy project risk score used by review and assistant explanations
- [`services/rule_ai.py`](../Dolg_APP/services/rule_ai.py): self-hosted rule-based assistant that explains project issues from review/scheme/BOM data
- [`services/simulation_analysis.py`](../Dolg_APP/services/simulation_analysis.py): NumPy/SciPy/Matplotlib/Pandas helpers for FFT, Bode plot, Monte Carlo tolerance, THD/SINAD/ENOB signal quality, parameter sweep, DC fallback and run statistics
- [`pcb_layout.py`](../Dolg_APP/pcb_layout.py): editor px → PCB mm, Gerber RS-274X, Excellon NC drill
- [`models.py`](../Dolg_APP/models.py): SchematicProject, ProjectVersion, SimulationRun, ProjectMeasurement, ProjectReview

## Data flow: User saves a scheme

```
User кликает 💾 Сохранить
       │
       ▼
simulation.html: buildSchemeData() — собирает components+connections
       │
       ▼
fetch POST /projects/api/<id>/save-scheme/ + X-CSRFToken
       │
       ▼
Dolg_APP.views.api_project_save_scheme (login_required)
       │
       ▼
SchematicProject.objects.filter(pk=id, user=request.user).update(
    scheme_data={...},
    updated_at=now()
)
       │
       ▼
JsonResponse({ok: True})
       │
       ▼
client: markSchemeSaved() → badge «✓ сохранено только что»
```

## Data flow: User runs SPICE simulation

```
User кликает ▶️ Запустить
       │
       ▼
simulation.html: buildElementNetlist() — собирает .cir
       │
       ▼
Web Worker (ngspice.wasm), либо fallback в JS-MNA
       │
       ▼
Результат: {voltages: {...}, currents: {...}, sweep: [...]}
       │
       ├──> рендер на canvas через drawCanvas() + colored wires
       │
       └──> POST /projects/api/<id>/simulations/  (опционально, для истории)
                  │
                  ▼
            SimulationRun.objects.create(...)
```

## Data flow: Pro numerical analytics

```
User запускает осциллограф/AC/Monte Carlo/Signal quality/Parameter sweep
       │
       ▼
fetch POST /simulation/api/pro/fft|bode|monte-carlo|signal-quality|parameter-sweep/
       │
       ▼
Dolg_APP.views.api_simulation_* (login_required + Pro gate + quota)
       │
       ▼
Dolg_APP.services.simulation_analysis
   • scipy.fft.rfft для FFT
   • scipy.signal / direct AC points для Bode
   • numpy random для tolerance Monte Carlo
   • FFT harmonics for THD/SINAD/ENOB signal quality
   • numpy log/linear axis for what-if parameter sweep
   • matplotlib Agg -> SVG
       │
       ▼
JsonResponse({ok, metrics, points, svg})
```

Если ngspice/JS fallback не справился с простой DC R/V/GND-схемой, UI/API может вызвать
`POST /simulation/api/fallback-solve/`: схема нормализуется до узлов, NumPy решает MNA-матрицу,
а ответ возвращает `nodeVoltages` и предупреждения.

## Data flow: AI-chat (если ANTHROPIC_API_KEY задан)

```
User кликает 🤖 и пишет вопрос
       │
       ▼
fetch POST /api/ai/chat/ {prompt, agent: 'recommend'}
       │
       ▼
Dolg_APP.ai_assistant.chat(prompt, agent='recommend')
   • build_system_blocks() — кэшируемые префиксы (cache_control: ephemeral)
   • build_catalog_snapshot() — топ-N товаров из БД (LocMem cache 60 сек)
   • local runtime → Ollama / PyTorch / rule-based fallback
       │
       ▼
JsonResponse({reply: "..."})
       │
       ▼
client: рендер в chat-bubble
```

## Frontend bundle

| Где | Что | Размер |
|---|---|---|
| `shop/static/simulation/scheme-3d.js` | Three.js 3D viewer, PCB-style mesh | ~30 KB |
| `shop/static/review/review-3d.js` | Three.js Engineering Review 3D analysis map with WebGL fallback | ~9 KB |
| `shop/static/simulation/scheme-netlist.js` | SPICE netlist builder, JS-fallback solver | ~15 KB |
| `shop/static/simulation/scheme-lab.js` | Virtual lab (мультиметр, осциллограф) | ~12 KB |
| `shop/static/simulation/ngspice.wasm` | WebAssembly ngspice (≈2 МБ) | 2 МБ |
| `shop/static/lib/dolg/` | Vite/TS bundle (опц.) — proof-of-concept TS-миграции | ~5 КБ |
| `Dolg_APP/templates/tools/simulation.html` | inline JS симулятора (~7700 LOC) | 250 КБ |

## Storage & persistence

| Что | Где | Backup |
|---|---|---|
| User accounts, projects, orders | PostgreSQL (volume `db_data`) | `scripts/backup_db.sh` daily → `./backups/` |
| Product images, avatars | `/media/` (host bind-mount) | rsync raw files |
| Static assets (после `collectstatic`) | `/staticfiles/` | regenerable из исходников |
| Browser autosave (per-user, локально) | `localStorage['dolg.sim.autosave']` | none — user-side |
| Чужие схемы (share-link) | те же `SchematicProject` rows, `share_token != ''` | через DB backup |

## External services

| Сервис | Required? | Что без него |
|---|---|---|
| **PostgreSQL** | Да для prod | dev — SQLite-фолбэк |
| **Ollama / local PyTorch** | Нет | AI-ассистент уходит в rule-based fallback |
| **ngrok tunnel** | Опц. для публичного доступа | работает только localhost |
| **Sentry** | Нет | ошибки только в console-logs |
| **Stripe** | Заглушка | demo-mode payments |
| **SMTP** | Нет (есть console-backend) | email-verify письма не уходят |

Локальные научные зависимости (`numpy`, `scipy`, `matplotlib`, `pandas`, `python-engineering`) не являются внешними сервисами: они установлены из `requirements.txt` и используются только внутри Django service-layer.

## Settings hierarchy

```
Dolg_PR/settings.py           ← база (всегда)
   │
   └── Dolg_PR/settings_prod.py   ← production: from .settings import *
   └── Dolg_PR/settings_dev.py    ← development (если есть)
   └── Dolg_PR/settings_test.py   ← CI (если есть)
```

Активный модуль — через `DJANGO_SETTINGS_MODULE` env. Production:
```
DJANGO_SETTINGS_MODULE=Dolg_PR.settings_prod
```

## Health-check & monitoring

| Endpoint | Что | Зависимости |
|---|---|---|
| `/healthz/` | k8s liveness/readiness, 200 OK | none (не лезет в БД) |
| `/admin/` | Django admin | auth + БД |
| `/api/projects/` | REST API проектов | auth + БД |

См. [RUNBOOK.md](RUNBOOK.md) для процедур восстановления.

## Deployment

- **Dev:** `python manage.py runserver` + SQLite (см. [LOCAL_SETUP.md](LOCAL_SETUP.md))
- **Prod-Docker:** `docker compose up -d` → 3 контейнера (db, web, nginx)
- **Public demo:** `start_public.bat` → `start_public_server.py` → ngrok tunnel

См. [DEPLOY.md](DEPLOY.md) для подробностей.

## Tests

| Где | Сколько | Что покрыто |
|---|---|---|
| `shop/tests.py` | 51 | Каталог, корзина, BOM, глобальный поиск по tool topics, оформление, инвентарь |
| `accounts/` | (нет) | — TODO |
| `Dolg_APP/tests.py` | 48 | Healthz, AI-assistant, проекты-ownership, PCB layout, share-token, demo populate, project review/import, Pro simulation analytics, NumPy fallback, signal quality, parameter sweep, Pro toolbar smoke, сохранение Pro-метрик, prod-checks |
| `knowledge/tests.py` | 23 | Энциклопедия, learning grader, инженерная лаборатория, `python-engineering` validation backend |

CI прогоняет всё через `manage.py test`, fail при coverage < 40% (см. [.github/workflows/django.yml](../.github/workflows/django.yml)).
