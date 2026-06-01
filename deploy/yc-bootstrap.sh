#!/usr/bin/env bash
# ==============================================================================
# DOLG bootstrap для Яндекс Compute Cloud VM (Ubuntu 22.04 LTS).
#
# Что делает:
#   1. Обновляет систему
#   2. Ставит Docker + Docker Compose + Git
#   3. Клонирует репо
#   4. Создаёт .env (требует ввода SECRET_KEY и пароля Postgres)
#   5. Запускает docker compose up -d
#   6. Конфигурирует UFW (firewall) — открывает 80, 443, 22
#   7. Создаёт systemd unit для auto-restart при перезагрузке VM
#   8. (Опционально) Certbot для SSL — запрашивает domain
#
# Использование:
#   ssh ubuntu@<vm-public-ip>
#   curl -fsSL https://raw.githubusercontent.com/zlodey2077/Dolg/main/deploy/yc-bootstrap.sh | bash
#
# или вручную:
#   wget https://raw.githubusercontent.com/zlodey2077/Dolg/main/deploy/yc-bootstrap.sh
#   chmod +x yc-bootstrap.sh
#   ./yc-bootstrap.sh
# ==============================================================================

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/zlodey2077/Dolg.git}"
PROJECT_DIR="${PROJECT_DIR:-/opt/dolg}"
DOMAIN="${DOMAIN:-}"

log() { printf "\n\033[1;36m▶ %s\033[0m\n" "$*"; }
err() { printf "\033[1;31m✗ %s\033[0m\n" "$*" >&2; }

# ── 1. Проверки ─────────────────────────────────────────────────────────────
[[ "$(id -u)" -eq 0 ]] && err "Не запускай от root. Используй ubuntu user + sudo." && exit 1
command -v sudo >/dev/null || { err "sudo не установлен"; exit 1; }

log "[1/7] Обновление системы"
sudo apt-get update -qq
sudo apt-get upgrade -y -qq

log "[2/7] Установка Docker, Compose, Git, ufw, certbot"
sudo apt-get install -y -qq \
    ca-certificates curl gnupg lsb-release git ufw \
    python3-certbot-nginx
# Docker repo
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update -qq
sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"

log "[3/7] Firewall (UFW)"
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

log "[4/7] Клонирование репо в $PROJECT_DIR"
if [[ -d "$PROJECT_DIR" ]]; then
    sudo chown -R "$USER:$USER" "$PROJECT_DIR"
    cd "$PROJECT_DIR" && git pull
else
    sudo mkdir -p "$PROJECT_DIR"
    sudo chown "$USER:$USER" "$PROJECT_DIR"
    git clone "$REPO_URL" "$PROJECT_DIR"
fi
cd "$PROJECT_DIR"

log "[5/7] Настройка .env"
if [[ ! -f .env ]]; then
    cp .env.example .env
    SECRET=$(openssl rand -base64 48 | tr -d '\n')
    PG_PASS=$(openssl rand -base64 24 | tr -d '/+=\n' | head -c 32)
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET|" .env
    sed -i "s|^DEBUG=.*|DEBUG=False|" .env
    sed -i "s|^POSTGRES_DB=.*|POSTGRES_DB=dolg|" .env
    sed -i "s|^POSTGRES_USER=.*|POSTGRES_USER=dolg|" .env
    sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$PG_PASS|" .env
    if [[ -n "$DOMAIN" ]]; then
        sed -i "s|^ALLOWED_HOSTS=.*|ALLOWED_HOSTS=$DOMAIN,localhost,127.0.0.1|" .env
        sed -i "s|^CSRF_TRUSTED_ORIGINS=.*|CSRF_TRUSTED_ORIGINS=https://$DOMAIN|" .env
    else
        PUBLIC_IP=$(curl -s ifconfig.me || echo "127.0.0.1")
        sed -i "s|^ALLOWED_HOSTS=.*|ALLOWED_HOSTS=$PUBLIC_IP,localhost,127.0.0.1|" .env
    fi
    log "  Сгенерированы случайный SECRET_KEY и пароль Postgres (см. .env)"
else
    log "  .env уже существует, не перезаписываю"
fi
log "  ВАЖНО: открой $PROJECT_DIR/.env и добавь HF_TOKEN / STRIPE_* / ANTHROPIC_API_KEY если нужны"

log "[6/7] Запуск docker compose"
sudo docker compose -f deploy/docker-compose.yml --env-file .env up -d --build

log "[7/7] Systemd unit для auto-restart"
sudo tee /etc/systemd/system/dolg.service >/dev/null <<EOF
[Unit]
Description=DOLG Django stack (docker compose)
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/bin/docker compose -f deploy/docker-compose.yml --env-file .env up -d
ExecStop=/usr/bin/docker compose -f deploy/docker-compose.yml down

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now dolg.service

log "✓ Готово!"
echo
echo "  Проверь:"
echo "    docker ps                                   # 3 контейнера: dolg_db, dolg_web, dolg_nginx"
echo "    curl -i http://localhost/                   # должен ответить Django"
echo "    docker logs dolg_web --tail 50              # логи приложения"
echo
PUBLIC_IP=$(curl -s ifconfig.me || echo '<vm-ip>')
echo "  Открой в браузере: http://$PUBLIC_IP/"
echo
if [[ -n "$DOMAIN" ]]; then
    log "Опционально: SSL (Let's Encrypt)"
    echo "    sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m admin@$DOMAIN"
fi
echo
log "Для обновления:  cd $PROJECT_DIR && ./deploy/yc-update.sh"
