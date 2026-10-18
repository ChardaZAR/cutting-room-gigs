$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$jsonPath = Join-Path $dir "jobs.json"
$jsPath = Join-Path $dir "jobs.js"
$indexPath = Join-Path $dir "index.html"
$standalonePath = Join-Path $dir "cutting-room-gigs-standalone.html"

$rawJson = Get-Content -Path $jsonPath -Raw -Encoding UTF8
$parsed = $rawJson | ConvertFrom-Json
$minifiedJson = $parsed | ConvertTo-Json -Depth 10 -Compress

# Write jobs.js for file:// fallback in index.html
$jsContent = "window.CRG_DATA = $minifiedJson;`n"
Set-Content -Path $jsPath -Value $jsContent -Encoding UTF8

# Generate cutting-room-gigs-standalone.html from index.html with inline window.CRG_DATA
if (Test-Path $indexPath) {
    $html = Get-Content -Path $indexPath -Raw -Encoding UTF8
    $inlineScript = "<script>window.CRG_DATA = $minifiedJson;</script>"
    $standaloneHtml = $html.Replace('<script src="jobs.js"></script>', $inlineScript)
    Set-Content -Path $standalonePath -Value $standaloneHtml -Encoding UTF8 -NoNewline
}

Write-Host "Synced jobs.json ($($parsed.jobs.Count) jobs, sweepDate: $($parsed.sweepDate)) -> jobs.js & cutting-room-gigs-standalone.html"
