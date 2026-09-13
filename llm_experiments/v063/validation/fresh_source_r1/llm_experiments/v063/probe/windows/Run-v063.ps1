#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$EvidenceBundle = '',
    [ValidatePattern('^[0-9a-f]{64}$')]
    [string]$ExpectedSha256 = 'baea752ac1a55dc7a20b42b41ced69b3c8e126105f65deea8ebecc8dde3f09fd',
    [switch]$SkipSelfTest,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$ProbeRoot = Split-Path -Parent $PSScriptRoot
$VersionRoot = Split-Path -Parent $ProbeRoot
$LlmRoot = Split-Path -Parent $VersionRoot
$ResultsRoot = Join-Path $VersionRoot 'results_llm'
$LogRoot = Join-Path $ResultsRoot ('automation_logs\v063_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
$LogPath = Join-Path $LogRoot 'run.log'
$ExitCode = 0
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
[System.IO.File]::WriteAllText($LogPath, '', $Utf8NoBom)

function Write-RunLog([string]$Message) {
    $line = '[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] ' + $Message
    Write-Host $line
    [System.IO.File]::AppendAllText($script:LogPath, $line + "`n", $script:Utf8NoBom)
}

function Invoke-PythonStep([string]$Label, [string[]]$Arguments) {
    Write-RunLog ('START: ' + $Label)
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $script:PythonExe @Arguments 2>&1 | ForEach-Object { Write-RunLog ([string]$_) }
        $stepExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $oldPreference }
    if ($stepExit -ne 0) { throw ($Label + ' failed, exit=' + $stepExit) }
    Write-RunLog ('DONE: ' + $Label)
}

Push-Location $ProbeRoot
try {
    $PythonExe = (Get-Command python.exe -ErrorAction Stop).Source
    if ([string]::IsNullOrWhiteSpace($EvidenceBundle)) {
        $EvidenceBundle = Join-Path $LlmRoot 'v062\results_llm\v062_construction_01_evidence.zip'
    }
    $EvidenceBundle = (Resolve-Path -LiteralPath $EvidenceBundle -ErrorAction Stop).Path
    Write-RunLog 'OFFLINE DIAGNOSTICS ONLY. No new model inference or model-facing prompt.'
    Write-RunLog ('Evidence: ' + $EvidenceBundle)
    if (-not $SkipSelfTest) {
        Invoke-PythonStep 'offline selftest' @('-X', 'utf8', '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v')
    }
    $OutputPath = $null
    for ($index = 1; $index -le 9999; $index++) {
        $candidate = Join-Path $ResultsRoot ('v063_forensics_{0:d2}' -f $index)
        if (-not (Test-Path -LiteralPath $candidate)) { $OutputPath = $candidate; break }
    }
    if ($null -eq $OutputPath) { throw 'No unused output directory is available.' }
    Invoke-PythonStep 'raw analysis and independent verification' @(
        '-X', 'utf8', '-B', 'tools\run_forensics.py', $EvidenceBundle, '--out', $OutputPath,
        '--expected-sha256', $ExpectedSha256)
    Write-RunLog ('ALL COMPLETE: ' + $OutputPath)
    Write-Host ("`nOffline analysis completed. Results: " + $OutputPath)
} catch {
    $ExitCode = 1
    Write-RunLog ('FAILED: ' + $_.Exception.Message)
} finally {
    Pop-Location
    Write-Host ('Log: ' + $LogPath)
    if (-not $NoPause) { [void](Read-Host 'Press Enter to close') }
}
exit $ExitCode
