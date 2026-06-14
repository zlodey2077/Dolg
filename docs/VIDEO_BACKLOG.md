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

- ☑⭐ Power Electronics with D — Силовая электроника, Тепловые аспекты (`JMh9FQPBdd8`, 15:09) — конспект Y
- ☐ Altium Academy — Thermal Resistance and Heat Transfer in PCB Design (`Zd0EdcWwaZg`, 11:48)
- ☐ S. Rajaram — Thermal Design of Electronic Equipment (`uRfKw9TKv4w`, 73:01)
- ☐ EEVblog #744 — SMD Thermal Heatsink Design (`2ygnAv6koSQ`, 22:43)

## Надёжность / derating (expert/paranoia + «реальная» ветка моделей)

- ☑⭐ High SNR — Прекратите завышать габариты MOSFET (`dqgPj5GjbJk`, 13:06) — конспект AK
- ☐ Phil’s Lab — Switching Regulator Component Selection & Simulation (`FqT_Ofd54fo`, 17:00)

## Питание / стабилизаторы (expert-правила + formula_compute, «собери стабилизатор 5В»)

- ☑⭐ Dmitry Kuznetsov — Compensating voltage stabilizers (`c2ctYvsGB-g`, 20:17) — конспект AL
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

- ☑⭐ Яков Шамрай — Введение в разработку САПР (`BNuoEWTykOU`, 65:30) — общая архитектура САПР — конспект AM
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

## Каталог / магазин (наш shop: карточка, поиск/фильтры, рекомендации, конверсия)

- ☐⭐ Как работают рекомендации товаров на маркетплейсах (Python) (`7M4WOiChC38`, 115:12) — рекомендашки → «похожие товары» через наш semantic_search
- ☐⭐ Как увеличить конверсию интернет-магазина. Контент/дизайн — Павел Лебедев (`h1tSsBdVtWQ`, 74:56) — карточка товара, конверсия
- ☐ Recommender System for an Online Store — OTUS (`75mYZz2uxXk`, 53:16) — реализация рекомендаций
- ☐ Customer Experience: рекомендательные системы — Userstory (`k16GOQoO2hI`, 33:17) — почему работают
- ☐ Фильтры, full-text поиск (Laravel Scout) (`DX-nrNVhhWI`, 37:13) — фасетный поиск (концепты, у нас rapidfuzz/Postgres FTS)
- ☐ UX/UI аудит главной интернет-магазина (`LB-nV16T8Xk`, 17:15) — UX-аудит каталога

## Новости / заголовки (наш раздел /news/)

- ☐⭐ Заголовки: что написать — Школа вебмастеров (`84mwHOUeqtw`, 58:32) — мастер-класс по заголовкам
- ☐ Как создавать убойные заголовки (`N2DJjNXtSGg`, 25:33) — компактнее
- ☐ Как придумать заголовок: метод газеты «Коммерсантъ» (`KdTOfZ_0JqI`, 1:55) — классический приём
- ☐ 16 советов написания заголовков (`GkUSjNDxCm4`, 2:48) — чек-лист

## Графика редактора (наш canvas симулятора/CAD, Canvas2D/WebGL/Pixi)

- ☑⭐ Rendering performance from the ground up — Martin Splitt (`xuifyagAeu4`, 41:33) — конспект U
- ☐ Cranking Up Performance in Graphics-Intensive Web Apps — Chrome (`wkDd-x0EkFU`, 39:29)
- ☐ Canvas2D is getting an update — Chrome (`dfOKFSDG7IM`, 10:42)
- ☐ Making WebGL Dance — Steven Wittens, JSConf (`GNO_CYUjMK8`, 30:55)

## Алгоритмы трассировки (наш A*-автороутер) — тонко на YouTube, добивать статьями

- ☐ Lee Algorithm Implementation (maze router, родитель нашего A*) (`YUE0k2uVPFs`, 0:48)

## GNN / графовые сети (наш gnn_simulator, локальный AI)

- ☐⭐ Stanford CS224W: ML with Graphs (`ew1cnUjRgl4`, серия) — эталонный курс
- ☑⭐ Petar Veličković — Theoretical Foundations of GNN (`uF53xsT7mjc`, 72:20) — конспект AO
- ☐ TensorFlow — Intro to Graph Neural Networks (`8owQBFAHw7E`, 51:06)
- ☐ Microsoft Research — Intro to GNN: Models & Applications (`zCEYiCxrL_0`, 59:00)

## RAG / эмбеддинги (наш rag_roadmap + semantic_search)

- ☐⭐ Complete RAG Tutorial: Indexes, Embeddings, Vectors — SCALER (`BnpW1pDWr64`, 55:25)
- ☐ Learn RAG From Scratch — freeCodeCamp (`sVcwVQRHIc8`, 153:11) — исчерпывающе (очень длинно)
- ☐ codebasics — RAG Explained (`dDkynerzV-Q`, 14:36) — компактно

## RF / антенны / согласование (наш rf_analysis/scikit-rf, РЭБ-killer)

- ☑⭐ RF Design-6: Smith Chart & Impedance Matching — Anurag Bhargava (`NX6G9A2U7kM`, 43:50) — конспект V
- ☐ Impedance Matching on Smith Charts — EMPossible (`L24aB89-m5w`, 12:07)
- ☐ HackadayU — Introduction to Antenna Basics, Class 1 (`axUcybeamIk`, 41:02)

## Встраиваемые / CircuitPython (наш экспорт schema→code.py, RP2040/ESP32)

- ☐⭐ CircuitPython with Raspberry Pi Pico — Getting Started (`07vG-_CcDG0`, 42:47)
- ☐ DigiKey — Intro to Raspberry Pi Pico & RP2040, MicroPython (`PrMQpv9iCFw`, 12:40)
- ☐ CircuitPython vs MicroPython: ключевые отличия (`wyOcb2MHzIs`, 4:13)
- ☐ Core Electronics — Pico Course for Beginners (`Ic4ExTusoTw`, 243:45) — исчерпывающе, очень длинно

## Безопасность веб/Django (наш security_backlog)

- ☐⭐ DjangoCon US — Security Best Practices for Django (`pMfM7fIK6cs`, 36:05)
- ☐⭐ PyCon Sweden — Django Security against OWASP (`lWfJfviWIBU`, 30:32)
- ☐ Ultimate Django Security Cheat Sheet (`CFGjMBtCFbk`, 23:05)
- ☐ PyCon 2019 — Hands-On Web Application Security (`8W4MGggwgfM`, 78:05)

## Тестирование / pytest (наш testing_infra)

- ☐⭐ Talk Python — pytest tips and tricks (`qQ6b7OwT124`, 58:26)
- ☐⭐ Zac Hatfield-Dodds — «Stop Writing Tests!» property-based (Hypothesis) (`tiy031EoDXo`, 29:36) — для движков идеально
- ☐ Testing the Database Layer: problems & best practices (`ZBLaHL1mTW0`, 48:15)
- ☐ Real Python — Getting Started With Testing (`6tTI2Y8Xsd4`, 58:24)

## Цифровая схемотехника / логика (наши логические компоненты схемы)

- ☑⭐ ПЛИСоводство — Цифровая схемотехника, Л1 (комбинационные схемы) (`aGMfFezjVnQ`, 24:26) — конспект AN
- ☐ Тимур Маликов — Триггеры (RS, D, JK) (`7QLQplw5EKE`, 16:56)
- ☐ Dmitry Kuznetsov — Цифровая электроника, вводная (`gGGsVSP0oLc`, 19:34)
- ☐ Digital Circuit Design / Verilog, L7 (`k88TfckjIGA`, 72:41)

## 3D / геометрия в коде (вектор design+3D: серверный CAD, OpenCASCADE/CadQuery/FreeCAD)

- ☑⭐ jobstr — 3D Modelling with Python & CadQuery (parametric) (`H5oMQa0SUhY`, 12:05) — конспект X
- ☐ jobstr — Python 3D Modelling (полный) (`2sg_rxwL3Ys`, 127:20) — исчерпывающе, очень длинно
- ☐ Glad Labs — CadQuery: Parametric 3D с чистым Python (`n4p_WhPYD-g`, 6:53)
- ☐ Quaoar — OpenCascade in Python, getting started (`P4wEb0HzqKg`, 5:03)
- ☐ Things I Learned — Dataset of 3D Objects с FreeCAD (scripting) (`_61OzGV00h4`, 17:04) — + корм для ML
- ☐ Ruben — Compiling CadQuery with Docker (`LTRUhQWZnP0`, 2:56) — серверный/Docker путь

## Postgres / pgvector (наш postgres_migration + rag_roadmap)

- ☐⭐ Tiger Data — 18 Months of Pgvector Learnings (`Ua6LDIOVN1s`, 47:13)
- ☑⭐ NeuralNine — PGVector: Turn PostgreSQL Into Vector DB (`j1QcPSLj7u0`, 20:04) — конспект Z (web-sourced, видео под bot-check)
- ☐ Dave Ebbelaar — PostgreSQL as VectorDB (`Ff3tJ4pJEa4`, 14:25)

## Численные методы / NumPy-SciPy (наш MNA-солвер, scipy.sparse)

- ☐⭐ Mr. P Solver — SciPy для физиков/инженеров (`jmX4FOUEfgU`, 93:29)
- ☐⭐ UWaterloo — Optimizing ML Code in NumPy & SciPy (`gYcrEZW-xek`, 82:28)
- ☑ Meerkat — Gauss-Newton, нелинейный МНК (`Kln0ZQ7sX8k`, 20:02) — для нелинейного солвера (диод/LED) — конспект W
- ☐ 3Blue1Brown — Abstract vector spaces (`TgKwz5Ikpc8`, 16:46) — интуиция

## WebSockets / Django Channels (наш чат + авто-реактивная схема)

- ☐⭐ DjangoCon Europe 2023 — Building & scaling a live app (`NdRB9-Xtl9M`, 29:01)
- ☐ Dennis Ivy — Channels & WebSockets Oversimplified (`cw8-KFVXpTE`, 16:35)
- ☐⭐ Red Eyed Coder — Real-Time Graph with Channels (`tZY260UyAiE`, 31:16) — live-обновление как наша авто-схема

## Чистый код / Чистая архитектура (Р. Мартин) — принцип работы, см. память

- ☑ «Clean Code» / «Clean Architecture» (Р. Мартин) — конспект AA (по книгам/тексту, как методология)
