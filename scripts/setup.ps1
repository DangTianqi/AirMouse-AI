$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create venv. Install Python 3.11 x64.' }
}
$taskPython = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (Test-Path 'requirements-lock.txt') {
    & $taskPython -m pip install -r requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Cannot install locked dependencies.' }
}
& $taskPython -m pip install -e '.[dev]'
if ($LASTEXITCODE -ne 0) { throw 'Cannot install project dependencies.' }
& $taskPython scripts/download_model.py
if ($LASTEXITCODE -ne 0) { throw 'Model download or validation failed.' }
Write-Host 'Ready. Run: .\.venv\Scripts\python.exe -m airmouse_ai'
