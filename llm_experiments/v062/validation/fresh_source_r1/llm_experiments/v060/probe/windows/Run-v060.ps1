#requires -Version 5.1

[CmdletBinding()]
param(
    [ValidatePattern('^v060_[A-Za-z0-9_-]+$')]
    [string]$RunName = '',
    [string]$BaselineBundle = '',
    [string]$V059EvidenceBundle = '',
    [switch]$SkipSelfTest,
    [switch]$CheckOnly,
    [switch]$NoOpen,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try {
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
    # Redirection hosts may not expose writable console encodings.
}
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'

$ProbeRoot = Split-Path -Parent $PSScriptRoot
$VersionRoot = Split-Path -Parent $ProbeRoot
$LlmRoot = Split-Path -Parent $VersionRoot
$RepoRoot = Split-Path -Parent $LlmRoot
$ResultsRoot = Join-Path $VersionRoot 'results_llm'
$ExperimentsRoot = Join-Path $VersionRoot 'experiments'
$LogsRoot = Join-Path $ResultsRoot 'automation_logs'
$Timestamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
$LogDir = Join-Path $LogsRoot ("v060_{0}" -f $Timestamp)
$LogPath = Join-Path $LogDir 'run.log'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$LockStream = $null
$ExitCode = 0

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
[System.IO.File]::WriteAllText($LogPath, '', $Utf8NoBom)

function Write-RunLog {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Message)
    $line = '[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Write-Host $line
    [System.IO.File]::AppendAllText($script:LogPath, $line + [Environment]::NewLine, $script:Utf8NoBom)
}

function Invoke-PythonStep {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    Write-RunLog ("START: {0}" -f $Label)
    $displayArgs = ($Arguments | ForEach-Object {
        if ($_ -match '\s') { '"{0}"' -f $_ } else { $_ }
    }) -join ' '
    Write-RunLog ("COMMAND: {0} {1}" -f $script:PythonExe, $displayArgs)
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $script:PythonExe @Arguments 2>&1 | ForEach-Object {
            Write-RunLog ([string]$_)
        }
        $nativeExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorPreference
    }
    if ($nativeExitCode -ne 0) {
        throw "'$Label' failed with exit code $nativeExitCode. No automatic retry was attempted."
    }
    Write-RunLog ("DONE: {0}" -f $Label)
}

function Test-RunNameAvailable {
    param([Parameter(Mandatory = $true)][string]$Name)
    $candidates = @(
        (Join-Path $script:ExperimentsRoot ("{0}.plan.json" -f $Name)),
        (Join-Path $script:ExperimentsRoot ("{0}.plan.baseline.zip" -f $Name)),
        (Join-Path $script:ResultsRoot $Name),
        (Join-Path $script:ResultsRoot ("{0}_evidence.zip" -f $Name)),
        (Join-Path $script:ResultsRoot ("{0}_independent.json" -f $Name))
    )
    return -not ($candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1)
}

function Get-FreeRunName {
    for ($index = 1; $index -le 9999; $index++) {
        $candidate = 'v060_position_{0:d2}' -f $index
        if (Test-RunNameAvailable -Name $candidate) { return $candidate }
    }
    throw 'No free v060_position_#### run name was found.'
}

function Test-LocalOllamaServer {
    param([Parameter(Mandatory = $true)][string]$BaseUrl)
    try {
        $response = Invoke-WebRequest -Uri ($BaseUrl.TrimEnd('/') + '/api/version') -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Ensure-LocalOllamaServer {
    param([Parameter(Mandatory = $true)][string]$PlanPath)
    $plan = Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $endpoint = [Uri]$plan.baseline.config.endpoint
    $allowedHosts = @('localhost', '127.0.0.1', '::1')
    if ($endpoint.Scheme -notin @('http', 'https') -or $endpoint.Host -notin $allowedHosts -or $endpoint.UserInfo) {
        throw "The plan endpoint is not an allowed loopback address: $endpoint"
    }
    $baseUrl = $endpoint.GetLeftPart([System.UriPartial]::Authority)
    if (Test-LocalOllamaServer -BaseUrl $baseUrl) {
        Write-RunLog ("Ollama server is available: {0}" -f $baseUrl)
        return
    }

    $ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
    $ollamaExe = if ($ollamaCommand) { $ollamaCommand.Source } else {
        Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    }
    if (-not (Test-Path -LiteralPath $ollamaExe)) {
        throw 'The Ollama server is unavailable and ollama.exe was not found. This launcher does not install or download models.'
    }
    Write-RunLog ("Starting Ollama server: {0}" -f $ollamaExe)
    $ollamaStdout = Join-Path $script:LogDir 'ollama.stdout.log'
    $ollamaStderr = Join-Path $script:LogDir 'ollama.stderr.log'
    Start-Process -FilePath $ollamaExe -ArgumentList @('serve') -WindowStyle Hidden `
        -RedirectStandardOutput $ollamaStdout -RedirectStandardError $ollamaStderr | Out-Null
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        Start-Sleep -Seconds 1
        if (Test-LocalOllamaServer -BaseUrl $baseUrl) {
            Write-RunLog ("Ollama server is ready: {0}" -f $baseUrl)
            return
        }
    }
    throw "The Ollama server was not ready within 30 seconds. See $ollamaStderr"
}

try {
    if ((Split-Path -Leaf $ProbeRoot) -ne 'probe' -or
        (Split-Path -Leaf $VersionRoot) -ne 'v060' -or
        (Split-Path -Leaf $LlmRoot) -ne 'llm_experiments') {
        throw "The expected repository structure was not found. Script: $PSCommandPath"
    }
    $requiredPaths = @(
        (Join-Path $ProbeRoot 'terminal_position_v060'),
        (Join-Path $ProbeRoot 'tools\analyze_v059.py'),
        (Join-Path $ProbeRoot 'tools\verify_v060.py')
    )
    foreach ($requiredPath in $requiredPaths) {
        if (-not (Test-Path -LiteralPath $requiredPath)) { throw "Required path is missing: $requiredPath" }
    }

    New-Item -ItemType Directory -Path $ResultsRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $ExperimentsRoot -Force | Out-Null
    $lockPath = Join-Path $LogsRoot 'v060.lock'
    try {
        $LockStream = [System.IO.File]::Open(
            $lockPath,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )
    } catch {
        throw "Another v060 launcher is running. Lock file: $lockPath"
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { throw 'Python was not found on PATH. Install Python 3.10 or later and add it to PATH.' }
    $PythonExe = $pythonCommand.Source
    & $PythonExe -X utf8 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.10 or later is required.' }

    if ([string]::IsNullOrWhiteSpace($BaselineBundle)) {
        $BaselineBundle = Join-Path $LlmRoot 'v058\results_llm\v058_order_02_evidence.zip'
    }
    if (-not (Test-Path -LiteralPath $BaselineBundle -PathType Leaf)) {
        throw "The v058 reference evidence ZIP was not found: $BaselineBundle"
    }
    $BaselineBundle = (Resolve-Path -LiteralPath $BaselineBundle).Path
    if ([string]::IsNullOrWhiteSpace($V059EvidenceBundle)) {
        $V059EvidenceBundle = Join-Path $LlmRoot 'v059\results_llm\v059_rules_01_evidence.zip'
    }
    if (-not (Test-Path -LiteralPath $V059EvidenceBundle -PathType Leaf)) {
        throw "The v059 evidence ZIP was not found: $V059EvidenceBundle"
    }
    $V059EvidenceBundle = (Resolve-Path -LiteralPath $V059EvidenceBundle).Path

    Set-Location -LiteralPath $ProbeRoot
    Write-RunLog ("Repository: {0}" -f $RepoRoot)
    Write-RunLog ("Python: {0}" -f $PythonExe)
    Write-RunLog ("Log: {0}" -f $LogPath)
    Write-RunLog ("v058 reference evidence: {0}" -f $BaselineBundle)
    Write-RunLog ("v059 diagnostic evidence: {0}" -f $V059EvidenceBundle)

    if (-not $SkipSelfTest) {
        Invoke-PythonStep -Label 'v060 self-test' -Arguments @('-X', 'utf8', '-B', '-m', 'terminal_position_v060', 'selftest')
    } else {
        Write-RunLog 'Self-test skipped because -SkipSelfTest was specified.'
    }

    $analysisPath = Join-Path $LogDir 'v059_analysis.json'
    Invoke-PythonStep -Label 'v059 evidence reanalysis' -Arguments @(
        '-X', 'utf8', '-B', 'tools\analyze_v059.py', $V059EvidenceBundle, '--out', $analysisPath
    )

    if ($CheckOnly) {
        $checkPlan = Join-Path $LogDir 'v060_check.plan.json'
        Invoke-PythonStep -Label 'current-source check plan preparation' -Arguments @(
            '-X', 'utf8', '-B', '-m', 'terminal_position_v060',
            'prepare', '--baseline-bundle', $BaselineBundle, '--out', $checkPlan
        )
        Invoke-PythonStep -Label 'current-source check plan validation' -Arguments @(
            '-X', 'utf8', '-B', '-m', 'terminal_position_v060', 'show', '--plan', $checkPlan
        )
        Write-RunLog 'Check complete. No model call, Ollama start, or inference-result creation was performed.'
        Write-Host "`nCheck completed successfully.`nLog: $LogPath" -ForegroundColor Green
    } else {
        if ([string]::IsNullOrWhiteSpace($RunName)) {
            $RunName = Get-FreeRunName
        } elseif (-not (Test-RunNameAvailable -Name $RunName)) {
            throw "Artifacts for run '$RunName' already exist. Specify another -RunName; existing runs are never overwritten."
        }
        $planPath = Join-Path $ExperimentsRoot ("{0}.plan.json" -f $RunName)
        $runOutputPath = Join-Path $ResultsRoot $RunName
        $evidencePath = Join-Path $ResultsRoot ("{0}_evidence.zip" -f $RunName)
        $independentPath = Join-Path $ResultsRoot ("{0}_independent.json" -f $RunName)
        Write-RunLog ("Run name: {0}" -f $RunName)
        Write-RunLog 'Contract: 40 inference calls, no automatic retry, no overwrite of existing results.'

        Invoke-PythonStep -Label 'v060 plan preparation' -Arguments @(
            '-X', 'utf8', '-B', '-m', 'terminal_position_v060',
            'prepare', '--baseline-bundle', $BaselineBundle, '--out', $planPath
        )
        Invoke-PythonStep -Label 'frozen plan validation' -Arguments @(
            '-X', 'utf8', '-B', '-m', 'terminal_position_v060', 'show', '--plan', $planPath
        )
        Ensure-LocalOllamaServer -PlanPath $planPath
        Invoke-PythonStep -Label 'v060 40-call inference run' -Arguments @(
            '-X', 'utf8', '-B', '-m', 'terminal_position_v060', 'run', '--plan', $planPath, '--out', $runOutputPath
        )
        Invoke-PythonStep -Label 'run audit' -Arguments @(
            '-X', 'utf8', '-B', '-m', 'terminal_position_v060', 'audit', '--plan', $planPath, '--run', $runOutputPath
        )
        Invoke-PythonStep -Label 'evidence ZIP creation' -Arguments @(
            '-X', 'utf8', '-B', '-m', 'terminal_position_v060',
            'bundle', '--plan', $planPath, '--run', $runOutputPath, '--out', $evidencePath
        )
        Invoke-PythonStep -Label 'independent verification' -Arguments @(
            '-X', 'utf8', '-B', 'tools\verify_v060.py', $evidencePath, '--out', $independentPath
        )

        $completionPath = Join-Path $LogDir 'completion.json'
        $completion = [ordered]@{
            contract = 'v060-one-click-completion-r1'
            state = 'complete'
            run_name = $RunName
            plan_path = $planPath
            results_path = $runOutputPath
            evidence_path = $evidencePath
            evidence_sha256 = (Get-FileHash -LiteralPath $evidencePath -Algorithm SHA256).Hash.ToLowerInvariant()
            independent_path = $independentPath
            log_path = $LogPath
            completed_at = (Get-Date).ToString('o')
        }
        [System.IO.File]::WriteAllText(
            $completionPath,
            (($completion | ConvertTo-Json -Depth 4) + [Environment]::NewLine),
            $Utf8NoBom
        )
        Write-RunLog ("ALL COMPLETE: {0}" -f $evidencePath)
        Write-Host "`nCompleted successfully." -ForegroundColor Green
        Write-Host "Evidence ZIP: $evidencePath"
        Write-Host "Independent verification: $independentPath"
        Write-Host "Log: $LogPath"
        if (-not $NoOpen) {
            Start-Process -FilePath explorer.exe -ArgumentList ('/select,"{0}"' -f $evidencePath) | Out-Null
        }
    }
} catch {
    $ExitCode = 1
    try { Write-RunLog ("FAILED: {0}" -f $_.Exception.Message) } catch { Write-Host 'The failure could not be written to the log.' -ForegroundColor Red }
    Write-Host "`nThe run stopped. No automatic retry was attempted." -ForegroundColor Red
    Write-Host "Log: $LogPath"
} finally {
    if ($LockStream) { $LockStream.Dispose() }
    Set-Location -LiteralPath $RepoRoot -ErrorAction SilentlyContinue
    if (-not $NoPause) { [void](Read-Host 'Press Enter to close this window') }
}

exit $ExitCode
