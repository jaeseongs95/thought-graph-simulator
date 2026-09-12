param(
    [string]$BaselineBundle = "",
    [string]$RunName = "v054_order_01"
)
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if ($RunName -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]*$') {
    throw "RunName에는 영문·숫자·밑줄·하이픈만 사용할 수 있습니다."
}
if ([string]::IsNullOrWhiteSpace($BaselineBundle)) {
    $Candidates = @(
        (Join-Path $Root "..\results_llm\v053_depth_01_evidence.zip"),
        (Join-Path $Root "..\v053_depth_01_evidence.zip"),
        (Join-Path $Root "v053_depth_01_evidence.zip")
    )
    $Found = @($Candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
    if ($Found.Count -ne 1) {
        throw "v053_depth_01_evidence.zip 경로를 -BaselineBundle로 명시하세요. 후보가 없거나 여러 개입니다."
    }
    $BaselineBundle = $Found[0]
}
$BaselineBundle = (Resolve-Path -LiteralPath $BaselineBundle).Path
$Plan = Join-Path $Root "..\experiments_v054\$RunName.plan.json"
$Run = Join-Path $Root "..\results_llm\$RunName"
$Evidence = Join-Path $Root "..\results_llm\${RunName}_evidence.zip"
foreach ($Path in @($Plan,$Run,$Evidence)) {
    if (Test-Path -LiteralPath $Path) { throw "기존 파일·폴더는 덮어쓰지 않습니다: $Path. 새 RunName을 지정하세요." }
}
function Run-Python {
    param([string[]]$PythonArguments)
    & python @PythonArguments
    if ($LASTEXITCODE -ne 0) { throw "Python 종료 코드: $LASTEXITCODE" }
}
Run-Python -PythonArguments @("-m","order_probe_v054","selftest")
Run-Python -PythonArguments @("-m","order_probe_v054","prepare","--baseline-bundle",$BaselineBundle,"--out",$Plan)
Run-Python -PythonArguments @("-m","order_probe_v054","show","--plan",$Plan)
& python -m order_probe_v054 run --plan $Plan --out $Run
$RunExit = $LASTEXITCODE
if ($RunExit -ne 0) {
    $Status = Join-Path $Run "status.json"
    if (Test-Path -LiteralPath $Status) { Get-Content -LiteralPath $Status -Raw -Encoding UTF8 }
    throw "실험이 중단되었습니다(종료 코드 $RunExit). 원문은 보존됩니다. 위 failure_stage/failure_kind/error를 확인하세요."
}
Run-Python -PythonArguments @("-m","order_probe_v054","audit","--plan",$Plan,"--run",$Run)
Run-Python -PythonArguments @("-m","order_probe_v054","bundle","--plan",$Plan,"--run",$Run,"--out",$Evidence)
Write-Host "결과: $(Join-Path $Run 'summary.ko.md')"
Write-Host "전달할 증거: $Evidence"
