param(
  [Parameter(Mandatory=$true)][string]$ApiOrigin,
  [string]$AppProject = 'sime-loop-app',
  [string]$KioskProject = 'sime-loop-kiosk',
  [string]$AppUrl = '',
  [switch]$BuildOnly
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$apiUri = [Uri]$ApiOrigin
if ($apiUri.Scheme -ne 'https' -or $apiUri.UserInfo -or $apiUri.AbsolutePath -ne '/') { throw 'ApiOrigin must be a public HTTPS origin, without credentials or a path.' }
foreach ($project in @($AppProject,$KioskProject)) {
  if ($project -notmatch '^[a-z0-9][a-z0-9-]{0,57}[a-z0-9]$') { throw 'Use a valid lowercase Cloudflare Pages project name.' }
}
Get-Command wrangler -ErrorAction Stop | Out-Null
function Check-Exit([string]$Step) { if ($LASTEXITCODE -ne 0) { throw "$Step failed. See the command output." } }
if (-not $BuildOnly) { wrangler whoami; Check-Exit 'Cloudflare authentication' }
$env:EXPO_PUBLIC_API_URL = ''
$env:EXPO_PUBLIC_APP_URL = if ($AppUrl) { $AppUrl.TrimEnd('/') } else { "https://$AppProject.pages.dev" }
$env:EXPO_PUBLIC_SURFACE = 'app'
Push-Location -LiteralPath (Join-Path $taskRoot 'mobile')
try {
  npm run typecheck; Check-Exit 'TypeScript'
  npm run export:web; Check-Exit 'Resident web build'
  $env:EXPO_PUBLIC_SURFACE = 'kiosk'
  npx expo export --platform web --output-dir dist-kiosk; Check-Exit 'Kiosk web build'
} finally { Pop-Location }
foreach ($surface in @(@{Name=$AppProject;Dir='dist';Config='wrangler.app.jsonc'},@{Name=$KioskProject;Dir='dist-kiosk';Config='wrangler.kiosk.jsonc'})) {
  $outputDir = Join-Path $taskRoot ('mobile\' + $surface.Dir)
  foreach ($file in @('_worker.js','_routes.json','_headers')) { Copy-Item -LiteralPath (Join-Path $taskRoot ('deploy\pages\' + $file)) -Destination (Join-Path $outputDir $file) -Force }
  $config = @{
    name=$surface.Name
    pages_build_output_dir=('../../mobile/' + $surface.Dir)
    compatibility_date='2026-10-23'
    vars=@{ API_ORIGIN=$ApiOrigin.TrimEnd('/') }
  }
  $configPath = Join-Path $taskRoot ('deploy\pages\' + $surface.Config)
  $config | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $configPath -Encoding utf8
  if (-not $BuildOnly) {
    $projects = wrangler pages project list --json | ConvertFrom-Json; Check-Exit 'List Pages projects'
    if (-not @($projects | Where-Object { $_.name -eq $surface.Name }).Count) { wrangler pages project create $surface.Name --production-branch main; Check-Exit 'Create Pages project' }
    wrangler pages deploy $outputDir --config $configPath --project-name $surface.Name --branch main --commit-dirty=true; Check-Exit 'Pages deployment'
  }
}
if ($BuildOnly) { Write-Host 'Both Pages builds and API proxy configurations are ready. No deployment was attempted.' }
else { Write-Host "Resident app: https://$AppProject.pages.dev`nStation screen: https://$KioskProject.pages.dev`nVerify the actual domains printed by Wrangler if a project name was already taken." }
