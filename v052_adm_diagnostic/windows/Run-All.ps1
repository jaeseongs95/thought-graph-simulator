param(
    [string]$RunName = "v052_adm_02",
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
    $BaselineBundle = Join-Path $repo "results_llm\v051_adm_01_evidence.zip"
}
$plan = Join-Path $repo ("experiments_v052\" + $RunName + ".plan.json")
$run = Join-Path $repo ("results_llm\" + $RunName)
$bundle = Join-Path $repo ("results_llm\" + $RunName + "_evidence.zip")
if (-not (Test-Path -LiteralPath $BaselineBundle -PathType Leaf)) { throw "Baseline evidence ZIP not found: $BaselineBundle" }
foreach ($p in @($plan, $run, $bundle)) {
    if (Test-Path -LiteralPath $p) { throw "Existing artifact is preserved. Choose a new -RunName: $p" }
}
function Invoke-Probe {
    param(
        [string[]]$Arguments,
        [string]$StatusPath = ""
    )
    & python -m adm_diagnostic_v052 @Arguments
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        $detail = ""
        if (-not [string]::IsNullOrEmpty($StatusPath) -and (Test-Path -LiteralPath $StatusPath -PathType Leaf)) {
            try {
                $s = Get-Content -LiteralPath $StatusPath -Raw -Encoding UTF8 | ConvertFrom-Json
                $detail = " State=$($s.state); Stage=$($s.failure_stage); Kind=$($s.failure_kind); Error=$($s.error)"
            } catch {
                $detail = " Status file exists but could not be parsed: $StatusPath"
            }
        }
        throw "Step failed. Raw evidence was preserved; no automatic retry. Exit: $code.$detail"
    }
}
Push-Location $module
try {
    Invoke-Probe -Arguments @("selftest")
    Invoke-Probe -Arguments @("prepare", "--baseline-bundle", $BaselineBundle, "--out", $plan)
    Invoke-Probe -Arguments @("run", "--plan", $plan, "--out", $run) -StatusPath (Join-Path $run "status.json")
    Invoke-Probe -Arguments @("audit", "--plan", $plan, "--run", $run)
    Invoke-Probe -Arguments @("bundle", "--plan", $plan, "--run", $run, "--out", $bundle)
    Get-Content -LiteralPath (Join-Path $run "summary.ko.md") -Encoding UTF8
    Write-Output "Evidence ZIP: $bundle"
} finally {
    Pop-Location
}
