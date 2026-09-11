param(
    [string]$RunName = "v051_adm_01",
    [string]$BaselineBundle = ""
)
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$module = Split-Path -Parent $PSScriptRoot
$repo = Split-Path -Parent $module
if ($RunName -notmatch '^[A-Za-z0-9_-]+$') { throw "RunName must contain letters, digits, underscore or hyphen only." }
if ([string]::IsNullOrEmpty($BaselineBundle)) {
    $BaselineBundle = Join-Path $repo "results_llm\v050_criterion_01_evidence.zip"
}
$plan = Join-Path $repo ("experiments_v051\" + $RunName + ".plan.json")
$run = Join-Path $repo ("results_llm\" + $RunName)
$bundle = Join-Path $repo ("results_llm\" + $RunName + "_evidence.zip")
if (-not (Test-Path -LiteralPath $BaselineBundle -PathType Leaf)) { throw "Baseline evidence ZIP not found: $BaselineBundle" }
foreach ($p in @($plan, $run, $bundle)) {
    if (Test-Path -LiteralPath $p) { throw "Existing artifact is preserved. Choose a new -RunName: $p" }
}
function Invoke-Probe {
    param([string[]]$Arguments)
    & python -m adm_pilot_v051 @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Step failed. Raw evidence was preserved; no automatic retry. Exit: $LASTEXITCODE" }
}
Push-Location $module
try {
    Invoke-Probe -Arguments @("selftest")
    Invoke-Probe -Arguments @("prepare", "--baseline-bundle", $BaselineBundle, "--out", $plan)
    Invoke-Probe -Arguments @("run", "--plan", $plan, "--out", $run)
    Invoke-Probe -Arguments @("audit", "--plan", $plan, "--run", $run)
    Invoke-Probe -Arguments @("bundle", "--plan", $plan, "--run", $run, "--out", $bundle)
    Get-Content -LiteralPath (Join-Path $run "summary.ko.md") -Encoding UTF8
    Write-Output "Evidence ZIP: $bundle"
} finally {
    Pop-Location
}
