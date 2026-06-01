# DOLG на Яндекс Compute Cloud — пошаговая инструкция

2026-06-01 — production VM deployment для дипломной защиты.

## Что получишь в итоге

- Публичный URL `http://<VM-IP>/` (или `https://<your-domain>/` если есть)
- Django + Postgres + nginx в Docker
- Auto-restart при перезагрузке VM (systemd)
- 60 дней триал-кредитов от Яндекса (~4000₽)
- После триала — ~600-1500₽/мес (можно отключить)

## Стоимость

| Конфигурация | Цена | Подходит для |
|---|---|---|
| 2 vCPU / 2 GB RAM / 20 GB SSD | ~600₽/мес | защита диплома (минимум) |
| 2 vCPU / 4 GB RAM / 30 GB SSD | ~1100₽/мес | комфортно с playwright |
| Прерываемая (preemptible) | -70% | НЕ для prod (VM выключается раз в 24ч) |

Триал даёт 4000₽ грантов на 60 дней — хватит на 4-6 месяцев работы базовой конфигурации.

---

## Шаг 1. Аккаунт Яндекса (5 мин)

1. https://yandex.cloud → Войти/Регистрация
2. Логин через ЯндексID (без отдельной почты-верификации, если у тебя уже есть Яндекс-почта)
3. Принять условия → **Активировать триальный период**:
   - Привязать карту (любая дебетовая, **списания не будет** в триале)
   - Получишь 4000₽ грантов на 60 дней

## Шаг 2. Создать SSH ключ (1 мин, на твоём Windows)

```cmd
ssh-keygen -t ed25519 -C "dolg-yc"
```

Жми Enter три раза (default путь, без пароля).

Скопируй **публичный** ключ — пригодится:
```cmd
type %USERPROFILE%\.ssh\id_ed25519.pub
```

## Шаг 3. Создать VM (3 мин)

1. https://console.cloud.yandex.ru → **Compute Cloud** → **Виртуальные машины** → **Создать ВМ**
2. **Имя:** `dolg-prod`
3. **Зона доступности:** любая (`ru-central1-a` обычно дешевле)
4. **Образ:** Ubuntu 22.04 LTS
5. **Вычислительные ресурсы:**
   - Платформа: Intel Cascade Lake
   - vCPU: **2**, гарантированная доля **100%**
   - RAM: **2 ГБ** (или 4, если хочешь playwright)
6. **Хранилище:** 20 ГБ SSD (network-ssd)
7. **Сеть:**
   - Подсеть: default
   - Публичный IP: **Автоматически** (зарезервированный лучше платный)
8. **Доступ:**
   - Логин: `ubuntu`
   - SSH-ключ: вставь содержимое `id_ed25519.pub` из Шага 2
9. **Создать ВМ** → 30 сек ждёшь → копируешь публичный IP

## Шаг 4. Подключиться по SSH (10 сек)

```cmd
ssh ubuntu@<VM-PUBLIC-IP>
```

Принять fingerprint (yes), готово.

## Шаг 5. Запустить bootstrap (5-10 мин на установку Docker и зависимостей)

В SSH-сессии VM выполни:

```bash
curl -fsSL https://raw.githubusercontent.com/zlodey2077/Dolg/main/deploy/yc-bootstrap.sh -o bootstrap.sh
chmod +x bootstrap.sh
./bootstrap.sh
```

Скрипт сам:
- Установит Docker + Compose + Git + UFW + Certbot
- Откроет порты 22, 80, 443
- Клонирует репо в `/opt/dolg/`
- Сгенерирует `.env` со случайными `SECRET_KEY` и паролем Postgres
- Запустит `docker compose up` (~5 мин на сборку образа)
- Создаст systemd unit `dolg.service` для auto-restart

### Если нужно указать домен заранее

```bash
DOMAIN=mydolg.example.com ./bootstrap.sh
```

## Шаг 6. Проверить что работает

```bash
docker ps
# Должно быть 3 контейнера: dolg_db, dolg_web, dolg_nginx

curl -i http://localhost/
# Должно вернуть 200 OK + HTML с DOLG

docker logs dolg_web --tail 50
# Логи Django
```

На своём компе в браузере открой: **http://<VM-PUBLIC-IP>/**

## Шаг 7. Дополнить .env секретами

```bash
cd /opt/dolg
nano .env
```

Добавь свои значения (если нужны):
- `HF_TOKEN` — для загрузки моделей с HuggingFace
- `STRIPE_PUBLIC_KEY` / `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET`
- `ANTHROPIC_API_KEY` — для AI чата
- `SENTRY_DSN` — для error tracking

После изменений:
```bash
sudo systemctl restart dolg.service
# или
sudo docker compose -f deploy/docker-compose.yml --env-file .env up -d
```

## Шаг 8. Создать superuser

```bash
sudo docker compose -f /opt/dolg/deploy/docker-compose.yml --env-file /opt/dolg/.env exec web python manage.py createsuperuser
```

Зайти в админку: **http://<VM-PUBLIC-IP>/admin/**

---

## Шаг 9 (опционально). Свой домен + HTTPS (15 мин)

### 9.1. Купить домен

- https://timeweb.com (от 199₽/год для .ru)
- https://reg.ru
- Cloudflare Registrar (без накруток)

### 9.2. Привязать к VM

В DNS-настройках домена:
- A-запись `@` → `<VM-PUBLIC-IP>`
- A-запись `www` → `<VM-PUBLIC-IP>`

Подождать 5-30 мин пока DNS прокатится.

### 9.3. SSL через Let's Encrypt

```bash
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com \
    --non-interactive --agree-tos -m your-email@mail.ru
```

Certbot автоматически перенастроит nginx, поставит cron для авто-обновления сертификата.

### 9.4. Обновить ALLOWED_HOSTS

```bash
nano /opt/dolg/.env
# ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com,<VM-IP>,localhost
# CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
sudo systemctl restart dolg.service
```

---

## Обновление кода после push в GitHub

```bash
ssh ubuntu@<VM-IP>
cd /opt/dolg
./deploy/yc-update.sh
```

Сам сделает:
- `git pull`
- rebuild docker image
- run migrations
- zero-downtime restart web-контейнера

## Логи и мониторинг

```bash
# Все логи web
docker logs dolg_web -f

# Логи только за последний час
docker logs dolg_web --since 1h

# Логи nginx
docker logs dolg_nginx -f

# Использование ресурсов
htop  # CPU/RAM
df -h  # диск
docker stats  # по контейнерам
```

## Backup БД (раз в день — рекомендуется)

```bash
crontab -e
# Добавить строку:
0 3 * * * docker exec dolg_db pg_dump -U dolg dolg | gzip > /home/ubuntu/backup-$(date +\%Y\%m\%d).sql.gz
```

---

## Что делать после защиты

1. Если деньги триала ещё есть — оставь VM работать
2. После триала Яндекс начнёт списывать (предупредит за 7 дней)
3. **Чтобы не платить:**
   - Выключи VM (Console → ВМ → Остановить) — диск всё равно тарифицируется ~50₽/мес
   - Удали VM полностью + диск, GitHub + локальный snapshot всё сохранят

---

## Troubleshooting

### `docker compose` падает на сборке
RAM 2GB мало — VM может OOM. Увеличь до 4GB в Console → ВМ → **Изменить конфигурацию**.

### 502 Bad Gateway в браузере
```bash
docker logs dolg_web --tail 100
# Чаще всего: ALLOWED_HOSTS не включает IP VM. Поправь .env и restart.
```

### Postgres не стартует
```bash
docker logs dolg_db --tail 50
# Возможно неправильный пароль в .env. Удали volume и пересоздай:
docker compose down -v  # ОСТОРОЖНО — удаляет БД!
docker compose up -d
```

### Хочу удалить всё и начать заново
```bash
cd /opt/dolg
sudo systemctl stop dolg
sudo docker compose -f deploy/docker-compose.yml --env-file .env down -v
sudo rm -rf /opt/dolg
./bootstrap.sh  # из home directory
```

---

## Связано

- [deploy/yc-bootstrap.sh](../deploy/yc-bootstrap.sh) — установочный скрипт
- [deploy/yc-update.sh](../deploy/yc-update.sh) — скрипт обновления
- [deploy/docker-compose.yml](../deploy/docker-compose.yml) — production stack
- [deploy/Dockerfile](../deploy/Dockerfile) — Django образ
- [docs/DEPLOY.md](DEPLOY.md) — общая стратегия бэкапов
