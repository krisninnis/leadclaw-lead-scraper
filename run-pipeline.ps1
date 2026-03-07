$ErrorActionPreference = 'Stop'
$base = 'C:\Users\KRIS\.openclaw\workspace\lead-scraper-bot'
$python = "$base\.venv\Scripts\python.exe"
$logDir = 'C:\Users\KRIS\.openclaw\workspace\logs'
if (!(Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

Push-Location $base
$cmd = '"' + $python + '" auto_pipeline.py --limit 4 --cities London Manchester --niches beauty 2>&1'
$out = cmd /c $cmd
$exit = $LASTEXITCODE
Pop-Location

$joined = ($out -join ' ')
$saved = ([regex]::Matches($joined, 'Saved\s+\d+\s+Google Places leads')).Count
$dedupe = [regex]::Match($joined, 'duplicates_marked=(\d+)').Groups[1].Value
$paused = [regex]::Match($joined, 'paused=(\d+)').Groups[1].Value
$sent = [regex]::Match($joined, 'sentCount'':\s*(\d+)').Groups[1].Value
if (-not $dedupe) { $dedupe = '0' }
if (-not $paused) { $paused = '0' }
if (-not $sent) { $sent = '0' }

if ($exit -eq 0) {
  $line = "$(Get-Date -Format o) scraper pipeline ok jobs_saved=$saved dedupe=$dedupe paused=$paused outreach_sent=$sent"
} else {
  $line = "$(Get-Date -Format o) scraper pipeline error exit=$exit"
}

Add-Content -Path (Join-Path $logDir 'scraper-pipeline.log') -Value $line
