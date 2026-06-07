# Видео-отложка (очередь на разбор)

Кандидаты на конспект, найденные через `scripts/yt_transcript.py` (yt-dlp `ytsearch`).
Конспекты пишутся в [ENGINEERING_NOTES.md](ENGINEERING_NOTES.md). Принцип отбора:
не how-to гайды, а лекции/глубина, углубляющие существующий функционал DOLG без новых сущностей.

Легенда: ☑ разобрано · ☐ в очереди · ⭐ высокий приоритет (прямое попадание в подсистему).

## Симулятор / движок (наш MNA `monte_carlo.solve_dc`)
- ☑ Adi Teman — Behind the Scenes of the SPICE Simulator, Part 1 (`1ZhzhWAt7xc`, 18:06) — конспект G
- ☐ Adi Teman — SPICE Behind the Scenes, Part 2–4 (найти ID, продолжение по DC/Newton/Transient)
- ☐⭐ Mastering Microelectronics — How SPICE Works (`r5JE1TYgERI`, 11:26)
- ☐ ЭПУ-схемотехника — SPICE моделирование в Altium Designer (`1RSW4fT6A-w`, 66:02)
- ☐ GERSIO — LTspice, введение (`IUpDn45Hv-Y`, 24:41)

## Monte Carlo / статистика (наш `run_tolerance_analysis`)
- ☑ MIT 6.0002 — Monte Carlo Simulation (`OgO1gpXSUzU`, 50:05) — конспект H
- ☐⭐ Maplesoft — Worst-Case Circuit Analysis (`I5YOvXu0cOE`, 88:59) — прямое продолжение worst-case
- ☐ Abhijit Pethe — Your Simulation Gives One Answer, Silicon Gives a Distribution (`bbSdXXFoaQo`, 27:51)

## Схемотехника / теория цепей (expert_rules + библиотека моделей ideal/real)
- ☐⭐ Kukoba Anatoliy — курс «Аналоговая схемотехника» (канал; лекции `6lGBHVyfLVs`/`tzy9je90r1E`/`65DV-kjpRwA`/`RvtCP51z_tU`/`vlrWW3yH6bY`, 50–124 мин)
- ☐ СПбГЭТУ «ЛЭТИ» — Аналоговая электроника, Лекция 1 (`k2DcpiT0ZG4`, 69:14)
- ☐ Константин Паращук — Аналоговая электроника (`pm9j9E2_WAo`, 90:44)
- ☐ Ю.В. Кузнецов — Основы теории цепей, Лекция 1 (`bSNQmDzgFGQ`, 88:31)
- ☐ Сигналы и системы — ОТЭЦ 2024, Лекция 01 (`mptbuT_Evuo`, 82:54)

## PCB / целостность сигналов / EMC (PCB-editor + DRC/ERC + автороутер)
- ☑ Рик Хартли (пер. Муравьёв) — Земля в печатных платах (`c-VAPqNBDRU`, 2:01:30) — конспект I
- ☐⭐ Robert Feranec — Many EMC Tips to Help You Design Better PCB (`gHF5JyJF-N4`, 111:43)
- ☐⭐ Академия программирования — PCB Return Currents (`ay32tYigkHE`, 75:18)
- ☐ Академия программирования — Ground, Noise, and Power (`zwa5x5qWxvE`, 72:38)
- ☐ LearnEMC — Circuit Board Layout for EMC (`ImkvsQEY6OY`, 14:13)
- ☐ Zuken — Практическая целостность сигнала (`nK52ND_fVUE`, 79:30)

## Термика (наша thermal-секция, P=ΔU²/R → ΔT)
- ☐⭐ Power Electronics with D — Силовая электроника, Тепловые аспекты (`JMh9FQPBdd8`, 15:09)
- ☐ Altium Academy — Thermal Resistance and Heat Transfer in PCB Design (`Zd0EdcWwaZg`, 11:48)
- ☐ S. Rajaram — Thermal Design of Electronic Equipment (`uRfKw9TKv4w`, 73:01)
- ☐ EEVblog #744 — SMD Thermal Heatsink Design (`2ygnAv6koSQ`, 22:43)

## Надёжность / derating (expert/paranoia + «реальная» ветка моделей)
- ☐⭐ High SNR — Прекратите завышать габариты MOSFET (`dqgPj5GjbJk`, 13:06)
- ☐ Phil’s Lab — Switching Regulator Component Selection & Simulation (`FqT_Ofd54fo`, 17:00)

## Питание / стабилизаторы (expert-правила + formula_compute, «собери стабилизатор 5В»)
- ☐⭐ Dmitry Kuznetsov — Compensating voltage stabilizers (`c2ctYvsGB-g`, 20:17)
- ☐ Морев А.В. — Источники питания, компенсационный стабилизатор (`WDBNIBA7Jt0`, 48:33)
- ☐ два + два пять — Types of Power Supplies, Transformers (`zlznzVM7wus`, 63:21)
- ☐ Dmitry Kuznetsov — DC-DC понижающего типа (`2pIHdbddPQI`, 33:54)
- ☐ Сергей Амелин — Источники тока (`NHfUwKLOoq4`, 49:16)

## Измерения / КИП (measurements/probes в симуляторе)
- ☐ Vladimir Savin — Контрольно-измерительные приборы, Лекция 1 (`5mvX41yB0kA`, 82:55)
- ☐ Vladimir Savin — КИП, Лекция 2 (`hrBEq6CwPbQ`, 85:34)
- ☐ ElectronicsClub — Как пользоваться осциллографом (`bAg7YkgrXKA`, 66:21)

---

**Уже разобрано в ENGINEERING_NOTES.md** (не дублируем здесь): DevOps (деплой/Docker/nginx/БД),
CAD (AutoCAD основы/массивы/блоки, КОМПАС 3D/2D-ЕСКД/резьба), лекции G/H/I (SPICE/MonteCarlo/Земля).

**Следующие оси для поиска (TODO):** радиотехника/антенны/РЭБ (наш RF/scikit-rf), встраиваемые/
микроконтроллеры (наш CircuitPython-экспорт), цифровая схемотехника/логика, трассировка/DFM.

## Код / реализация инженерных программ (архитектура DOLG: CAD, симулятор, движки)
- ☐⭐ Яков Шамрай — Введение в разработку САПР (`BNuoEWTykOU`, 65:30) — общая архитектура САПР
- ☐⭐ Introduction to Constraint-based Modelling — Karthik (`G0ibqc6RKSM`, 72:52) — constraint solver (привязки/параметрика CAD)
- ☐ C3D Labs — Геометрическое ядро C3D и КОМПАС-3D (`-6aeoVhTx84`, 20:28) — что такое геом. ядро (3D-вектор)
- ☐ IEEE — Introduction to SPICE, General-Purpose Simulator (`BnbcD-k4PD8`, 73:30) — глубже движок симулятора
- ☐ SolveSpace (open-source параметрический CAD с constraint solver) — референс кода (`7eCLYjkIbU8` — обзор; смотреть репозиторий)
- ☐ SketchGraphs — датасет CAD-констрейнтов (`ki784S3wjqw`, 2:33) — потенц. корм для ML-привязок

## КПД / производительность (наш Django-бэкенд + профилирование)
- ☐⭐ PyCon ZA — Supercharge Your Django Apps: Performance Secrets (`BrXXDyO9Pzw`, 29:21)
- ☐ DjangoCon US — Optimizing Django response times (`vYWPnzhDpTo`, 23:20)
- ☐ Python Ireland — Django Performance Optimization (Silk) (`mVg3pKEV75M`, 30:24)
- ☐ NeuralNine — Code Profiling with cProfile (`BZzb_Wpag_M`, 15:10) — профилировщик
