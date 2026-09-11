[CmdletBinding()]
param([string]$RunName = "v049_expression_01")

$ErrorActionPreference = "Stop"
if ($RunName -notmatch '^[A-Za-z0-9_-]+$') {
    throw "RunName은 영문·숫자·밑줄·하이픈만 사용할 수 있습니다."
}
$module = Split-Path -Parent $PSScriptRoot
$repo = Split-Path -Parent $module
Set-Location -LiteralPath $module
$baseline = Join-Path $repo "results_llm\v048_seed_01_evidence.zip"
$plan = Join-Path $repo ("experiments_v049\" + $RunName + ".plan.json")
$run = Join-Path $repo ("results_llm\" + $RunName)
$bundle = Join-Path $repo ("results_llm\" + $RunName + "_evidence.zip")

if (-not (Test-Path -LiteralPath $baseline -PathType Leaf)) {
    throw "v048 증거 ZIP이 없습니다: $baseline"
}
foreach ($path in @($plan, $run, $bundle)) {
    if (Test-Path -LiteralPath $path) {
        throw "기존 파일/폴더는 덮어쓰지 않습니다. 다른 RunName을 사용하세요: $path"
    }
}

python -m paired_probe_v049 selftest
if ($LASTEXITCODE -ne 0) { throw "오프라인 selftest 실패. 중단합니다." }
python -m paired_probe_v049 prepare --baseline-bundle $baseline --out $plan
if ($LASTEXITCODE -ne 0) { throw "v048 재감사 또는 계획 생성 실패. 중단합니다." }
Write-Host "이제 계획된 로컬 모델 추론을 실행합니다. 최대 480회 요청입니다."
python -m paired_probe_v049 run --plan $plan --out $run
if ($LASTEXITCODE -ne 0) { throw "수집 미완료 또는 실행 계약 오류. 기존 결과를 보존하세요: $run" }
python -m paired_probe_v049 audit --plan $plan --run $run
if ($LASTEXITCODE -ne 0) { throw "오프라인 재감사 실패. 원문을 보존하세요." }
python -m paired_probe_v049 bundle --plan $plan --run $run --out $bundle
if ($LASTEXITCODE -ne 0) { throw "증거 ZIP 생성 실패." }
Get-Content -LiteralPath (Join-Path $run "summary.ko.md") -Encoding UTF8
Write-Host "전달할 결과 ZIP: $bundle"
