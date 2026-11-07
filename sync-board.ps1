$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$jsonPath = Join-Path $dir "jobs.json"
$statePath = Join-Path $dir "user-state.json"
$jsPath = Join-Path $dir "jobs.js"
$indexPath = Join-Path $dir "index.html"
$standalonePath = Join-Path $dir "cutting-room-gigs-standalone.html"

$rawJson = Get-Content -Path $jsonPath -Raw -Encoding UTF8
$parsed = $rawJson | ConvertFrom-Json
$minifiedJson = $parsed | ConvertTo-Json -Depth 10 -Compress

$minifiedState = "{}"
if (Test-Path $statePath) {
    try {
        $rawState = Get-Content -Path $statePath -Raw -Encoding UTF8
        $parsedState = $rawState | ConvertFrom-Json
        # Never embed notifyCfg (alert email + SMTP app password) in files that get committed/published
        $publicKeys = @("status", "statusBySig", "appliedMeta", "alertRules", "disabledSources", "updatedAt")
        $minifiedState = $parsedState | Select-Object -Property ($publicKeys | Where-Object { $parsedState.PSObject.Properties.Name -contains $_ }) | ConvertTo-Json -Depth 10 -Compress
    } catch {
        $minifiedState = "{}"
    }
}

# Write jobs.js for file:// fallback in index.html
$jsContent = "window.CRG_DATA = $minifiedJson;`nwindow.CRG_STATE = $minifiedState;`n"
Set-Content -Path $jsPath -Value $jsContent -Encoding UTF8

# Generate cutting-room-gigs-standalone.html from index.html with inline window.CRG_DATA
if (Test-Path $indexPath) {
    $html = Get-Content -Path $indexPath -Raw -Encoding UTF8
    $inlineScript = "<script>window.CRG_DATA = $minifiedJson;`nwindow.CRG_STATE = $minifiedState;</script>"
    $standaloneHtml = $html.Replace('<script src="jobs.js"></script>', $inlineScript)
    Set-Content -Path $standalonePath -Value $standaloneHtml -Encoding UTF8 -NoNewline
}

Write-Host "Synced jobs.json ($($parsed.jobs.Count) jobs, sweepDate: $($parsed.sweepDate)) -> jobs.js & cutting-room-gigs-standalone.html"
