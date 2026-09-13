param([switch]$CheckOnly, [switch]$NoPause, [string]$Baseline = '',
      [string]$RunName = '', [string]$Endpoint = 'http://127.0.0.1:11434')
$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$ProbeRoot = Split-Path $PSScriptRoot -Parent
$VersionRoot = Split-Path $ProbeRoot -Parent
$ExperimentsRoot = Split-Path $VersionRoot -Parent
if (-not $Baseline) { $Baseline = Join-Path $ExperimentsRoot 'v058\results_llm\v058_order_02_evidence.zip' }
if (-not $RunName) { $RunName = 'v064_direct_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff') }
$LogDir = Join-Path $VersionRoot ('results_llm\automation_logs\' + $RunName)
$ExitCode = 2
try {
    if (Test-Path -LiteralPath $LogDir) { throw 'Existing log directory; no retry or overwrite.' }
    [void][IO.Directory]::CreateDirectory($LogDir)
    $Log = Join-Path $LogDir 'run.log'
    [IO.File]::WriteAllText($Log, '', $utf8)
    $PythonExe = (Get-Command python.exe -ErrorAction Stop).Source
    $env:V064_BASELINE = (Resolve-Path -LiteralPath $Baseline).Path
    $Baseline = $env:V064_BASELINE
    . (Join-Path $PSScriptRoot 'native.ps1')
    $code = Invoke-PythonCapture $PythonExe @('-X','utf8','-B','-m','unittest','discover','-s','tests','-v') $ProbeRoot $Log
    if ($code -ne 0) { throw ('Selftest exit code: ' + $code) }
    $Plan = Join-Path $VersionRoot ('experiments\' + $RunName + '.plan.json')
    $code = Invoke-PythonCapture $PythonExe @('-X','utf8','-B','run.py','prepare','--baseline',$Baseline,'--run-name',$RunName,'--out',$Plan) $ProbeRoot $Log
    if ($code -ne 0) { throw ('Preparation exit code: ' + $code) }
    if ($CheckOnly) {
        [Console]::WriteLine('OFFLINE CHECK COMPLETE. No Ollama HTTP call or model inference.')
    } else {
        [Console]::WriteLine('USER RUN: maximum 18 inference calls; no download/start/retry.')
        $Out = Join-Path $VersionRoot ('results_llm\' + $RunName)
        $code = Invoke-PythonCapture $PythonExe @('-X','utf8','-B','run.py','execute','--plan',$Plan,'--baseline',$Baseline,'--out',$Out,'--endpoint',$Endpoint) $ProbeRoot $Log
        if ($code -ne 0) { throw ('Execution stopped; partial artifacts preserved. Exit code: ' + $code) }
    }
    $ExitCode = 0
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
}
if (-not $NoPause) { [void](Read-Host 'Press Enter to close') }
exit $ExitCode
