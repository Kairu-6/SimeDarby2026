$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$env:UV_CACHE_DIR = Join-Path $taskRoot '.cache\uv'
$env:HF_HOME = Join-Path $taskRoot '.cache\huggingface'
$env:npm_config_cache = Join-Path $taskRoot '.cache\npm'
Push-Location -LiteralPath (Join-Path $taskRoot 'backend')
try {
    uv sync --extra vision
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
    uv run --extra vision python scripts/warm_model.py
    if ($LASTEXITCODE -ne 0) { throw 'Model download failed. Check your connection and retry.' }
} finally { Pop-Location }
Push-Location -LiteralPath (Join-Path $taskRoot 'mobile')
try {
    npm ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'App dependency installation failed.' }
} finally { Pop-Location }
Write-Host 'Ready. Run scripts/start-backend.ps1 and scripts/start-app.ps1 in separate terminals.'
