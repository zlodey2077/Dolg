# WORKFRONT_20260602_ADMIN_AI_RECHECK: нейронка и админ-панель после перепроверки

Дата: 2026-06-02.

Контекст: пользователь уточнил, что часть ранее предложенного уже реализована, симулятор пока не трогать, а основной фокус перенести на нейронку, датасеты и админ-панель.

## Ограничение итерации

Симулятор в этой итерации не дорабатываем.

Разрешено:

- читать данные симулятора;
- использовать уже сохраненные `scheme_data`;
- использовать результаты review/измерений, если они есть;
- импортировать схемы в проекты и AITrainingExample;
- улучшать админку, ML-датасеты, training pipeline, review snapshots и project data.

Не делаем сейчас:

- правки canvas/worker/ngspice UI;
- изменения AC/DC/TRAN engine;
- новые элементы управления в `simulation.html`;
- переписывание схемного редактора.

## Что уже есть и не нужно делать заново

### ML / нейронка

| Уже есть | Где | Комментарий |
|---|---|---|
| Optional PyTorch backend | `Dolg_APP/ml/neural.py` | Tiny model, teacher baseline, topology/risk/next-component heads, progress callback. |
| AI pipeline | `Dolg_APP/ml/pipeline.py` | `find_analogs`, `detect_anomalies`, `explain_scheme`, `recommend_next_component`; neural backend подключается как deep-hint. |
| AI training service | `Dolg_APP/services/ai_training.py` | Opt-in сбор схем, learning/review/artifact examples, validation, export, similarity, scheme scoring, promotion to projects. |
| Команды датасета | `collect_ai_training_examples`, `collect_good_schemes_for_ai`, `import_external_datasets`, `validate_ai_dataset`, `export_ai_dataset`, `train_tiny_circuit_ai`, `promote_ai_examples_to_projects` | Базовый pipeline уже есть. |
| Staff ML training page | `/staff/ml-training/`, `Dolg_APP/ml_admin_views.py`, `templates/admin/ml_training.html` | Старт тренировки, выбор JSON dataset, include DB, progress polling. |
| Staff dataset quality page | `/staff/ml-dataset/`, `templates/admin/ml_dataset_quality.html` | Сводка датасета, validation errors/warnings, model status. |
| Import progress | `ml_dataset_import_status` | Есть stale detection после 120 секунд и reset. |
| AITrainingExample admin dashboard | `templates/admin/dolg_app/aitrainingexample/change_list.html` | Показывает total/validated/source/topology и warnings/errors. |
| Promotion в проекты | admin actions и `promote_ai_examples_to_projects` | AI-примеры уже могут попадать в `SchematicProject`. |

### Админ-панель

| Уже есть | Где | Комментарий |
|---|---|---|
| Project admin dashboard | `SchematicProjectAdmin.changelist_view` | Считает projects/demo/public/reviews/simulation_runs/measurements. |
| Project-related admin models | `SimulationRunAdmin`, `ProjectMeasurementAdmin`, `ProjectReviewAdmin`, `ProjectEventAdmin` | Списки есть, но нет единого project cockpit. |
| Artifact admin | `EngineeringArtifactAdmin` | Статусы, facts/warnings/errors, actions и создание AI examples из summary. |
| AITrainingExample admin | `AITrainingExampleAdmin` | Validation actions, promote actions, dashboard. |
| Shop admin | `shop/admin.py` | Product data quality summary, datasheet quality filter, custom changelist. |
| Knowledge admin | `knowledge/admin.py` | Articles, materials, learning tracks/lessons/tasks/attempts/progress. |
| Moderation admin | `moderation/admin.py` | Cases/reports/actions/restrictions/rules, bulk hide/restore/reject. |
| Accounts admin | `accounts/admin.py` | Profile customization, `allow_ai_training`, unit system, AI tone. |
| Orders admin | `orders/admin.py` | Order lists, statuses, payment/shipment basics. |

## Что фактически слабое

### 1. Админка фрагментирована

Сейчас есть много списков, но нет единого операционного центра.

Проблема:

- staff видит отдельные модели, но не видит цепочку `проект -> review -> measurements -> artifacts -> AI examples -> training`;
- быстрые действия разбросаны;
- нет общего статуса "что сломано в данных";
- нет очереди задач "что надо обработать сегодня".

### 2. ML job state cache-only

Тренировка и импорт запускаются через `threading` и progress в `cache`.

Что хорошо:

- HTTP-запрос не висит;
- progress polling уже есть;
- есть stale detection и reset;
- есть защита path traversal для dataset path.

Что плохо:

- job history теряется после cache flush/restart;
- нет отдельной модели `MLJob`;
- нет нормального cancel/stop;
- нет перезапуска failed job;
- нет персистентного stdout/stderr;
- сложно отдавать метрики в Grafana;
- поток в web-процессе - временное решение, не полноценная очередь.

### 3. Dataset quality неоднородный

Факты из текущей БД:

- `AITrainingExample`: 72;
- все 72 отмечены `is_validated=True`;
- по `features.evidence_kind`:
  - `learning_task`: 36;
  - `auto_quality_scheme`: 14;
  - `review_rule`: 14;
  - `curated_demo_case`: 8;
- 36 примеров без структурной схемы/graph-ish features.

Вывод:

- для текстового AI и retrieval эти примеры полезны;
- для graph/tiny neural модели их нельзя смешивать со scheme-backed примерами;
- в админке нужно явно показывать `text-only` vs `scheme-backed`.

### 4. Проектные данные не питают нейронку достаточно

Сейчас:

- `SchematicProject`: 28;
- `ProjectReview`: 1;
- `ProjectMeasurement`: 0;
- `SimulationRun`: 0;
- `EngineeringArtifact`: 0.

Вывод:

- нейронка и AI-ассистент уже имеют код, но мало живых проектных фактов;
- следующий шаг не трогает симулятор, но должен создавать review/artifact/project snapshots из уже имеющихся `scheme_data` и импортов.

### 5. Grafana-интеграция не оформлена как источник админ-метрик

Пока по коду есть админские страницы, но нет явного metrics layer:

- dataset import progress;
- training progress;
- validation errors/warnings;
- counts по examples/projects/reviews/artifacts;
- duration импортов/тренировок;
- stale jobs.

Это нужно не только для красоты, а чтобы зависшие импорты были видны сразу.

## Новый фокус итерации

### P0. Admin Cockpit V1

Цель: сделать админку не набором списков, а центром управления данными DOLG.

Добавить страницу:

`/staff/ops/` или кастомный блок на admin index.

Блоки:

1. **Data health**
   - products;
   - projects;
   - reviews;
   - measurements;
   - artifacts;
   - AI examples;
   - comments/moderation cases;
   - subscriptions/orgs.
2. **AI dataset**
   - total examples;
   - validated/unvalidated;
   - scheme-backed/text-only;
   - source coverage;
   - topology balance;
   - quality buckets;
   - last training result.
3. **Jobs**
   - current import;
   - current training;
   - stale flag;
   - last error;
   - reset/retry links.
4. **Project pipeline**
   - projects without review;
   - projects without AI example;
   - projects promoted from AI;
   - demo projects not public/approved.
5. **Moderation**
   - open cases;
   - pending content;
   - active restrictions.

Acceptance:

- staff заходит в одну страницу и видит, что именно пусто/зависло;
- есть ссылки на нужные admin changelists;
- есть быстрые действия: validate dataset, collect good schemes, promote to projects, reset stale job.

### P0. Persistent MLJob model

Цель: заменить cache-only прогресс на историю задач.

Модель:

`MLJob`

Поля:

- `job_type`: `dataset_import`, `training`, `validation`, `export`, `promotion`;
- `status`: `queued`, `running`, `success`, `error`, `cancelled`, `stale`;
- `progress_percent`;
- `processed`, `created`, `updated`, `skipped`;
- `source`;
- `parameters`;
- `result`;
- `stdout_tail`;
- `error`;
- `started_at`, `heartbeat_at`, `finished_at`;
- `created_by`.

Что поменять:

- `ml_admin_views` пишет progress и в cache, и в `MLJob`;
- import/training status endpoints возвращают `job_id`;
- reset помечает job как `cancelled/stale`, а не просто очищает cache;
- в admin появляется история jobs.

Acceptance:

- после restart история задач не исчезает;
- зависшие импорты видны в админке;
- можно доказать на защите, что тяжелые операции контролируются.

### P0. Dataset type split

Цель: не смешивать text-only и scheme-backed examples.

Добавить в `features` стандартизированные поля:

- `dataset_kind`: `scheme_backed`, `text_only`, `artifact_backed`, `review_backed`;
- `scheme_family`;
- `topology_label`;
- `complexity_label`;
- `quality_label`;
- `quality_score`;
- `graph_features_present`;
- `source_ids`;
- `teacher_rules`.

Правила:

- tiny PyTorch training берет только `scheme_backed` или examples с `scheme_data/graph_features`;
- text-only examples остаются для retrieval/answer style/learning explanation;
- admin показывает предупреждение, если training выбран на смешанном корпусе.

Acceptance:

- 36 text-only examples перестают считаться проблемой для текстового AI, но исключаются из graph training;
- dataset quality dashboard явно показывает баланс.

### P0. Dataset import hardening

Цель: добить зависания импортов.

Уже есть:

- `--download-deadline`;
- `--local-only`;
- progress cache;
- stale detection;
- reset incomplete HF files.

Добавить:

- `MLJob.heartbeat_at`;
- stage-level timeout: `download`, `parse`, `persist`, `promote`;
- skip shard on deadline instead of hanging whole import;
- retry count per shard;
- output warning `network_unavailable` вместо молчаливого ожидания;
- local-cache-first режим по умолчанию для демо;
- admin кнопка `Продолжить из cache`.

Acceptance:

- зависший импорт виден как stale/error;
- reset не единственный способ восстановления;
- import не блокирует весь серверный процесс надолго.

### P1. Admin Project Cockpit

Цель: усилить именно админку проектов, не трогая симулятор.

В `SchematicProjectAdmin` добавить:

- inlines или read-only sections:
  - versions;
  - reviews;
  - measurements;
  - events;
  - AI examples;
  - artifacts.
- actions:
  - create/rebuild review from current `scheme_data`;
  - collect AI example from project;
  - promote to public demo;
  - mark as needs data;
  - attach artifact report.

Acceptance:

- админ может из одной карточки проекта понять, чего не хватает;
- можно быстро наполнить демо-проекты review/AI examples.

### P1. AI Dataset Review Queue

Цель: админ должен не просто видеть 72 examples, а модерировать корпус.

Добавить фильтры/колонки:

- `dataset_kind`;
- `scheme_family`;
- `topology_label`;
- `quality_label`;
- `source coverage`;
- `has scheme_data`;
- `has teacher_rules`;
- `used_in_model`;
- `created_from_project/artifact/learning`.

Actions:

- validate selected;
- quarantine selected;
- mark text-only;
- mark scheme-backed;
- recalculate quality;
- promote selected to projects;
- export selected JSONL.

Acceptance:

- можно собрать чистый graph-training corpus без ручного копания в JSON;
- можно отдельно держать text corpus для объясняющего AI.

### P1. Grafana/metrics bridge

Цель: сделать счетчики для админки и ML видимыми в Grafana.

Endpoint:

`/staff/metrics/prometheus/` или management export.

Метрики:

- `dolg_ai_examples_total`;
- `dolg_ai_examples_validated_total`;
- `dolg_ai_examples_scheme_backed_total`;
- `dolg_ml_job_running`;
- `dolg_ml_job_stale`;
- `dolg_ml_job_duration_seconds`;
- `dolg_projects_without_review_total`;
- `dolg_artifacts_total`;
- `dolg_moderation_open_cases_total`;
- `dolg_dataset_validation_errors_total`.

Acceptance:

- Grafana может показать ML/import progress и stale jobs;
- админка и Grafana используют один service-layer counters.

### P1. Neural improvement without simulator changes

Цель: прокачать нейробалабола за счет данных, а не правки симулятора.

Что делать:

1. Улучшить `score_scheme_for_training`.
2. Заполнять `scheme_family/topology_label`.
3. Поддержать похожие проекты:
   - по компонентному составу;
   - по graph metrics;
   - по review findings;
   - по source topics.
4. В `deep_hint` показывать:
   - похожие валидированные схемы;
   - teacher rule;
   - quality score;
   - confidence policy;
   - почему модель не уверена.
5. В AI-панели использовать это как explanation, но не менять verdict.

Acceptance:

- AI не повторяет одно и то же, а опирается на похожие случаи;
- staff видит, какие примеры реально влияют на hints.

## Что убрать из ближайшего фронта

| Убрать/отложить | Почему |
|---|---|
| Measurement Core как P0 | Требует данных симулятора; сейчас симулятор не трогаем. Оставить только чтение уже существующих records. |
| SimulationRun seed как P0 | Можно вернуться позже; сейчас фокус на ML/admin. |
| NetInspector UI | Может затронуть simulator/CAD UI; отложить. |
| Lithium XML import preview UI | Полезно, но вторично после админки и dataset jobs. Можно оставить как P2. |
| Gerber/PCB exports | Не входит в текущий фокус. |

## Новый порядок выполнения

### День 1-2: аудит и админ-основа

1. Добавить `MLJob`.
2. Перевести ML import/training progress на `MLJob + cache`.
3. Добавить admin для `MLJob`.
4. Добавить `/staff/ops/` dashboard.

### День 3-4: dataset quality

1. Стандартизировать `features.dataset_kind`.
2. Пересчитать dataset metadata командой.
3. Улучшить `ml_dataset_quality.html`.
4. Добавить actions в `AITrainingExampleAdmin`.

### День 5-6: import hardening

1. Добавить stage timeout/retry/skip.
2. Сделать local-cache-first default для демо.
3. Добавить job history и output tail.
4. Проверить зависшие импорты.

### День 7-8: neural deep hints

1. Улучшить похожие случаи.
2. Добавить explanation fields в `deep_hint`.
3. Обновить AI API response.
4. Обновить документацию и демо-сценарий.

## Короткий вывод

Предыдущий фронт был слишком широким и частично дублировал уже реализованные вещи. После перепроверки ближайший реальный фронт:

1. **Админка как операционный центр.**
2. **Persistent ML jobs вместо cache-only прогресса.**
3. **Dataset quality и разделение text-only/scheme-backed.**
4. **Защита dataset import от зависаний.**
5. **Нейронка умнее за счет curated examples, похожих случаев и trace, без правок симулятора.**

