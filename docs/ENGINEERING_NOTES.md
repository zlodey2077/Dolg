# Инженерные заметки (DOLG)

Общий рабочий документ по инженерному делу, математике и коду: конспекты обучающих
видео, статей, разборов — с привязкой к проекту DOLG. Пополняется по мере изучения
материалов (видео тянутся через `scripts/yt_transcript.py` / MCP `yt-transcript`).

## Закреплённые видео-источники

- **DevOps / деплой / инфраструктура:** канал [Просто Devops](https://www.youtube.com/@prosto_devops).
  Пользовательская ссылка `https://www.youtube.com/@prosto_devop` проверена 2026-06-07 и даёт 404;
  рабочий handle канала — `@prosto_devops`.
- **AutoCAD / САПР-функции для будущих конспектов:** [Autodesk AutoCAD: базовый уровень. Занятие №1](https://youtu.be/bsz_mFMpb7Y?si=YtaSgzuYCoGkKBrb).
  Транскрипт доступен через `scripts/yt_transcript.py`; основные главы: интерфейс, лицензия, сброс настроек,
  навигация, выбор объектов, `Line`/`Polyline`, прямоугольник, круг, сохранение DWG.

## Правила работы (best practices)

- **Мультимодальный поиск информации.** Когда ищешь инфу в интернете — использовать НЕ
  только текст, но и другие модальности: **видео** (транскрипт через `yt_transcript` →
  конспект), доки библиотек (context7), при необходимости аудио/кадры. Текст — не
  единственный источник; видео часто отражает практику и «суть» лучше статьи.

## Содержание
- [Видео-конспекты: DevOps / инфраструктура](#видео-конспекты-devops--инфраструктура)
  - [1. Что такое деплой? (Kubernetes)](#1-что-такое-деплой-kubernetes)
  - [2. Всё про Docker (best practices)](#2-всё-про-docker-best-practices)
  - [3. NGINX](#3-nginx)
  - [4. Всё про базы данных](#4-всё-про-базы-данных)
  - [5. DevOps Roadmap 2026](#5-devops-roadmap-2026)

---

## Видео-конспекты: DevOps / инфраструктура

Источник: канал [Просто Devops](https://www.youtube.com/@prosto_devops). Видео отобраны
по релевантности стеку DOLG (Django + Docker + nginx + переход на Postgres + контейнеризация движков).

### Очередь на расширение конспектов

Свежая выборка с канала `@prosto_devops` через `yt-dlp` 2026-06-07:

- [NETWORKING IN KUBERNETES](https://www.youtube.com/watch?v=1MlOpq06kg0) — приоритет для будущего K8s/Service/Ingress блока.
- [DEVOPS ROADMAP 2026](https://www.youtube.com/watch?v=a68hSZz0gAQ) — приоритет для дорожной карты развития DOLG DevOps.
- [Why is IT infrastructure so complex?](https://www.youtube.com/watch?v=glT-zyYf4Iw) — полезно для архитектурного SWAT/SWOT-разбора.
- [EVERYTHING YOU NEED TO KNOW ABOUT NETWORKS](https://www.youtube.com/watch?v=a55ecIWIkVc) — база для сетевого слоя Docker/nginx/ASGI.
- [EVERYTHING YOU NEED TO KNOW ABOUT LINUX](https://www.youtube.com/watch?v=eBqMWeVVzXE) — база для VM/YC/bootstrap/runbook.
- [WHICH LINUX TO CHOOSE?](https://www.youtube.com/watch?v=-1gm8-1FwkE) — опционально для выбора серверной ОС.

### 1. Что такое деплой? (Kubernetes)
[видео, 13:00](https://www.youtube.com/watch?v=n5Yk-9hZgXw)

**TL;DR:** Деплой в K8s = набор правил поверх декларативного подхода (описываем *желаемое
состояние*, кластер сам приводит реальность к нему).

**4 столпа деплоя:**
- **Deployment** — образ/версия, число реплик, лимиты CPU/RAM.
- **ConfigMap** — настройки отдельно от кода (не пересобирать образ ради смены лог-уровня/URL).
- **Service** — стабильная точка входа (поды смертны, IP меняются); раскидывает трафик на живые поды внутри кластера.
- **Ingress** — «дверь снаружи внутрь»: домен → Service.

**Путь деплоя 2025:** код → Docker → манифесты (можно генерить ИИ, но *доверяй-но-проверяй*) →
**Helm** (шаблон + `values-dev/prod.yaml` вместо копий YAML) → **CI** собирает образ в registry →
**CD/GitOps (ArgoCD)**: CI делает git-commit в инфра-репо, ArgoCD изнутри кластера синхронизирует.

**GitOps плюсы:** снаружи в кластер не ходим (безопасно); source of truth = git; self-healing
(вернёт состояние из git); авто-откат, canary/blue-green.

**Грабли:** stateful (БД/очереди) в K8s — боль, лучше VM/managed; секреты — Vault/Sealed Secrets,
никогда в репо; мониторинг (Prometheus/Grafana) — часть деплоя.

**Релевантность DOLG:** дорожная карта *если* пойдём в оркестрацию. Принцип «конфиг отдельно
от кода» + секреты уже актуальны для `settings.py`/`.env`. Stateless-движки (SPICE/КОМПАС в
контейнере) — кандидаты в K8s; БД — нет.

### 2. Всё про Docker (best practices)
[видео, 19:00](https://www.youtube.com/watch?v=vBD4jzv0oJ0)

**TL;DR:** Идеальный образ стоит на трёх китах — **скорость, безопасность, надёжность**. 13 правил.

**Образ — минимальный:**
- **Alpine** (~5 МБ, musl libc — для Go/статиков; Python/C++ могут тормозить/ломаться) →
  **slim** (Debian без доков, но с glibc — безопасный дефолт для Python) → **distroless**
  (только рантайм+приложение, нет shell/пакетника — максимум безопасности, но не подебажить).
- **Не `latest`** — пинить конкретную версию (`node:18-alpine`) → детерминированная сборка байт-в-байт.
- **`.dockerignore`** — не слать демону `.git`/`node_modules`/логи (скорость + безопасность).

**Кэш слоёв (быстрая пересборка):**
- Образ = слои; меняется слой → все последующие пересобираются.
- **Отделять зависимости от кода**: сначала `COPY` манифестов (requirements.txt) + установка,
  потом `COPY` остального кода → слой зависимостей берётся из кэша при правке кода.
- **Объединять команды** в один слой (`RUN a && b && rm cache` через `&&` + `\`) — иначе удалённые
  файлы остаются «мёртвым грузом» внутри образа.
- `COPY` (не `ADD`) для локальных файлов; для скачивания — `RUN wget/curl`. `ADD` — антипаттерн.

**Мультистейдж** (главное!): билд-стейдж (компиляторы/SDK, ~1 ГБ) → финальный стейдж копирует
только артефакт в чистый alpine (~15 МБ). Быстро качается, безопаснее (нечем взламывать).
**BuildKit** — современный движок (граф зависимостей, параллельные стейджи, cache mount);
включать `DOCKER_BUILDKIT=1` на старых CI.

**Безопасность:**
- **Непривилегированный пользователь** (`USER appuser`) — иначе root в контейнере = root на хосте при побеге.
- **Build secrets** (`--mount=type=secret`, требует BuildKit) — не `ARG`/`ENV` (запекаются в `docker history`).

**Надёжность (сигналы/оркестратор):**
- **PID1 ловит сигналы**: запуск через `exec` (приложение становится PID1) или `tini` (Java/капризные)
  — иначе SIGTERM от оркестратора игнорится → SIGKILL → оборванные транзакции.
- **HEALTHCHECK** — иначе Docker судит «жив ли процесс», а не отвечает ли приложение (зомби-контейнер).
- **hadolint** — статический анализ Dockerfile в CI.

**Релевантность DOLG (прямо в наш `Dockerfile`/`deploy/`):**
- База: `python:3.x-slim` (не alpine — у нас numpy/scipy/torch на glibc), пинить версию.
- `COPY requirements*.txt` → `pip install` ПЕРЕД `COPY` кода (кэш зависимостей — у нас тяжёлые либы).
- Мультистейдж: собирать колёса/ассеты в билд-стейдже, в финал — только нужное.
- Непривилегированный USER (есть в security backlog), HEALTHCHECK на `/healthz` (у нас уже есть `health.py`!),
  `.dockerignore` (`.venv`, `.git`, `media`, `*.log`), hadolint в pre-commit.

### 3. NGINX
[видео, 13:41](https://www.youtube.com/watch?v=2dJvLXy5RSE)

**TL;DR:** nginx (Игорь Сысоев, Rambler, 2004) решил проблему **C10K** асинхронной event-driven
архитектурой — где Apache (процесс на соединение) умирал на 10k, nginx держит сотни тысяч.

**Архитектура:** master-процесс (читает конфиг, не обрабатывает запросы) + worker'ы (≈ числу ядер),
каждый асинхронно держит тысячи соединений (event loop). Reload конфига без простоя
(новые воркеры стартуют, старые доживают запросы).

**Что умеет:**
- **Статика** — отдаёт HTML/CSS/JS/картинки вне конкуренции.
- **Reverse proxy** (основная роль): SSL/TLS-терминация (бэкенд не возится с сертификатами),
  буферизация медленных клиентов, единая точка входа, маршрутизация по путям/доменам.
- **Балансировщик** (разные алгоритмы), **кэш ответов** бэкенда (1000 запросов из кэша, не дёргая бэк).
- Производительность: 8 ядер/16 ГБ → 50-100k rps статики, 10-50k rps reverse-proxy, до 2 млн соединений.

**Где не тянет:** частый reload на больших кластерах; статичный конфиг (правка файла + reload);
service mesh (mTLS между сервисами, трейсинг, ретраи) — это Istio/Envoy, не nginx. В K8s Ingress
на базе nginx → `deprecated` в пользу Gateway API (но работать будет ещё долго).

**Релевантность DOLG (у нас `deploy/nginx.conf`):**
- Мы используем nginx именно как reverse proxy перед Django/Daphne — ровно сценарий из видео.
- Actionable: SSL-терминация на nginx, отдача `static/`+`media/` напрямую nginx'ом (не Django),
  кэш статики, gzip/brotli, буферизация. Для нашего масштаба (один сервер) nginx — идеален,
  mesh/Envoy не нужны.

### 4. Всё про базы данных
[видео, 19:46](https://www.youtube.com/watch?v=ApyFWo1Qimg)

**TL;DR:** БД — единственный **stateful** компонент: «приложения — скот, БД — сердце». Универсальной
базы нет, инструмент подбирается под профиль нагрузки.

**Классы баз:**
- **Реляционные (Postgres/MySQL)** — деньги/заказы/строгая структура, гарантии **ACID**. Postgres = стандарт.
- **NoSQL (MongoDB)** — нет жёсткой схемы (каталог разнородных товаров, профили с вложенностью); JSON-доки,
  но прожорлива и сложнее в админинге.
- **In-memory (Redis/Memcached)** — микросекунды, кэш/сессии/счётчики; энергозависимо — *ускоритель, не хранилище*.
- **Колоночные (ClickHouse)** — миллиарды строк аналитики/логов, сжатие ×десятки; жрёт все ядра.
- Взрослая архитектура — гибрид: Postgres хранит, Redis кэширует, ClickHouse анализирует.

**Надёжность:**
- **SPOF** (один сервер) недопустим → **репликация** (master пишет, реплики копируют через журнал **WAL**
  — «сначала запиши в журнал»). Реплика проигрывает WAL и становится копией.
- **Синхронная** (ждёт реплику — банки/биллинг, ≥3 серверов) vs **асинхронная** (быстро, риск потерять
  последнюю запись — соцсети/блоги). Вечный компромисс скорость↔надёжность.
- **Failover** автоматом (не руками в 3 ночи): **Patroni** + распределённый арбитр (etcd/Consul) — лидер
  держит ключ с TTL, при смерти ключ протухает, реплики гонятся за лидерством, победитель → master + переезд VIP/DNS.
- **Репликация ≠ бэкап!** `DROP` реплицируется на все сервера за миллисекунды. От человеческой ошибки — только бэкап.
  - Логический (дамп в текст — просто, но медленно: 1 ТБ = часы/сутки) vs физический (копия файлов + архив WAL →
    **PITR**, восстановление на точку во времени «за секунду до того как Вася дропнул»).
  - **RPO** (сколько данных готовы потерять) и **RTO** (сколько лежим при восстановлении) — задаёт бизнес.

**БД в Kubernetes:** можно (2026), но с умом — НЕ `Deployment`, а `StatefulSet`, а лучше **операторы**
(сами делают Patroni/TLS/бэкапы). On-prem → операторы; облако → managed-сервис. Большой нагруженный
монолит-БД → лучше VM (предсказуемость); 500 мелких БД / БД-на-PR → Kubernetes-фабрика.

**Golden signals БД (мониторить, не CPU):** активные соединения (+ **PgBouncer** как пулер, не пускать
приложение в БД напрямую); диск IOPS/очередь; lag реплики; блокировки; **здоровье бэкапов** (алёрт на
возраст последнего успешного архива!).

**Релевантность DOLG (наш переход SQLite→Postgres):**
- Подтверждает выбор Postgres (ACID для заказов/оплаты Stripe). См. чек-лист postgres-миграции в памяти.
- Для production: настроить WAL-архивацию + физический бэкап с PITR (security backlog: «бэкапы»),
  алёрт на возраст бэкапа, PgBouncer при росте соединений.
- Реплика/Patroni — оверкилл для диплома (один сервер), но знать для защиты («как бы масштабировал»).
- Redis у нас уже есть в планах (кэш/Channels) — ровно роль «ускорителя».

### 5. DevOps Roadmap 2026
[видео, 35:50](https://www.youtube.com/watch?v=a68hSZz0gAQ)

**TL;DR:** практичный DevOps-путь строится не от абстрактного списка технологий, а от рабочих задач:
версионировать конфиги, жить в Linux, понимать процессы/ресурсы/сеть, упаковывать приложения в Docker,
собирать CI/CD, затем переходить к Ansible, Kubernetes, мониторингу, логам и IaC.

**Порядок обучения из видео:**
- **Git** — начинать с него, потому что конфиги, pipeline, манифесты и документация тоже код.
- **Linux** — не просто читать, а жить в системе: терминал, файлы, права, редактор, сервисы.
- **Processes** — `ps`, PID, signals, zombie/orphan, `systemd`, unit-файлы, OOM killer, `/proc`.
- **Resource monitoring** — `top`/`htop`, load average, CPU, memory, `iowait`.
- **Disk** — `df`, `du`, inode exhaustion, ротация логов, поиск раздувшихся файлов.
- **Networking** — базовые модели, порты, DNS, маршрутизация, firewall; без этого Docker/K8s становятся магией.
- **Docker** — image/container, Dockerfile, volumes, networks, compose, registry, healthcheck.
- **CI/CD** — идеального pipeline нет: зависит от проекта, ветвления, окружений, тестов, релизной стратегии.
- **Ansible / IaC** — конфигурация серверов через idempotent playbooks, inventory, roles.
- **Kubernetes** — control plane, worker node, pod, deployment, statefulset, daemonset, jobs, configmap/secret,
  probes, requests/limits, services, ingress, PV/PVC, Helm.
- **Monitoring/logging** — Prometheus/Grafana, exporters, PromQL, dashboards, alerting; для логов ELK/OpenSearch или Loki.
- **Clouds/Terraform** — в конце, когда уже понятны Linux/Docker/CI/K8s; state хранить удалённо, например в S3.

**Релевантность DOLG после containerization-прохода:**
- Уже закрыто: Git/Markdown как рабочая дисциплина, Dockerfile, Compose, `web/asgi/worker`, Redis,
  nginx edge, Prometheus/Grafana, CI container job, production preflight.
- Следующий практический слой: локально поднять Docker Desktop/WSL2 и прогнать `docker compose config`,
  `docker build`, `docker compose up db redis web`, затем `curl /healthz/`.
- После Docker runtime: добавить hadolint/Trivy policy в CI, backup/PITR runbook для Postgres,
  Ansible bootstrap для VM вместо ручного `yc-bootstrap.sh`.
- Kubernetes пока не нужен для дипломного production, но roadmap полезен для защиты: можно объяснить,
  как DOLG эволюционирует от одного Compose-хоста к Helm/GitOps, не таща БД в кластер преждевременно.

**Локальный статус Docker на 2026-06-07:**
- `where docker` не находит Docker CLI.
- Docker Desktop не найден в `C:\Program Files\Docker\Docker`.
- VS Code установлен, но это не равно Docker Engine; Docker extension без daemon не даст `docker build`.
- `winget search Docker.DockerDesktop` видит пакет Docker Desktop 4.76.0, но установка из текущей Codex-сессии
  невозможна без UAC/admin (`IsAdmin=False`), installer зависает и был остановлен.
- Корректный следующий шаг: запустить терминал/installer от администратора, установить Docker Desktop,
  включить WSL2/VirtualMachinePlatform при запросе Windows, перезагрузить машину, затем проверить:
  `docker version`, `docker run --rm hello-world`, `docker compose version`.
