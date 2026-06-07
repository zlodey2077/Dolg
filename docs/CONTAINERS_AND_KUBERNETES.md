# Containers and Kubernetes runbook

This project now has three container layers:

- Docker Desktop bootstrap for Windows.
- Docker Compose for local/prod-like runs.
- Kubernetes manifests in `deploy/k8s` for Docker Desktop Kubernetes, kind,
  minikube, or a small cluster.

## 1. Windows Docker Desktop

Check the current machine:

```powershell
docker version
docker compose version
kubectl version --client
```

If `docker version` shows a client but cannot connect to
`npipe:////./pipe/docker_engine`, start the Windows service and Desktop app:

```powershell
scripts/bootstrap_docker_desktop.ps1 -StartVisible
```

If the script relaunches with UAC, accept it. Docker Desktop service start is a
Windows admin operation; a non-admin shell cannot complete that part. After the
first successful start, normal project commands should work from the usual
terminal.

## 2. Docker Compose local run

From the repository root:

```powershell
scripts/docker_compose_up.ps1
```

The script creates ignored local secrets in `deploy/.env.docker.local`, validates
the compose file, builds the image, starts Postgres/Redis/Django/nginx/
Prometheus/Grafana, and waits for `/healthz`.

URLs:

- App: `http://localhost:8080/`
- Prometheus: `http://localhost:9090/`
- Grafana: `http://localhost:3000/`

Stop:

```powershell
scripts/docker_compose_down.ps1
```

Stop and remove volumes:

```powershell
scripts/docker_compose_down.ps1 -Volumes
```

## 3. Kubernetes local run

Build a local image visible to the cluster:

```powershell
docker build -f deploy/Dockerfile -t dolg:local .
```

Validate and apply:

```powershell
python scripts/check_k8s_static.py
kubectl kustomize deploy/k8s
kubectl apply -k deploy/k8s
kubectl -n dolg wait --for=condition=complete job/dolg-migrate --timeout=180s
kubectl -n dolg rollout status deploy/dolg-web
kubectl -n dolg rollout status deploy/dolg-asgi
kubectl -n dolg rollout status deploy/dolg-worker
kubectl -n dolg port-forward svc/dolg-nginx 8080:80
```

Then open `http://localhost:8080/`.

For kind, load the image before applying:

```powershell
kind load docker-image dolg:local
```

## 4. Static checks

These do not require a live Docker daemon:

```powershell
python scripts/check_docker_static.py
python scripts/check_k8s_static.py
docker compose --env-file deploy/.env.docker.local -f deploy/docker-compose.yml config
```

`docker compose config` requires the env file because production-like compose
fails fast on missing secrets.

## 5. Production notes

- Do not use `deploy/.env.docker.local` outside local smoke runs.
- Replace Kubernetes `secretGenerator` literals with a real secret supply:
  external Secret, SealedSecret, SOPS, cloud secret manager, or CI/CD injection.
- Replace `dolg:local` with an immutable registry tag.
- Keep `METRICS_TOKEN` synchronized between Django and Prometheus.
- Run migrations as an explicit release job before scaling web replicas.
