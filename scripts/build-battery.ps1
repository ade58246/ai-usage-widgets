param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not $uvCommand -and -not (Test-Path -LiteralPath $pythonExe)) {
    throw "Missing uv or .venv. Install uv with 'scoop install uv' and run 'uv sync --locked'."
}

Push-Location $projectRoot
try {
    if ($uvCommand) {
        if (-not $SkipTests) {
            & $uvCommand.Source run --frozen python -m pytest
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            & $uvCommand.Source run --frozen ruff check .
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
        New-Item -ItemType Directory -Force -Path ".build" | Out-Null
        & $uvCommand.Source run --frozen python -m battery_usage_widget.icon_factory --output ".build\BatteryUsageWidget.ico"
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $uvCommand.Source run --frozen python -m PyInstaller --noconfirm --clean "battery_usage_widget.spec"
        exit $LASTEXITCODE
    }

    if (-not $SkipTests) {
        & $pythonExe -m pytest
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $pythonExe -m ruff check .
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    New-Item -ItemType Directory -Force -Path ".build" | Out-Null
    & $pythonExe -m battery_usage_widget.icon_factory --output ".build\BatteryUsageWidget.ico"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $pythonExe -m PyInstaller --noconfirm --clean "battery_usage_widget.spec"
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
