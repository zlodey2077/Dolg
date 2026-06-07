$ErrorActionPreference = "Stop"
$env:DEBUG = "True"
$env:DJANGO_SETTINGS_MODULE = "Dolg_PR.settings_test"

Write-Host "== Django system check =="
.\.venv\Scripts\python.exe manage.py check

Write-Host "== Test suite with coverage =="
.\.venv\Scripts\coverage.exe run manage.py test accounts shop orders Dolg_APP knowledge moderation
.\.venv\Scripts\coverage.exe report -m
