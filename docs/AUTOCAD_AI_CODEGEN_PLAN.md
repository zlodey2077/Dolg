# AutoCAD AI Codegen Plan

Дата: 2026-06-09

Цель: зафиксировать рабочий план по нейросетевому генератору AutoCAD-скриптов и CAD-геометрии: от датасета и источников до валидации, ускорения инференса и финального теста "начертить план квартиры по текстовому описанию".

## Короткий вывод

Идея правильная, но начинать лучше не с прямого дообучения большой модели на сырых LISP/DXF-файлах. Самый устойчивый путь:

1. Собрать легальный реестр источников и датасет только с понятными лицензиями.
2. Ввести промежуточную CAD-JSON схему: стены, окна, двери, слои, блоки, размеры, стили, ограничения.
3. Научить генератор выдавать сначала CAD-JSON, а уже затем конвертировать его в DXF, AutoLISP, ezdxf Python или AutoCAD .NET.
4. Валидировать результат объективно: парсинг, список entities, слои, bounding boxes, размеры, открытие в AutoCAD/ezdxf.
5. Дообучать модель через LoRA только после появления проверенных пар "запрос -> схема -> код -> результат".

Такой подход уменьшает риск получить "красивый, но нерабочий код" и делает систему пригодной для автоматических тестов.

## Что важно поправить в исходной идее

- CodeBERT tokenizer не стоит насильно прикручивать к CodeGemma или CodeT5 при fine-tuning. Для дообучения обычно используется нативный токенизатор выбранной модели. CodeBERT tokenizer можно оставить для отдельного retrieval/classification слоя или анализа code/text-пар.
- Сырые скрипты с CADforum, Autodesk Community и форумов нельзя автоматически считать пригодными для обучения. Нужно проверять лицензию, условия использования и сохранять source/license metadata по каждому примеру.
- Скриншот AutoCAD полезен для финального контроля, но первая линия валидации должна быть геометрической: entities, слои, координаты, типы примитивов, размеры, пересечения и ограничения.
- AutoCAD COM/ActiveX через pyautocad/comtypes удобен для прототипа, но для стабильного production-пайплайна лучше иметь headless-ветку на ezdxf и отдельный Windows-runner для живого AutoCAD.
- Асинхронная отрисовка может ускорить UX, но COM-вызовы AutoCAD часто нужно сериализовать. `async/await` лучше использовать как оркестратор очереди команд, а не как параллельный доступ к AutoCAD.

## Архитектура

Пайплайн:

```text
Пользовательский запрос
  -> intent/parser
  -> CAD-JSON plan
  -> generator backend
       -> ezdxf Python
       -> DXF
       -> AutoLISP
       -> AutoCAD .NET / C#
       -> ActiveX/VBA
  -> validator
  -> renderer/executor
  -> repair loop
  -> cache
```

Основной контракт между моделью и CAD-средой:

```json
{
  "units": "mm",
  "layers": ["walls", "windows", "doors", "dimensions"],
  "entities": [
    {
      "type": "line",
      "layer": "walls",
      "start": [0, 0],
      "end": [5000, 0]
    },
    {
      "type": "window",
      "layer": "windows",
      "bounds": {
        "center": [2500, 0],
        "width": 1200,
        "height": 1500
      }
    }
  ],
  "constraints": [
    "all walls must be closed",
    "windows must lie on wall segments"
  ]
}
```

## Датасет

### Источники данных

1. Официальные AutoCAD-документы: AutoLISP, DXF, .NET/ObjectARX, ActiveX.
2. ezdxf tutorials/examples и синтетически созданные DXF-примеры.
3. GitHub-репозитории с AutoLISP/DXF/AutoCAD automation кодом только при понятной permissive-лицензии.
4. Собственные синтетические пары: "задача на русском/английском -> CAD-JSON -> код -> ожидаемые entities".
5. DCL/VBA/.NET примеры добавить во второй фазе, когда базовая геометрия уже валидируется.
6. Форумы и сообщества использовать как материал для ручного анализа задач и терминологии, но не как автоматический training corpus без проверки лицензии.

### Схема записи

```json
{
  "id": "acad_task_000001",
  "task_ru": "Нарисуй линию от точки (0,0) до (100,50) на слое Walls",
  "task_en": "Draw a line from (0,0) to (100,50) on the Walls layer",
  "intent": "draw_line",
  "input_drawing": null,
  "output_format": "ezdxf_python",
  "cad_json": {
    "entities": []
  },
  "code": "msp.add_line((0, 0), (100, 50), dxfattribs={'layer': 'Walls'})",
  "expected_entities": [
    {
      "type": "LINE",
      "layer": "Walls",
      "start": [0, 0],
      "end": [100, 50]
    }
  ],
  "source_url": "synthetic",
  "license": "project-owned",
  "verification_status": "validated_by_ezdxf",
  "autocad_required": false,
  "notes": ""
}
```

### Минимальные классы задач

- Примитивы: line, polyline, circle, arc, rectangle, hatch.
- Слои: создание, выбор, цвет, line type, line weight.
- Блоки: создание, вставка, атрибуты, динамические параметры.
- Архитектурные элементы: стены, окна, двери, комнаты, размеры.
- Операции: move, rotate, mirror, array, trim/extend-like transformations.
- Аннотации: dimensions, text, labels, title block.
- Импорт/экспорт: DXF, JSON, screenshot/render metadata.

## Модельная стратегия

### Фаза 1 - без fine-tuning

- Retrieval + шаблонные генераторы.
- Модель получает документацию, примеры и JSON schema.
- Выход строго ограничен: CAD-JSON или небольшой code block.
- Валидатор отклоняет результат, если нарушена схема или геометрия.

### Фаза 2 - supervised fine-tuning

- База: CodeT5/CodeT5+ или CodeGemma.
- LoRA/PEFT адаптеры, чтобы не переобучать всю модель.
- Сначала обучать на "request -> CAD-JSON", затем на "CAD-JSON -> code".
- Для CodeGemma учитывать лицензию Google и требования Hugging Face gated-моделей.

### Фаза 3 - repair loop

- Модель генерирует код.
- Валидатор возвращает ошибки: invalid DXF, wrong layer, missing block, bad bounds.
- Модель исправляет только diff/patch, а не переписывает весь чертеж.

### Фаза 4 - live AutoCAD runner

- pyautocad/comtypes для COM/ActiveX прототипа.
- Отдельный Windows-runner с установленным AutoCAD.
- Изоляция профиля, backup drawing, запрет выполнения непроверенных макросов.
- Скриншот используется как дополнительный сигнал, но не заменяет геометрическую проверку.

## Ускорение

1. LoRA: быстрое дообучение адаптеров на проверенных CAD-парах.
2. CAD-JSON вместо сырого DXF: модель генерирует смысл, а не пытается помнить весь синтаксис DXF.
3. ONNX Runtime/int8: рассмотреть после стабильного baseline, потому что экспорт LLM в ONNX может быть отдельной задачей.
4. SQLite cache: ключом должен быть normalized request + schema version + target backend, а не просто raw prompt.
5. Chunked generation: генерировать и проверять чертеж частями: outline -> walls -> openings -> dimensions -> annotations.
6. Speculative decoding: экспериментально, после появления малой модели-черновика и большой модели-ревьюера.
7. Геометрическое сжатие через octree/spherical CNN: research-направление для 3D/сложной геометрии, не MVP.

## Валидация

Минимальные проверки:

- JSON schema validation.
- DXF parse/write через ezdxf.
- Entity count/type/layer checks.
- Bounding box и units checks.
- Проверка замкнутости стен/контуров.
- Проверка, что окна и двери лежат на стенах.
- Проверка размеров и аннотаций.
- Открытие в AutoCAD только для задач, где нужен реальный AutoCAD runtime.

Метрики:

- syntax_valid_rate;
- geometry_valid_rate;
- layer_style_accuracy;
- autocad_execution_success_rate;
- repair_loop_success_rate;
- average_latency;
- cache_hit_rate;
- license_coverage_rate.

## Финальный тест

Задача:

```text
Начерти план квартиры по текстовому описанию:
две комнаты, кухня, санузел, коридор, входная дверь, по одному окну в каждой комнате,
стены 200 мм, размеры в миллиметрах, отдельные слои для стен, окон, дверей и размеров.
```

Критерии прохождения:

- Создан валидный CAD-JSON.
- Сгенерирован DXF или ezdxf Python без ошибок.
- Все помещения имеют замкнутые контуры.
- Двери и окна размещены на стенах.
- Слои корректны.
- Размеры читаемы.
- Файл открывается в AutoCAD или валидируется headless через ezdxf.

## Реестр источников

| Источник | Статус | Как использовать |
|---|---|---|
| Autodesk AutoCAD API overview - https://aps.autodesk.com/developer/overview/autocad | Primary | Карта официальных AutoCAD API: ObjectARX, .NET, AutoLISP, ActiveX |
| Autodesk AutoCAD/ObjectARX Help 2025 - https://help.autodesk.com/view/OARX/2025/ENU/ | Primary | Официальная справка по ObjectARX/.NET |
| AutoCAD .NET Transaction class - https://help.autodesk.com/view/OARX/2025/ENU/?guid=OARX-ManagedRefGuide-Autodesk_AutoCAD_DatabaseServices_Transaction | Primary | Примеры жизненного цикла database transaction |
| AutoLISP Developer's Guide - https://help.autodesk.com/cloudhelp/2022/ENU/AutoCAD-AutoLISP/files/GUID-265AADB3-FB89-4D34-AA9D-6ADF70FF7D4B.htm | Primary | Синтаксис и официальные паттерны AutoLISP |
| AutoCAD ActiveX customization - https://help.autodesk.com/view/ACDLT/2026/ENU/?caas=caas%2Fdocumentation%2FACD%2F2014%2FENU%2Ffiles%2FGUID-2090E4E8-9AE0-4E01-B5EB-0843A30EB0E9-htm.html | Primary | COM/ActiveX автоматизация и VBA-подход |
| AutoCAD ActiveX create objects - https://help.autodesk.com/cloudhelp/2020/ENU/AutoCAD-ActiveX/files/GUID-98C74CFE-E0C6-40AD-A8B7-E4FC6CE7E16F.htm | Primary | Создание объектов через ActiveX |
| Autodesk DXF Reference - https://help.autodesk.com/cloudhelp/2018/ENU/AutoCAD-DXF/files/index.htm | Primary | Спецификация DXF как текстового обменного формата |
| About DXF files - https://help.autodesk.com/cloudhelp/2023/ENU/AutoCAD-DXF/files/GUID-235B22E0-A567-4CF6-92D3-38A2306D73F3.htm | Primary | Модель tagged data и структура DXF |
| ezdxf docs - https://ezdxf.readthedocs.io/ | Primary | Headless генерация, чтение и проверка DXF |
| ezdxf PyPI - https://pypi.org/pypi/ezdxf/ | Primary | Версии и пакет для Python-зависимостей |
| pyautocad docs - https://pyautocad.readthedocs.io/ | Secondary | COM/ActiveX прототипирование AutoCAD из Python |
| cad2json - https://github.com/chyh1990/cad2json | Candidate | Проверить поддержку, лицензию и пригодность для CAD->JSON |
| CodeT5 - https://github.com/salesforce/CodeT5 | Candidate model | База для code understanding/generation экспериментов |
| CodeGemma - https://deepmind.google/models/gemma/codegemma/ | Candidate model | Кодовая модель Google; проверить лицензию перед использованием |
| CodeGemma on Hugging Face - https://huggingface.co/google/codegemma-7b | Candidate model | Модель может требовать принятия условий доступа |
| CodeBERT tokenizer - https://huggingface.co/microsoft/codebert-base/tree/main | Auxiliary | Не основной tokenizer для CodeGemma/CodeT5, но полезен для retrieval/classification |
| Hugging Face PEFT - https://github.com/huggingface/peft | Training infra | LoRA/PEFT адаптеры для экономного fine-tuning |
| ONNX Runtime quantization - https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html | Inference infra | int8/quantization после стабильного baseline |
| Microsoft SchGen - https://huggingface.co/microsoft/SchGen | Adjacent reference | Пример codegen-модели для схем, не AutoCAD |
| revit-coder-14b - https://huggingface.co/schauh11/revit-coder-14b | Adjacent reference | Сравнить подходы Revit API codegen, не смешивать данные без проверки |
| Microsoft O-CNN - https://github.com/microsoft/O-CNN | Research | Octree-предобработка геометрии для будущих 3D/CAD экспериментов |
| Autodesk GitHub - https://github.com/autodesk | Candidate | Искать официальные generative design материалы; конкретный repo `Autodesk/generative-design` нужно перепроверить |

## Ближайшие изменения в проекте

1. Создать `cad_codegen_sources.yaml` или JSON-реестр источников с license/status.
2. Описать CAD-JSON schema для базовых entities.
3. Добавить headless prototype на `ezdxf`: natural task -> static JSON -> DXF -> validation report.
4. Сгенерировать первые 50-100 synthetic tasks для стен, окон, дверей, слоев и размеров.
5. Подключить SQLite cache для нормализованных CAD-команд.
6. Добавить pytest-набор для geometry validation.
7. После этого переходить к модели: сначала RAG/constrained generation, затем LoRA.

## Риски

- Лицензии форумных скриптов могут запретить training usage.
- AutoCAD GUI/COM трудно стабильно гонять в CI.
- LISP/VBA/.NET код может быть опасен при исполнении, нужен sandbox и allowlist операций.
- Fine-tuning на грязном датасете ухудшит качество сильнее, чем отсутствие fine-tuning.
- Скриншотная проверка без геометрических метрик будет слишком шумной.

## Решение для MVP

MVP должен быть не "модель сразу пишет LISP", а "модель или шаблон пишет CAD-JSON, валидатор доказывает корректность, backend переводит в DXF/ezdxf/AutoLISP". Это даст контролируемую основу, которую потом можно расширять до AutoCAD .NET, pyautocad, repair loop и полноценного apartment-plan генератора.
