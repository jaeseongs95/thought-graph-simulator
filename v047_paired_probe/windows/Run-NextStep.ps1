param(
    [string]$RepositoryRoot = "",
    [string]$RunName = "v047_paired_01",
    [switch]$Execute
)
$ErrorActionPreference = "Stop"
$BundleRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = Split-Path -Parent $BundleRoot
}
$RepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
if ($RunName -notmatch '^[a-zA-Z0-9_-]+$') { throw "RunName에는 영문, 숫자, 밑줄, 하이픈만 사용할 수 있습니다." }
$SourceRoot = Join-Path $RepositoryRoot "results_llm"
$PlanPath = Join-Path $RepositoryRoot ("experiments_v047\" + $RunName + ".plan.json")
$RunPath = Join-Path $SourceRoot $RunName
if (-not (Test-Path -LiteralPath $SourceRoot -PathType Container)) { throw "원본 results_llm 폴더를 찾지 못했습니다: $SourceRoot" }
if (Test-Path -LiteralPath $PlanPath) { throw "기존 계획은 덮어쓰지 않습니다: $PlanPath" }
if (Test-Path -LiteralPath $RunPath) { throw "기존 결과는 덮어쓰지 않습니다: $RunPath" }
Push-Location -LiteralPath $BundleRoot
try {
    & python -m paired_probe_v047 selftest
    if ($LASTEXITCODE -ne 0) { throw "오프라인 시험 실패. 추론을 시작하지 않습니다." }
    & python -m paired_probe_v047 prepare --source-root $SourceRoot --out $PlanPath
    if ($LASTEXITCODE -ne 0) { throw "계획 생성 실패. 추론을 시작하지 않습니다." }
    if (-not $Execute) {
        Write-Host "계획만 생성했습니다. LLM 추론은 실행하지 않았습니다."
        Write-Host ('python -m paired_probe_v047 run --plan "' + $PlanPath + '" --out "' + $RunPath + '"')
        return
    }
    & python -m paired_probe_v047 run --plan $PlanPath --out $RunPath
    if ($LASTEXITCODE -ne 0) { throw "추론 수집이 완료되지 않았습니다. 보존된 status.json과 원문을 확인하세요. 자동 재시도하지 않습니다." }
    & python -m paired_probe_v047 audit --plan $PlanPath --run $RunPath
    if ($LASTEXITCODE -ne 0) { throw "오프라인 감사 실패. 성공률 해석을 중단하세요." }
    Write-Host "수집·감사가 완료됐습니다. 모델의 정답률은 summary.ko.md에서 별도로 확인하세요."
    Write-Host (Join-Path $RunPath "summary.ko.md")
} finally {
    Pop-Location
}
