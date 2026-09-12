param(
    [string]$RunName = "v055_model_01",
    [string]$BaselineBundle = "",
    [switch]$AllTests
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$packageRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $packageRoot
Set-Location -LiteralPath $packageRoot
if ($RunName -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$') { throw "RunName must be a plain file name." }
$results = Join-Path $repoRoot "results_llm"
if ([string]::IsNullOrWhiteSpace($BaselineBundle)) { $BaselineBundle = Join-Path $results "v054_order_01_evidence.zip" }
if (-not (Test-Path -LiteralPath $BaselineBundle -PathType Leaf)) { throw "Baseline not found: $BaselineBundle" }
$BaselineBundle = (Resolve-Path -LiteralPath $BaselineBundle).Path
$captureDir = Join-Path $results ($RunName + ".capture")
$plan = Join-Path $results ($RunName + ".plan.json")
$run = Join-Path $results $RunName
$bundle = Join-Path $results ($RunName + "_evidence.zip")
foreach ($p in @($captureDir, $plan, $run, $bundle)) {
    if (Test-Path -LiteralPath $p) { throw "Existing evidence is preserved. Choose a new -RunName: $p" }
}
function Invoke-Probe {
    param([string[]]$Arguments)
    & python -m model_probe_v055 @Arguments
    if ($LASTEXITCODE -ne 0) {
        $code = $LASTEXITCODE
        $detail = ""
        $statusPath = Join-Path $run "status.json"
        $capturePath = Join-Path $captureDir "capture.json"
        try {
            if (Test-Path -LiteralPath $statusPath) {
                $saved = Get-Content -LiteralPath $statusPath -Raw -Encoding UTF8 | ConvertFrom-Json
                $detail = "Stage=$($saved.failure_stage); Kind=$($saved.failure_kind); Error=$($saved.error); Evidence=$statusPath"
            } elseif (Test-Path -LiteralPath $capturePath) {
                $saved = Get-Content -LiteralPath $capturePath -Raw -Encoding UTF8 | ConvertFrom-Json
                $detail = "Capture state=$($saved.state); Error=$($saved.error); Evidence=$capturePath"
            }
        } catch { $detail = "Detailed error record could not be read. Check $run and $captureDir." }
        throw "Step failed: $($Arguments[0]). Exit: $code. Raw evidence preserved; no automatic retry. $detail"
    }
}
# Python stdout는 UTF-8. 원문/기존 자료는 보존한다.
& python tools/validate_release.py
if ($LASTEXITCODE -ne 0) { throw "Release integrity check failed. No model inference was started." }
# 두 모델의 metadata만 먼저 확인한다. capture는 추론을 실행하지 않는다.
Invoke-Probe -Arguments @("capture", "--baseline-bundle", $BaselineBundle, "--out", $captureDir)
if ($AllTests) { Invoke-Probe -Arguments @("selftest", "--all") } else { Invoke-Probe -Arguments @("selftest") }
Invoke-Probe -Arguments @("prepare", "--baseline-bundle", $BaselineBundle, "--capture", (Join-Path $captureDir "capture.json"), "--out", $plan)
Invoke-Probe -Arguments @("run", "--plan", $plan, "--out", $run)
Invoke-Probe -Arguments @("audit", "--plan", $plan, "--run", $run)
Invoke-Probe -Arguments @("bundle", "--plan", $plan, "--run", $run, "--out", $bundle)
Write-Host "Evidence bundle: $bundle"
