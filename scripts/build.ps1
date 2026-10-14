$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$taskPython = Join-Path (Get-Location) '.venv\Scripts\python.exe'
& $taskPython scripts/download_model.py
if ($LASTEXITCODE -ne 0) { throw 'Model validation failed.' }
New-Item -ItemType Directory -Path artifacts -Force | Out-Null
& $taskPython -m pytest -q --basetemp=artifacts/pytest-build
if ($LASTEXITCODE -ne 0) { throw 'Tests failed. Build stopped.' }
& $taskPython scripts/collect_licenses.py
if ($LASTEXITCODE -ne 0) { throw 'License collection failed.' }
& $taskPython -m PyInstaller --noconfirm packaging/airmouse.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
$taskExe = Join-Path (Get-Location) 'dist\AirMouseAI\AirMouseAI.exe'
$taskSmoke = Start-Process -FilePath $taskExe -ArgumentList '--smoke-test' -WindowStyle Hidden -PassThru
if (-not $taskSmoke.WaitForExit(30000)) { throw 'EXE GUI smoke test timed out. Check local logs.' }
if ($taskSmoke.ExitCode -ne 0) { throw 'EXE GUI smoke test failed.' }
$taskReport = Join-Path (Get-Location) 'artifacts\exe-model-report.json'
$taskModel = Start-Process -FilePath $taskExe -ArgumentList @('--model-self-test', '--report', "`"$taskReport`"") -WindowStyle Hidden -PassThru
if (-not $taskModel.WaitForExit(35000)) { throw 'EXE model subprocess test timed out.' }
if ($taskModel.ExitCode -ne 0) { throw "EXE model subprocess test failed. See $taskReport" }
& $taskPython scripts/package_release.py
if ($LASTEXITCODE -ne 0) { throw 'Portable ZIP packaging failed.' }
Write-Host "Build and startup checks passed: $taskExe"
