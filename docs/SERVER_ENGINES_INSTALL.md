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
