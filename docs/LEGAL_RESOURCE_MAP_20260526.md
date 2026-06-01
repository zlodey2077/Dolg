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
