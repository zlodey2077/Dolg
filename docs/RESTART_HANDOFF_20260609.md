# Restart Handoff - 2026-06-09

## Why reboot now

- WSL was updated successfully, but `wslinstaller.exe` remained stuck without non-admin permission to terminate it.
- Reboot should clear the installer wrapper and let Docker Desktop see the updated WSL kernel cleanly.
- System stability improved after moving large data off `C:` and disabling several autostarts.

## Current facts

- `C:` free space after cleanup: about 137 GB.
- WSL update installed successfully according to MSI logs.
- `wsl --version` reported:
  - WSL: 2.7.3.0
  - Kernel: 6.6.114.1-1
- Docker CLI is installed: 29.5.2.
- Docker daemon was not running because `com.docker.service` could not be started from a non-elevated shell.
- Docker/Compose/Kubernetes static checks passed.
- `scripts/docker_compose_up.ps1 -ConfigOnly` creates `deploy/.env.docker.local` and validates Compose without a live daemon.
- Runtime Docker smoke still requires Docker Desktop service to be started through UAC/admin.
- Battery is heavily worn:
  - Designed capacity: 37000 mWh
  - Full charged capacity: 8510 mWh
  - Health: about 23%
- Power diagnostics report:
  - `D:\Cleanup_Quarantine\2026-06-09_C_drive_offload\system_optimization\power_hardware_diagnostics.md`

## User action after reboot

1. Start Docker Desktop normally.
2. If Windows asks for permissions, approve them.
3. Wait until Docker Desktop says the engine is running.
4. Keep the charger connected and avoid moving the laptop during the first Docker check.
5. If Docker Desktop still hangs, run:

```powershell
scripts/bootstrap_docker_desktop.ps1 -StartVisible
```

## Codex first checks after reboot

Run these before changing project files:

```powershell
Get-Process -Name wslinstaller,msiexec,wsl -ErrorAction SilentlyContinue
wsl --version
wsl --status
Get-Service com.docker.service
docker version
docker ps
```

Expected:

- No stuck `wslinstaller.exe`.
- WSL responds without kernel update errors.
- Docker daemon responds.

## Project work front

### 1. Local startup reliability

- Re-run `start_local.bat`.
- Confirm startup time target: ideally under 30 seconds.
- Check:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/healthz -UseBasicParsing
```

- If startup regresses, profile:

```powershell
.venv\Scripts\python.exe scripts\profile_django_checks.py
```

### 2. Docker baseline

- Build the app image.
- Run the app through Docker Compose.
- Verify health endpoint from containerized app.
- Fix Dockerfile/Compose issues found after the real engine starts.
- Keep Docker setup lightweight because this laptop is resource-constrained.

Likely checks:

```powershell
docker compose config
docker compose build
docker compose up
```

### 3. Compose hardening

- Add or verify healthchecks.
- Verify `.env.example` and local env handling.
- Ensure migrations are explicit and predictable.
- Check static files/media volumes.
- Check non-root container user where practical.
- Add resource-friendly defaults for local development.

### 4. Kubernetes baseline

- Keep Kubernetes optional for now; Docker Desktop Kubernetes may be heavy for this machine.
- Prefer a minimal `deploy/k8s` baseline before enabling a local cluster:
  - namespace
  - deployment
  - service
  - configmap placeholders
  - secret placeholders
  - readiness/liveness probes
  - resource requests/limits
- Decide later between Docker Desktop Kubernetes and `kind`, based on machine stability.

### 5. Documentation

- Update `docs/CONTAINERS_AND_KUBERNETES.md` with actual tested commands.
- Update `docs/LOCAL_SETUP.md` if startup commands changed.
- Keep system diagnostics out of project docs except short operational notes.

### 6. Git hygiene

- Before committing, inspect existing staged files:
  - `.claude/settings.local.json`
  - `docs/VIDEO_BACKLOG.md`
- Do not mix unrelated old staged changes into Docker/Kubernetes commits unless explicitly approved.
- Commit container/devops changes separately from system-diagnostics notes.

## Later, after Docker/Kubernetes

- Return to CAD/AutoCAD research plan and notes.
- Add CAD programmatic scheme-building mode that works together with the vector editor:
  - one shared drawing/entity model for manual vector editing and generated operations;
  - CAD-JSON/DSL operations such as `add_component`, `add_wire`, `route_wire`, `set_layer`, `array`, `dimension`;
  - programmatic operations must render as normal vector objects;
  - vector edits should update the canonical scheme model where possible;
  - AI must generate constrained operations/CAD-JSON first, not direct canvas mutations.
- Continue video-note backlog from the DevOps and AutoCAD references.
- Resume project cleanup only after container baseline is stable.
