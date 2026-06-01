$ErrorActionPreference = "Stop"

$env:DJANGO_SETTINGS_MODULE = "Dolg_PR.settings_test"
$env:DEBUG = "True"
$env:RUN_BROWSER_E2E = "1"

Write-Host "== Browser e2e smoke: simulation, errors, BOM, exports, CAD, projects, AC/DC/TRAN, persistence, visual layout, modals, warnings =="
.\.venv\Scripts\python.exe manage.py test Dolg_APP.tests_browser --verbosity 1
