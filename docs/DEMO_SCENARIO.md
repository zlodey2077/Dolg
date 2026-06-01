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
