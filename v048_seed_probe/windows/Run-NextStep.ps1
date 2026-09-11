param(
    [ValidateSet("Prepare", "Run", "Audit", "Bundle")]
    [string]$Stage = "Prepare",
    [ValidatePattern("^[A-Za-z0-9_-]+$")]
    [string]$RunName = "v048_seed_01"
)

$ErrorActionPreference = "Stop"
$moduleRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $moduleRoot
$baselineRun = Join-Path $repoRoot "results_llm\v047_paired_01"
$baselinePlan = Join-Path $repoRoot "experiments_v047\v047_paired_01.plan.json"
$plan = Join-Path $repoRoot ("experiments_v048\" + $RunName + ".plan.json")
$run = Join-Path $repoRoot ("results_llm\" + $RunName)
$archive = Join-Path $repoRoot ("results_llm\" + $RunName + "_evidence.zip")

function Invoke-CheckedPython {
    param([string[]]$PythonArguments)
    & python @PythonArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python 실행 실패 또는 미완료입니다. 다음 단계로 진행하지 않습니다. 종료 코드: $LASTEXITCODE"
    }
}

Push-Location $moduleRoot
try {
    switch ($Stage) {
        "Prepare" {
            if (Test-Path $plan) { throw "기존 계획 파일을 덮어쓰지 않습니다: $plan" }
            if (Test-Path $run) { throw "기존 결과 폴더를 덮어쓰지 않습니다: $run" }
            Invoke-CheckedPython -PythonArguments @("-m", "paired_probe_v048", "selftest")
            Invoke-CheckedPython -PythonArguments @("-m", "paired_probe_v048", "prepare", "--baseline-run", $baselineRun, "--baseline-plan", $baselinePlan, "--out", $plan)
        }
        "Run" {
            Invoke-CheckedPython -PythonArguments @("-m", "paired_probe_v048", "run", "--plan", $plan, "--out", $run)
            Get-Content (Join-Path $run "summary.ko.md") -Encoding UTF8
        }
        "Audit" {
            Invoke-CheckedPython -PythonArguments @("-m", "paired_probe_v048", "audit", "--plan", $plan, "--run", $run)
        }
        "Bundle" {
            Invoke-CheckedPython -PythonArguments @("-m", "paired_probe_v048", "bundle", "--plan", $plan, "--run", $run, "--out", $archive)
        }
    }
}
finally {
    Pop-Location
}
