param([switch]$Web, [string]$ApiUrl)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$env:npm_config_cache = Join-Path $taskRoot '.cache\npm'
if ($ApiUrl) { $env:EXPO_PUBLIC_API_URL = $ApiUrl }
Set-Location -LiteralPath (Join-Path $taskRoot 'mobile')
if ($Web) { npm run web } else { npm start }
