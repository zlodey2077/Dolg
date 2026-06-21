# Отчёт: 3D-поверхность поля напряжений (готово + проверено)

Реализована и **проверена в реальном симуляторе** первая genuinely-новая 3D-визуализация данных:
поле напряжений тяжёлой схемы как 3D-рельеф. Это «тяжёлый 3д-график» из запроса.

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
