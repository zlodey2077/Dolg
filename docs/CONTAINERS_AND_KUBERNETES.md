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

To only create the local env file and validate Compose without a running Docker
daemon:

```powershell
scripts/docker_compose_up.ps1 -ConfigOnly
```

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

One-command local flow:

```powershell
scripts/k8s_local_up.ps1
```

The script validates Kubernetes manifests, builds `dolg:local`, applies
`deploy/k8s`, waits for the migration Job and rollouts, then prints the current
pods/services/PVCs.

Open the app through port-forwarding:

```powershell
kubectl -n dolg port-forward svc/dolg-nginx 8080:80
```

Then open `http://localhost:8080/`.

To start the port-forward inside the same foreground script run:

```powershell
scripts/k8s_local_up.ps1 -PortForward
```

For kind, load the image before applying:

```powershell
scripts/k8s_local_up.ps1 -KindCluster <cluster-name>
```

Stop Kubernetes objects:

```powershell
scripts/k8s_local_down.ps1
```

Stop workloads but keep PVC data:

```powershell
scripts/k8s_local_down.ps1 -KeepPvcs
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
- The base namespace enforces Pod Security `baseline` and warns/audits
  `restricted`. Workloads drop Linux capabilities and use `RuntimeDefault`
  seccomp.
- Django pods run as uid/gid `1000`, mount writable PVCs through `fsGroup`, and
  use startup/readiness/liveness probes.
- Prometheus reads `METRICS_TOKEN` through a mounted Kubernetes Secret file,
  not a literal token in the Prometheus ConfigMap.
- `dolg-web` has a PodDisruptionBudget so voluntary disruptions keep at least
  one web replica available.
- `deploy/k8s/networkpolicy.yaml` starts with default-deny and opens only the
  DOLG flows needed for nginx, Django, ASGI, Postgres, Redis, Prometheus, and
  Grafana.

## 6. What remains

- OS/runtime: start `com.docker.service` through UAC/admin once and confirm
  `docker info` returns the server version.
- If Docker Desktop hangs while the Docker service is stopped or `vmcompute` is
  stopped, run `scripts/bootstrap_docker_desktop.ps1 -StartVisible` and accept
  the UAC prompt. The bootstrap checks WSL, `vmcompute`, `hns`,
  `LxssManager`, `docker-users`, and the Docker Desktop service.
- Runtime smoke: run `scripts/docker_compose_up.ps1` and verify the app,
  Prometheus, and Grafana URLs.
- Kubernetes smoke: enable Docker Desktop Kubernetes or use kind/minikube, then
  run `scripts/k8s_local_up.ps1`.
- Production hardening: replace local literals with a real secret manager,
  publish immutable images to a registry, add Helm values per environment,
  move from Pod Security `baseline` to `restricted` after runtime smoke, and
  document Postgres backup/PITR.
