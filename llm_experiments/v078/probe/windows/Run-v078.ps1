#requires -Version 5.1
param([switch]$CheckOnly,[switch]$AllTests,[switch]$NoPause,[string]$RepoRoot='',[string]$Baseline='')
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONDONTWRITEBYTECODE='1'
$Probe=Split-Path $PSScriptRoot -Parent
$code=2
try {
    $py=(Get-Command python.exe -ErrorAction Stop).Source
    $argv=@('-X','utf8','-B',(Join-Path $Probe 'launch.py'))
    if ($RepoRoot) { $argv+=@('--repo-root',$RepoRoot) }
    if ($Baseline) { $argv+=@('--baseline',$Baseline) }
    if ($CheckOnly) { $argv+='--check-only' }
    if ($AllTests) { $argv+='--all-tests' }
    $ErrorActionPreference='Continue'
    & $py @argv
    $code=$LASTEXITCODE
    $ErrorActionPreference='Stop'
} catch { [Console]::Error.WriteLine($_.Exception.Message) }
if (-not $NoPause) { [void](Read-Host 'Press Enter to close') }
exit $code
