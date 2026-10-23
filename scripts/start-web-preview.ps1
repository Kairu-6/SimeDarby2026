param([int]$Port = 8003)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$env:UV_CACHE_DIR = Join-Path $taskRoot '.cache\uv'
$env:HF_HOME = Join-Path $taskRoot '.cache\huggingface'
$env:DATABASE_PATH = Join-Path $taskRoot 'backend\data\public-preview.sqlite3'
$env:PUBLIC_PREVIEW = 'true'
$env:DEMO_MODE = 'true'
$env:PUSH_NOTIFICATIONS_ENABLED = 'false'
$env:PUBLIC_APP_URL = ''
$env:WEB_BUILD_PATH = Join-Path $taskRoot 'mobile\dist'
$env:KIOSK_API_KEY = ''
$env:DEVICE_API_KEY = [System.Guid]::NewGuid().ToString('N') + [System.Guid]::NewGuid().ToString('N')
if (-not (Test-Path -LiteralPath (Join-Path $env:WEB_BUILD_PATH 'index.html'))) { throw 'Build the web app first: cd mobile; npm run export:web' }
Set-Location -LiteralPath (Join-Path $taskRoot 'backend')
uv run --extra vision uvicorn app.main:app --host 127.0.0.1 --port $Port --proxy-headers
