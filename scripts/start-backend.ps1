$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$env:UV_CACHE_DIR = Join-Path $taskRoot '.cache\uv'
$env:HF_HOME = Join-Path $taskRoot '.cache\huggingface'
Set-Location -LiteralPath (Join-Path $taskRoot 'backend')
uv run --extra vision uvicorn app.main:app --host 0.0.0.0 --port 8000
