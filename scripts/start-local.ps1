$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Installing frontend deps..."
Set-Location "$root\frontend"
if (-not (Test-Path "node_modules")) { npm install }
npm run build

Write-Host "Installing backend deps..."
Set-Location "$root\backend"
if (-not (Test-Path ".venv")) { python -m venv .venv }
& "$root\backend\.venv\Scripts\python.exe" -m pip install -r requirements.txt

Write-Host "Starting API + UI on http://localhost:8910"
& "$root\backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8910
