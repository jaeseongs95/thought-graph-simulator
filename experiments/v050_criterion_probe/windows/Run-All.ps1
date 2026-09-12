param(
    [string]$RunName = "v050_criterion_01",
    [string]$BaselineBundle = ""
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$moduleRoot = Split-Path $PSScriptRoot -Parent
$repoRoot = Split-Path $moduleRoot -Parent
Set-Location $moduleRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
if ($RunName -notmatch '^[A-Za-z0-9_-]+$') { throw "RunName에는 영문자·숫자·밑줄·하이픈만 사용할 수 있습니다." }
if ([string]::IsNullOrWhiteSpace($BaselineBundle)) {
    $BaselineBundle = Join-Path $repoRoot "results_llm\v049_expression_01_evidence.zip"
}
$plan = Join-Path $repoRoot ("experiments_v050\" + $RunName + ".plan.json")
$run = Join-Path $repoRoot ("results_llm\" + $RunName)
$bundle = Join-Path $repoRoot ("results_llm\" + $RunName + "_evidence.zip")
if (-not (Test-Path -LiteralPath $BaselineBundle -PathType Leaf)) { throw "기준선 증거 ZIP이 없습니다: $BaselineBundle" }
foreach ($target in @($plan, $run, $bundle)) {
    if (Test-Path -LiteralPath $target) { throw "기존 산출물을 보존합니다: $target . 별도 실행에는 새로운 -RunName을 지정하세요." }
}
function Invoke-Probe {
    param([string[]]$CliArgs)
    & python -X utf8 -m criterion_probe_v050 @CliArgs
    if ($LASTEXITCODE -ne 0) { throw "명령이 종료 코드 $LASTEXITCODE 로 실패했습니다. 기존 증거를 보존합니다." }
}
Write-Host "[1/5] 오프라인 자체 시험"
Invoke-Probe -CliArgs @("selftest")
Write-Host "[2/5] 계획 동결 (모델 추론 없음)"
Invoke-Probe -CliArgs @("prepare", "--baseline-bundle", $BaselineBundle, "--out", $plan)
Write-Host "[3/5] 로컬 모델 추론 (최대 560회)"
Invoke-Probe -CliArgs @("run", "--plan", $plan, "--out", $run)
Write-Host "[4/5] 오프라인 재감사"
Invoke-Probe -CliArgs @("audit", "--plan", $plan, "--run", $run)
Write-Host "[5/5] 증거 ZIP 생성"
Invoke-Probe -CliArgs @("bundle", "--plan", $plan, "--run", $run, "--out", $bundle)
Get-Content -LiteralPath (Join-Path $run "summary.ko.md") -Encoding UTF8
Write-Host "증거 ZIP: $bundle"
