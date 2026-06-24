#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash scripts/install_docker_engine_linux.sh"
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemd is required for this installer."
  exit 1
fi

. /etc/os-release

install_debian_like() {
  apt-get update
  apt-get install -y ca-certificates curl gnupg lsb-release
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg

  arch="$(dpkg --print-architecture)"
  codename="${VERSION_CODENAME:-$(lsb_release -cs)}"
  echo \
    "deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/${ID} ${codename} stable" \
    >/etc/apt/sources.list.d/docker.list

  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
}

install_fedora_like() {
  dnf -y install dnf-plugins-core
  dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
  dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
}

case "${ID_LIKE:-${ID}}" in
  *debian*|*ubuntu*)
    install_debian_like
    ;;
  *fedora*|*rhel*)
    install_fedora_like
    ;;
  *)
    echo "Unsupported distro: ${PRETTY_NAME:-${ID}}"
    echo "Supported: Ubuntu/Debian/Fedora-like."
    exit 1
    ;;
esac

systemctl enable --now docker

target_user="${SUDO_USER:-}"
if [[ -n "${target_user}" && "${target_user}" != "root" ]]; then
  usermod -aG docker "${target_user}"
  echo "Added ${target_user} to docker group. Log out/in once before using docker without sudo."
fi

docker version
docker compose version
docker run --rm hello-world
