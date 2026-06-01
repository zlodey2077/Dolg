# DOLG production image — Python 3.14 slim + gunicorn.
# Multi-stage не используем: NumPy/SciPy/Matplotlib ставятся wheel-пакетами,
# одностадийная сборка проще для диплома и демо.

FROM python:3.14-slim

# Системные зависимости:
#   - libpq5  — рантайм Postgres-клиента (psycopg2-binary его подтягивает,
#               но явно фиксируем для предсказуемости)
#   - curl    — healthcheck
#   - fonts-dejavu — cyrillic-шрифт для PDF-генерации (см.
#                    shop/views.py:_register_pdf_cyrillic_fonts)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 curl fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=Dolg_PR.settings

WORKDIR /app

# Зависимости отдельным слоем — кеш переиспользуется при правке кода.
COPY requirements.txt requirements-prod.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install -r requirements-prod.txt

# Копируем проект. Перечисление каталогов вместо COPY . . — не тащим
# случайно .git, .venv, db.sqlite3 (см. .dockerignore тоже).
COPY Dolg_APP/    Dolg_APP/
COPY Dolg_PR/     Dolg_PR/
COPY accounts/    accounts/
COPY orders/      orders/
COPY shop/        shop/
COPY knowledge/   knowledge/
COPY scripts/     scripts/
COPY manage.py    ./
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

# Нерут-юзер — best practice для прод-контейнеров.
RUN useradd --uid 1000 --shell /bin/bash --create-home dolg \
    && chown -R dolg:dolg /app
USER dolg

# Volume для media + staticfiles. STATIC_ROOT собирается в /app/staticfiles
# командой collectstatic из entrypoint, MEDIA_ROOT = /app/media.
VOLUME ["/app/media", "/app/staticfiles"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/healthz/ || exit 1

ENTRYPOINT ["./entrypoint.sh"]
CMD ["gunicorn", "Dolg_PR.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--timeout", "60"]
