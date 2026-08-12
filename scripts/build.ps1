param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Missing .venv. Create it and install development dependencies first."
}

Push-Location $projectRoot
try {
    if (-not $SkipTests) {
        & $pythonExe -m pytest
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $pythonExe -m ruff check .
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }

    New-Item -ItemType Directory -Force -Path ".build" | Out-Null
    & $pythonExe -m codex_usage_widget.icon_factory --output ".build\CodexUsageWidget.ico"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $pythonExe -m PyInstaller --noconfirm --clean "codex_usage_widget.spec"
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
