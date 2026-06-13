$ErrorActionPreference = 'Stop'

$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $base '.venv\Scripts\python.exe'
$logDir = Join-Path $base 'logs'

if (!(Test-Path $logDir)) {
  New-Item -ItemType Directory -Path $logDir | Out-Null
}

Push-Location $base

try {
  $cmd = '"' + $python + '" auto_pipeline.py --limit 6 --skip-outreach 2>&1'
  $out = cmd /c $cmd
  $exit = $LASTEXITCODE
} finally {
  Pop-Location
}

$joined = ($out -join ' ')

$saved = ([regex]::Matches($joined, 'Saved\s+\d+\s+leads')).Count
$selected = [regex]::Match($joined, '"selected_for_message_generation":\s*(\d+)').Groups[1].Value
$filtered = [regex]::Match($joined, '"filtered_by_quality_score":\s*(\d+)').Groups[1].Value

if (-not $selected) { $selected = '0' }
if (-not $filtered) { $filtered = '0' }

if ($exit -eq 0) {
  $line = "$(Get-Date -Format o) scraper pipeline ok saved_events=$saved selected_messages=$selected filtered_by_quality=$filtered outreach_sent=0"
} else {
  $line = "$(Get-Date -Format o) scraper pipeline error exit=$exit"
}

Add-Content -Path (Join-Path $logDir 'scraper-pipeline.log') -Value $line

$out
