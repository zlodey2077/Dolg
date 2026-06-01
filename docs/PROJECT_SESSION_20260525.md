# Сеанс проектирования DOLG

## Смысл слоя

`SchematicProject` теперь рассматривается не только как сохраненная схема, а как web-ориентированный сеанс проектирования. В одном контейнере сходятся схема, версии, запуски симуляций, измерения, Engineering Review, BOM, комментарии, импорт, экспорт и история действий.

Это закрывает важную дипломную линию: DOLG связывает торговую часть и инженерную часть не через набор разрозненных страниц, а через одну информационную модель проекта.

## Что добавлено

- `ProjectEvent` — журнал действий проекта: `scheme_saved`, `simulation_run`, `measurement_added`, `review_created`, `bom_exported`, `import_finished`, `comment_added`.
- `/projects/api/<id>/dashboard/` — dashboard API проектного кабинета: схема, версии, симуляции, измерения, последний review, BOM и события.
- Кнопка `Сеанс` на странице `/projects/` — компактный кабинет проекта с историей сеанса.
- `SimulationRun` получил async-поля: `status`, `progress_percent`, `message`, `started_at`, `finished_at`.
- WebSocket `ws/project/<id>/` — push-канал проекта для будущих долгих операций: симуляция, review, import, export.
- Постобработка симуляции: `/projects/api/<id>/simulation/postprocess/` считает RMS, average, peak-to-peak, `V/I`, `I*V`, markers, формулы, FFT и Bode.
- CSV export: `/projects/api/<id>/simulation/<run_id>/export.csv`.
- Design Validity Guard — review предупреждает, если расчет или измерение выходит за пределы ratings/datasheet: ток, напряжение, мощность, температура.

## Почему это важно для защиты

- Можно показать не “каталог + редактор”, а полный инженерный цикл: схема -> симуляция -> измерение -> review -> BOM -> отчет -> история.
- События проекта доказывают, что система хранит контекст работы, а не только финальные файлы.
- Постобработка приближает DOLG к Qucs-подходу: результат симуляции становится набором данных, над которым можно выполнять формулы.
- Validity Guard добавляет инженерную честность: “симуляция посчиталась” не означает “режим допустим”.

## Demo flow

1. Открыть `/projects/`.
2. Нажать `Сеанс` у demo-проекта.
3. Показать версии, последние симуляции, измерения, review, BOM и события.
4. Запустить или сохранить симуляцию.
5. Выполнить postprocess: RMS/FFT/Bode/формула.
6. Экспортировать CSV.
7. Открыть Engineering Review и показать warning по области применимости, если есть перегрузка.

## Контроль качества

- `python manage.py check` — OK.
- `python manage.py makemigrations --check --dry-run` — No changes detected.
- `python manage.py test Dolg_APP.tests.SimulationRunModelTests Dolg_APP.tests.ProjectSessionTests Dolg_APP.tests.EngineeringReviewTests Dolg_APP.tests.SimulationAnalysisLibraryTests` — 40/40 OK.
- `python manage.py test shop.tests.DemoReadyCommandScientificStackTests` — 1/1 OK.
- `python manage.py check_demo_ready --json` — OK, добавлен блок `project_session`.
- `python manage.py check_data_integrity --json` — OK, `rating_limit_coverage: 43/43`.
