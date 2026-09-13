#requires -Version 5.1
[CmdletBinding()]
param([string]$BaselineBundle = '', [string]$RunName = '', [switch]$AllTests)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$PackageRoot = Split-Path -Parent $PSScriptRoot
$RepoRoot = Split-Path -Parent $PackageRoot
$Python = (Get-Command python -ErrorAction Stop).Source
$invokeArgs = @((Join-Path $PackageRoot 'tools\auto_run_v057.py'), '--repo-root', $RepoRoot)
if ($BaselineBundle) { $invokeArgs += @('--baseline-bundle', $BaselineBundle) }
if ($RunName) { $invokeArgs += @('--run-name', $RunName) }
if ($AllTests) { $invokeArgs += '--all-tests' }
# 네이티브 stderr의 문구가 아니라 프로세스 종료 코드로 성공/실패를 판단한다.
$ErrorActionPreference = 'Continue'
& $Python @invokeArgs
$code = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
exit $code
