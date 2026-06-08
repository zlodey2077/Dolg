# DOLG Kubernetes base

This directory is a local/demo Kubernetes base for Docker Desktop Kubernetes,
kind, minikube, or a small VM cluster. It is intentionally self-contained:
Postgres, Redis, Django WSGI, Django ASGI, Celery, nginx, Prometheus, and
Grafana are represented as Kubernetes objects.

Local flow from the repository root:

```powershell
scripts/bootstrap_docker_desktop.ps1
scripts/k8s_local_up.ps1
kubectl -n dolg port-forward svc/dolg-nginx 8080:80
```

Open `http://localhost:8080/`.

Important production notes:

- Replace the `secretGenerator` literals in `kustomization.yaml` with an
  external Secret manager, SealedSecret, SOPS, or cluster-native secret supply.
- Build and push a real image tag, then replace `dolg:local`.
- The local Prometheus token is a demo value. Rotate it for any non-local
  environment. Prometheus reads it from the `dolg-secret` mounted file.
- The migration Job is simple and explicit. For GitOps/Helm, make the Job name
  release-specific or manage it as a hook.
- `dolg-web` has a PodDisruptionBudget and app pods use startup/readiness/
  liveness probes for safer rollouts.
