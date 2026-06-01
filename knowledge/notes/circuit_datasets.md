# Открытые circuit datasets для расширения DOLG ML training

Research выполнен 2026-05-26. Все ссылки верифицированы через WebSearch.
Импортёры в `Dolg_APP/services/cad_import.py` уже умеют: `import_spice_netlist`,
`import_kicad_xml`, `import_kicad_sexpr` — батчевый цикл = ~50 строк.

## Топ-3 datasets для импорта

### 1. Open Schematics (HF) — главный приз
- **URL**: https://huggingface.co/datasets/bshada/open-schematics
- **License**: CC-BY-4.0 (атрибуция обязательна)
- **Размер**: **84 470 KiCad-схем**
- **Формат**: parquet, поля `schematic` (.kicad_sch текст) + готовый `json` + PNG + `components_used`
- **Импорт**: `datasets.load_dataset("bshada/open-schematics")` → для каждой записи приоритет `json` → fallback `import_kicad_sexpr(schematic)`
- **×335 от текущих 340 схем** — один источник умножает dataset на два порядка
- Метаданные: `source_ids: ['hf:bshada/open-schematics']`, `attribution: "Open Schematics CC-BY-4.0"`

### 2. Masala-CHAI — академический curated
- **URL paper**: https://arxiv.org/abs/2411.14299
- **License**: open-source (см. репо в Appendix)
- **Размер**: 7 500 SPICE-netlists из 10 учебников
- **Формат**: .sp / .cir
- **Импорт**: `import_spice_netlist` напрямую
- **Ценность**: педагогическая, идеально для curriculum learning (от простых RLC к Δ-Σ)

### 3. AnalogGym — high-quality benchmarks
- **URL paper**: https://arxiv.org/abs/2409.08534
- **GitHub**: github.com/CODA-Team/AnalogGym
- **Размер**: 30 топологий в 5 категориях (sensing, references, LDO, amplifiers, PLL)
- **Формат**: SPICE + testbenches
- **Ценность**: качество > количества, few-shot evaluation

## Также полезно

- **CircuitJS1 (Falstad)**: github.com/pfalstad/circuitjs1, GPL-2.0, **1000+ примеров** в `war/circuits/`. Свой текстовый формат, парсер ~150 строк, либо batch-export в SPICE через UI.
- **ngspice examples**: BSD-3-Clause, синергия с уже подключённой ngspice.wasm.
- **symbench/spice-datasets**: GitHub-краулинг KiCad → SPICE дедуплицированный (лицензию проверить вручную).
- **KiCad symbols**: CC-BY-SA-4.0, тысячи символов — для расширения словаря компонентов tokenizer'а.
- **CircuitNet 2.0**: 10 791 designs ICLR'24, slишком крупный для tiny PyTorch на JSON.
- **OSHWA**: 2000+ certified projects, директория с фильтром по KiCad.

## Лицензионная стратегия

| Лицензия | Совместимость | Использование |
|---|---|---|
| MIT / BSD / Apache / CC0 | полная | core training set |
| CC-BY-4.0 | требует атрибуции | основной приз (Open Schematics) — указывать в `__training_metadata.attribution` |
| CC-BY-SA-4.0 | + ShareAlike | для словаря компонентов OK; производные схемы — публиковать совместимо |
| GPL-2.0 / GPL-3.0 | copyleft | НЕ включать raw netlists в репозиторий; тренировка модели — fair use |

**Рекомендация для диплома**: core на CC-BY-4.0 + BSD/MIT/Apache; GPL — opt-in subset вне основного чекпоинта.

## Технический план импорта (TODO)

1. `pip install datasets` (~50 МБ)
2. Создать `Dolg_APP/management/commands/import_external_dataset.py`:
   - `--source open_schematics` → `load_dataset("bshada/open-schematics")`
   - Filter: `3 ≤ len(components) ≤ 50`
   - Dedup по нормализованному графу
   - Batch insert в `AITrainingExample` с правильным `attribution`
3. Размер на диске: parquet ~500 МБ + распакованные схемы ~2 ГБ → отдельный location, не в git
4. После импорта: `python manage.py train_tiny_circuit_ai --include-curated` подхватит автоматически

Этот sprint отложен — текущая база (340 procedural curated) + passive features (см. `Dolg_APP/ml/neural.py`) уже даёт baseline, на которую можно сравнивать после import.
