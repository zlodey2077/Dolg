# DOLG REST API

Минимальная справка по JSON-эндпоинтам. Полные URL-роуты — в [`Dolg_APP/urls.py`](../Dolg_APP/urls.py),
[`shop/urls.py`](../shop/urls.py), [`accounts/urls.py`](../accounts/urls.py).

## Аутентификация

Сессионная (Django session cookie). Все endpoint'ы с `@login_required` без cookie вернут `302 → /accounts/login/?next=<url>`.

CSRF: POST/PUT/DELETE требуют заголовок `X-CSRFToken` из cookie `csrftoken`.

```js
// JS-клиент: токен через document.cookie
function getCsrf() {
    const m = document.cookie.match(/(^| )csrftoken=([^;]+)/);
    return m ? m[2] : '';
}
fetch('/projects/api/...', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
    body: JSON.stringify({...}),
});
```

## Health

### `GET /healthz/`
Liveness probe. Не лезет в БД.

**Response:** `200 OK`, body `ok` (text/plain).

---

## Schematic projects

### `GET /projects/api/`
Список проектов текущего пользователя + публичные demo-проекты.

**Response:**
```json
{
    "projects": [
        {"id": 1, "name": "Делитель", "category": "led",
         "status": "draft", "is_demo": false,
         "updated_at": "2026-05-15T10:00:00Z"},
        ...
    ]
}
```

### `POST /projects/api/create/`
Создать новый проект.

**Request:**
```json
{
    "name": "Усилитель",
    "description": "класс А",
    "category": "audio",
    "status": "draft",
    "scheme_data": {"components": [], "connections": []}
}
```

**Response:** `{"ok": true, "project": {...}}`.

### `POST /projects/api/<id>/update/`
Изменить метаданные (имя, описание, категория, статус).

**Request:** `{"name": "Новое имя"}` (любое подмножество полей).

**Response:** `{"ok": true, "project": {...}}` или `404` если не ваш.

### `POST /projects/api/<id>/save-scheme/`
Перезаписать `scheme_data`.

**Request:**
```json
{
    "scheme_data": {
        "version": 2,
        "components": [{"id": 0, "type": "resistor", "x": 100, ...}, ...],
        "connections": [{"from": {"compId": 0, "portId": "a"}, ...}, ...]
    }
}
```

**Response:** `{"ok": true}`.

### `GET /projects/api/<id>/load-scheme/`
Получить полный `scheme_data` проекта.

**Response:**
```json
{
    "ok": true,
    "project": {"id": 1, "name": "...", ...},
    "scheme_data": {"version": 2, "components": [...], "connections": [...]}
}
```

### `POST /projects/api/<id>/delete/`
Удалить проект.

**Response:** `{"ok": true}`.

### `POST /projects/api/<id>/share/`
Сгенерировать/отозвать share-token для публичного просмотра.

**Response:**
```json
{"ok": true, "share_token": "abc123def456...", "share_url": "/s/abc123def456.../"}
```
или (если уже был) — `{"ok": true, "share_token": "", "share_url": ""}` (отозван).

### `GET /s/<token>/`
Публичный read-only просмотр схемы. Без логина.

**Response:** HTML страница симулятора в shared-режиме.

---

## Simulation runs

### `POST /projects/api/<id>/simulations/`
Сохранить результат запуска SPICE-симуляции в историю.

**Request:**
```json
{
    "analysis_type": "dc",
    "engine": "ngspice.wasm",
    "elapsed_ms": 42,
    "status": "success",
    "netlist": "* DOLG netlist\nV1 1 0 5\n...",
    "result_summary": {"V(1)": 5.0, "I(R1)": 0.001},
    "result_data": {...},
    "warnings": []
}
```

**Response:** `{"ok": true, "run_id": 123}`.

### `GET /projects/api/<id>/simulations/`
История последних 25 запусков.

**Response:**
```json
{
    "ok": true,
    "runs": [
        {"id": 123, "analysis_type": "dc", "elapsed_ms": 42,
         "status": "success", "created_at": "..."},
        ...
    ]
}
```

### `GET /projects/api/<id>/simulation-runs/stats/`
Pandas-агрегация истории симуляций проекта: самые медленные запуски и статистика по типам анализа.

**Response:**
```json
{
    "ok": true,
    "runs_count": 12,
    "slowest_runs": [{"id": 5, "analysis_type": "ac", "elapsed_ms": 120}],
    "by_analysis_type": [{"analysis_type": "dc", "runs": 3, "mean_elapsed_ms": 41.3}],
    "mean_elapsed_ms": 68.5
}
```

---

## Pro simulation analytics

### `POST /simulation/api/pro/fft/`
FFT-спектр осциллографа. Требует логин, Pro/Unlimited и квоту `simulations`.

**Request:**
```json
{"samples": [0, 0.31, 0.59], "sample_rate_hz": 1000, "window": "hann"}
```

**Response:** `{"ok": true, "peak_frequency_hz": 50.0, "points": [...], "svg": "<svg..."}`.

### `POST /simulation/api/pro/bode/`
Bode plot для AC-результатов или расчетного RC low-pass. Требует логин, Pro/Unlimited и квоту `simulations`.

**Request:**
```json
{"kind": "rc_lowpass", "resistance_ohm": 10000, "capacitance_f": 0.0000001}
```

**Response:** `{"ok": true, "cutoff_frequency_hz": 159.0, "magnitude_points": [...], "phase_points": [...], "svg": "<svg..."}`.

### `POST /simulation/api/pro/monte-carlo/`
Monte Carlo tolerance для делителя напряжения или RC cutoff. Требует логин, Pro/Unlimited и квоту `simulations`.

**Request:**
```json
{"kind": "voltage_divider", "vin": 9, "r1_ohm": 1000, "r2_ohm": 2000, "samples": 1000}
```

**Response:** `{"ok": true, "metric": "vout", "mean": 6.0, "p05": 5.8, "p95": 6.2, "svg": "<svg..."}`.

### `POST /simulation/api/pro/signal-quality/`
Signal quality для TRAN-сигналов: fundamental, THD, SINAD, ENOB, crest factor и гармоники. Требует логин, Pro/Unlimited и квоту `simulations`.

**Request:**
```json
{"samples": [0, 1, 0, -1], "sample_rate_hz": 1000, "max_harmonics": 5}
```

**Response:** `{"ok": true, "thd_percent": 2.1, "sinad_db": 56.0, "enob": 9.0, "harmonics": [...], "svg": "<svg..."}`.

### `POST /simulation/api/pro/parameter-sweep/`
What-if/parameter sweep для делителя, RC cutoff, NE555 astable и LED-резистора. Требует логин, Pro/Unlimited и квоту `simulations`.

**Request:**
```json
{"kind": "rc_cutoff", "parameter": "resistance_ohm", "resistance_ohm": 10000, "capacitance_f": 0.0000001, "scale": "log"}
```

**Response:** `{"ok": true, "metric": "cutoff_frequency", "min": 159.0, "max": 15900.0, "points": [...], "svg": "<svg..."}`.

### `POST /simulation/api/fallback-solve/`
Server-side DC fallback для простых R/V/GND-схем. Требует логин и квоту `simulations`, но не требует Pro.

**Request:**
```json
{"scheme_data": {"components": [...], "connections": [...]}}
```

**Response:** `{"ok": true, "engine": "server_side_numpy_mna", "nodeVoltages": {"out": 3.33}}`.

Pro-аналитика в интерфейсе может сохранить ключевой результат как `ProjectMeasurement`
через `POST /projects/api/<id>/measurements/create/`. Для этого передаются `metric`,
`label`, `value`, `unit`, `source` и необязательный JSON `result` с деталями расчета
например `peak_magnitude`, `sample_count`, `p05/p95`, `thd_percent`, `best_point` или `nodeVoltages`.

---

## Engineering protocol

### `POST /api/sim/protocol/`
Генерирует Markdown/PDF-протокол проектирования. Требует логин. Есть два режима:
ручной payload (`scheme_data`, `measurements`, `lab_calcs`, `findings`) и проектный
режим через `project_id`.

В проектном режиме endpoint использует те же правила доступа, что проектные API:
чужой private-проект вернет `404`. Если доступ есть, протокол сам подтягивает
`scheme_data`, последние `SimulationRun`, сохраненные `ProjectMeasurement` и
in-memory Engineering Review findings. Review не сохраняется в БД, чтобы генерация
отчета не засоряла историю проекта.

**Request:**
```json
{
    "project_id": 7,
    "include_dc": true,
    "include_review": true,
    "download": false,
    "format": "json"
}
```

**Response:**
```json
{
    "ok": true,
    "project": {"id": 7, "name": "Review LED"},
    "sections": [
        "Состав схемы",
        "Расчет рабочей точки (DC, MNA)",
        "Запуски симуляции",
        "Измерения",
        "Проверки (DRC / review)",
        "Выводы"
    ],
    "meta": {"section_count": 6, "has_findings": true},
    "markdown": "# Протокол проектирования: Review LED\n..."
}
```

Если `download: true`, ответ возвращается как `text/markdown` с attachment filename
`dolg_protocol_project_<id>.md` для проектного режима или `protocol.md` для ручного.
Если передать `format: "pdf"`, endpoint вернет `application/pdf` с filename
`dolg_protocol_project_<id>.pdf` или `protocol.pdf`.

---

## Server engine catalog

### `GET /api/sim/server-engines/`
Публичный каталог движков для будущего Docker/Kubernetes router-слоя. Логин не
требуется. Опциональный query-параметр `category` фильтрует каталог: `core`,
`spice`, `modeling`, `eda`, `embedded`, `lab`, `radio`, `cv`, `ops`.

**Response:**
```json
{
    "ok": true,
    "categories": [{"key": "spice", "label": "SPICE/схемы"}],
    "engines": [
        {
            "id": "xyce",
            "name": "Xyce",
            "status": "primary-candidate",
            "category": "spice",
            "endpoint": "/engines/xyce/jobs",
            "tags": ["electronics", "spice", "dc", "ac", "transient"]
        }
    ],
    "summary": {
        "total": 21,
        "docker_rest_ready": 4,
        "primary_candidate": "xyce"
    },
    "router_profile": {
        "primary_engine": "xyce",
        "interactive_engine": "dolg-ngspice-wasm",
        "python_bridge": "pyspice"
    }
}
```

### `POST /api/sim/server-engines/recommend/`
Подбирает подходящие движки для текущей схемы по компонентам и тегам. Логин не
требуется; для браузерного POST действует обычный CSRF-заголовок `X-CSRFToken`.

**Request:**
```json
{
    "scheme_data": {"components": [{"type": "resistor"}, {"type": "voltage_source"}]},
    "limit": 5
}
```

**Response:**
```json
{
    "ok": true,
    "engines": [{"id": "xyce", "name": "Xyce", "status": "primary-candidate"}],
    "router_profile": {"primary_engine": "xyce", "python_bridge": "pyspice"}
}
```

Текущий слой является catalog/router-profile API. Реальное выполнение внешних
CLI-движков должно идти через отдельный async job gateway, а не через web request.

### `GET /api/sim/jobs/`
Lists external engine jobs visible to the current user. Requires login.
Optional filters: `engine_id`, `status`, `project_id`.

**Response:**
```json
{
    "ok": true,
    "jobs": [
        {
            "id": 12,
            "engine_id": "xyce",
            "analysis_type": "tran",
            "status": "queued",
            "progress_percent": 0,
            "links": {
                "status": "/api/sim/jobs/12/",
                "result": "/api/sim/jobs/12/result/"
            }
        }
    ]
}
```

### `POST /api/sim/jobs/`
Creates an async external-engine job record. Requires login. This endpoint does
not start a CLI process inside the web request; workers will later consume
`queued` jobs.

**Request:**
```json
{
    "engine_id": "xyce",
    "analysis_type": "tran",
    "project_id": 7,
    "netlist": "* demo\n.tran 1u 1m\n.end",
    "scheme_data": {"components": [], "connections": []},
    "options": {"timeout_s": 30}
}
```

**Response:** HTTP `202 Accepted`
```json
{
    "ok": true,
    "job": {
        "id": 12,
        "engine_id": "xyce",
        "engine_name": "Xyce",
        "status": "queued",
        "input_payload": {
            "engine_endpoint": "/engines/xyce/run",
            "expected_outputs": ["raw/CSV curves", "solver log", "convergence report"],
            "source": "api"
        }
    },
    "router_profile": {"primary_engine": "xyce", "python_bridge": "pyspice"}
}
```

### `GET /api/sim/jobs/<id>/`
Returns job status, input contract and result payload if it already exists.

### `GET /api/sim/jobs/<id>/result/`
Returns HTTP `202` while the job is `queued`/`running`, and HTTP `200` after
`success`. The response shape is stable in both cases: `ok`, `job`, `result`,
`pending`.

Current implementation is a safe gateway plus a local worker. It validates the
engine, persists `EngineJob`, keeps external CLI execution out of Django
requests, and can process `dolg-numpy-mna` jobs through the internal NumPy MNA
adapter.

The simulation UI uses the same contract in the server-engine runner modal:
select `engine_id`/`analysis_type`, submit the current scheme, poll
`queued -> running -> success/error`, and render normalized `nodes`,
`branches`, `metrics` and `warnings`.

Run one local worker pass:
```bash
python manage.py run_engine_worker --once --limit 5
```

Run a local polling worker:
```bash
python manage.py run_engine_worker --limit 5 --sleep 2
```

Default worker mode only claims local adapter jobs (`dolg-numpy-mna`). External
engines such as `xyce`, `pyspice` and `gnucap` remain queued until a dedicated
Docker/CLI worker is started. Local worker results use the shared contract:
`nodes`, `branches`, `waveforms`, `metrics`, `warnings`, `artifacts`.

If a successful local job has `project_id`, the worker also creates a
`SimulationRun` for that project and logs `ProjectEvent(event_type="simulation_run")`.
This keeps browser-driven simulation history and worker-driven server-engine
history in one place.

---

## AI assistant

### `POST /api/ai/chat/`
Отправить сообщение в Claude. Требует логин (rate-limit по сессии).

**Request:**
```json
{
    "prompt": "Подскажи резистор для LED 5В",
    "agent": "recommend"
}
```

**Agents:**
- `recommend` — подбор товаров из каталога DOLG
- `explain` — объяснение схемы / компонента
- `replace` — заменить незакрытый компонент аналогом

**Response (success):**
```json
{"reply": "Для LED 5В с током 20 мА...", "agent": "recommend"}
```

**Response (errors):**
- `503` — `{"error": "AI временно недоступен", "code": "service_unavailable"}` — ключ не задан или API недоступен
- `429` — `{"error": "rate_limit", "retry_after_seconds": 60}` — превышен лимит на пользователя
- `400` — `{"error": "validation", "details": "prompt пустой"}`

---

## PCB

### `GET /projects/<id>/pcb/`
HTML-страница PCB-просмотра.

### `GET /projects/<id>/pcb/gerber/`
Скачать архив с Gerber (top copper) + Excellon NC drill.

**Response:** `application/zip`, attachment `dolg-pcb-<id>.zip` с файлами:
- `top-copper.gbr`
- `drill.drl`

---

## Shop

### `GET /api/products/?q=<query>&category=<slug>&limit=20`
Поиск товаров (для autocomplete и AI-snapshot).

**Response:**
```json
{
    "ok": true,
    "products": [
        {"id": 42, "name": "Резистор 10кОм 0.25Вт",
         "part_number": "MF25-10K", "price": "5.00",
         "stock": 1500, "category": "resistors"},
        ...
    ]
}
```

### `POST /cart/add/<product_id>/`
Добавить в корзину (form-data, не JSON).

**Form:** `quantity=1`.

**Response:** `302 → /cart/` или JSON если `Accept: application/json`.

### `POST /api/cart/add-bom/`
Массовое добавление позиций BOM из схемы.

**Request:**
```json
{"items": [
    {"part_number": "MF25-10K", "qty": 3},
    {"part_number": "LED-RED-5MM", "qty": 1}
]}
```

**Response:** `{"ok": true, "added": 4, "skipped": 0, "errors": []}`.

---

## Accounts

### `POST /accounts/login/`
Login (form, не JSON).

**Form:** `username`, `password`, `next` (опц. — куда вернуть после login).

**Response:** `302 → /` или `302 → <next>` если задан и валиден.

### `POST /accounts/register/`
Регистрация (form). Проверяет AUTH_PASSWORD_VALIDATORS из settings.

### `GET /accounts/verify-email/<token>/`
Подтвердить email по токену из письма (HMAC, TTL 24ч).

### `POST /accounts/resend-verification/`
Перезапросить письмо подтверждения. Rate-limit 5 минут / сессию.

---

## Соглашения

### Формат ошибок
Все API возвращают одинаковую структуру:
```json
{"ok": false, "error": "<human-readable>", "details": "<technical>"}
```
HTTP-коды: `400` для validation, `401` для auth, `403` для permission, `404` для not-found, `429` для rate-limit, `500` для server-error.

### Throttling
- AI-chat: 30 req/час/пользователь
- Save-scheme: 60 req/мин/пользователь (через session-counter)

### Pagination
Где есть списки — параметр `?limit=N&offset=M` (default limit=20, max 100).
В response: `{"items": [...], "total": N, "has_more": true|false}`.

### CORS
Кросс-доменные запросы запрещены — все API только same-origin (через session cookie).

---

## Тестирование API (curl)

```bash
# Авторизация (сохраняем cookies в jar)
curl -c cookies.txt -X POST http://localhost:8000/accounts/login/ \
     -d 'username=admin&password=...'

# Получаем CSRF из cookies
csrf=$(grep csrftoken cookies.txt | awk '{print $7}')

# Создаём проект
curl -b cookies.txt -X POST http://localhost:8000/projects/api/create/ \
     -H "Content-Type: application/json" \
     -H "X-CSRFToken: $csrf" \
     -d '{"name":"Тест","scheme_data":{}}'
```
