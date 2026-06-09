# Startup reliability audit

Дата: 2026-06-09

Цель: вернуть локальный запуск DOLG к предсказуемому сценарию "нажал `start_local.bat`, получил `http://127.0.0.1:8000/`", без зависания на hot-reload, пустых логов и ложных OK-статусов.

## Симптом

Текущий сбой:

- `manage.py migrate --check` иногда не успевает за 30 секунд.
- Launcher продолжает старт, но печатает ложное `[OK] Миграции применены`.
- `start_local.bat` запускает `start_server.py --local --hot`.
- Hot-mode через `jurigged` на Windows выводит терминальные capability-запросы вида `ESC P + q ... ESC \` и `ESC[6n`.
- Django не становится готовым за 90 секунд, fallback уходит в plain, но `.tmp_django.log` иногда уже пустой или перезаписан.

## Подтвержденные подозреваемые

1. **Hot/jurigged как дефолт локальной кнопки.**
   `start_local.bat` запускал `--hot`, хотя для ежедневной работы нужен стабильный plain `runserver --noreload`. Hot полезен как ручной эксперимент, но не как default.

2. **Терминальные control-sequences от hot-stack.**
   Строки `ESC P + q...` и `ESC[6n` похожи на запросы терминальных capabilities. В обычном Django plain-mode они не нужны и не должны попадать в окно launcher-а.

3. **Ложный статус миграций.**
   После `timeout/error` код продолжал идти в общий `else` и писал `[OK] Миграции применены`. Это маскировало реальное состояние preflight.

4. **Лог Django перезаписывался при fallback.**
   Hot-попытка и plain-fallback писали в один файл через `w`, поэтому хвост лога мог потерять первопричину.

5. **Django autoreloader под внешним launcher-ом.**
   Уже исправлено ранее: plain-mode стартует с `--noreload`, чтобы не плодить parent/child процессы и не оставлять старый код на порту.

6. **Daphne/ASGI runserver запускал system checks.**
   Даже plain-команда `runserver --skip-checks --noreload` может уходить в `Performing system checks...`, если активен `daphne` runserver. One-click launcher теперь ставит `DOLG_SKIP_ASGI=1` и использует обычный WSGI runserver.

7. **Healthz зависел от URLConf.**
   `/healthz` был зарегистрирован первым URL, но импорт корневого `urlpatterns` всё равно тянул все `include(...)`. Добавлен ранний `HealthzMiddleware`, чтобы readiness/liveness отвечали до тяжелой маршрутизации.

8. **Тяжелые импорты на старте.**
   Уже исправлено ранее для `openpyxl`: импорт перенесен внутрь XLSX-export handler. Иначе `openpyxl -> numpy` мог добавлять секунды к любому `manage.py`.

9. **`migrate --check` запускал system checks и management-command слой.**
   Для preflight это лишнее: system checks импортируют URLConf, `Dolg_APP.views`, `reportlab`, rule-AI сервисы и читают шаблоны. Launcher теперь использует fast migration probe через `MigrationExecutor`, а `manage.py migrate --noinput --skip-checks` запускает только когда реально есть pending migrations.

10. **Eager Celery import.**
   Уже исправлено ранее: `Dolg_PR.__init__` больше не импортирует Celery app при простом `import Dolg_PR.settings`.

11. **Системная нагрузка Windows.**
   Docker Desktop, Defender, VS Code/Jedi и браузер могут временно раздувать 10-15 секунд до 30+ секунд. Это не главный баг launcher-а, но влияет на таймауты.

12. **Optional app probes не нужны для one-click локального запуска.**
   `django_prometheus`, `axes`, `csp`, `silk` остаются доступны для обычных/prod-команд, но launcher ставит `DOLG_SKIP_OPTIONAL_APP_PROBES=1`, чтобы не тратить старт на лишние probe-импорты.

## Кто может накосячить дальше

- Любые module-level импорты тяжелых библиотек в `views.py`, `urls.py`, `admin.py`, `apps.py`: `numpy`, `pandas`, `scipy`, `matplotlib`, `openpyxl`, `reportlab`, `qrcode`, `playwright`.
- `AppConfig.ready()` с дорогими side effects. Сейчас там только signals/checks, но это место нужно держать легким.
- Новые URL imports, которые подтянут ML/CAD/simulation stack при `manage.py check`, `migrate --check` или `runserver`.
- Docker Desktop/WSL во время локального Python-startup: хорошо для контейнеров, но может съедать CPU/RAM на Windows-хосте.
- Windows Defender, сканирующий `.venv`, `db.sqlite3`, `media`, generated reports и Docker layers.
- Любой launcher, который снова включит `--hot` или Django autoreload по умолчанию.
- Shell/IDE вывод, случайно записанный в config-файлы. Такое уже случалось с `pyproject.toml`, и это ломает инструменты до старта Django.

## Новая политика запуска

- `start_local.bat`: только стабильный `start_server.py --local --no-hot`.
- Hot-mode: ручной режим для точечной разработки:
  `.\.venv\Scripts\python.exe start_server.py --local --hot`
- Plain-mode: всегда `manage.py runserver 127.0.0.1:8000 --skip-checks --noreload`.
- One-click launcher: `DOLG_SKIP_ASGI=1`, чтобы `daphne` не подменял runserver и не запускал дорогие checks.
- One-click launcher: `DOLG_SKIP_OPTIONAL_APP_PROBES=1`, чтобы optional observability/security/dev apps не импортировались без явной необходимости.
- Migration preflight: fast `MigrationExecutor` probe, короткий timeout по умолчанию 10 секунд, timeout/error предупреждает и продолжает только в non-strict режиме, но больше не печатает ложный OK.
- Readiness: `/healthz` отвечает через ранний middleware до URLConf, поэтому Docker/K8s/launcher smoke не ждут импорт всех views.
- `.tmp_django.log`: очищается один раз перед стартом, затем обе попытки `hot/plain` пишутся append-ом с заголовком команды.
- При hot-fallback launcher чистит orphan-процессы и порт перед plain-попыткой.
- Окружение launcher-а гасит цвет и terminal-probes через `TERM=dumb`, `NO_COLOR=1`, `PY_COLORS=0`, `CLICOLOR=0`.

## Быстрые проверки после правок

```powershell
.\.venv\Scripts\python.exe -m py_compile start_server.py
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe scripts\profile_django_checks.py
.\.venv\Scripts\python.exe start_server.py --local --no-hot --no-browser
```

Ожидаемое поведение: порт 8000 освобождается, миграции проверяются мягко, Django поднимается в plain-mode, `/healthz` отвечает, `.tmp_django.log` содержит команду запуска и реальный хвост при ошибке.

## Замеры после оптимизации

Локальный замер на Windows-хосте 2026-06-09:

- `manage.py check`: 9-16 секунд вместо наблюдавшихся ~50 секунд.
- `scripts/profile_django_checks.py`: `django.setup` ~6-8 секунд, сами registered checks ~3-4 секунды.
- Fast migration probe в launcher-е: ~6-7 секунд вместо плавающего `manage.py migrate --check --skip-checks` до 29+ секунд и occasional timeout.
- Launcher smoke `start_server.py --local --no-hot --no-browser`: TCP ready за ~13.6 секунды, `/healthz` вернул `200` с `database/cache: ok`.

Оставшийся главный источник разброса: Windows filesystem / Defender / VS Code Jedi / Docker Desktop background load. Кодовый hot path теперь не зависит от `jurigged`, `daphne runserver`, тяжелого URLConf для healthz и медленного management-command migration check.
