#requires -Version 5.1
param(
    [string]$RepoRoot='',
    [string]$Baseline='',
    [string]$PythonPath='',
    [string]$RunName='',
    [string]$Endpoint='http://127.0.0.1:11434',
    [switch]$CheckOnly,
    [switch]$InspectOnly,
    [switch]$AllTests,
    [switch]$NoOpen
)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
$OutputEncoding=New-Object System.Text.UTF8Encoding($false)
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONDONTWRITEBYTECODE='1'
$ExitCode=2
# 고정 소스 ZIP이다. 외부 다운로드, 모델 갱신, Ollama 시작을 하지 않는다.
$ExpectedSha256='__SHA256__'
$EmbeddedSource=@'
__PAYLOAD__
'@
try {
    $Bytes=[Convert]::FromBase64String($EmbeddedSource)
    $Hasher=[Security.Cryptography.SHA256]::Create()
    try { $ActualSha256=([BitConverter]::ToString($Hasher.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant() }
    finally { $Hasher.Dispose() }
    if ($ActualSha256 -ne $ExpectedSha256) { throw '내장 v081 소스 ZIP의 SHA-256이 다릅니다. 실행하지 않습니다.' }
    $TempRoot=Join-Path ([IO.Path]::GetTempPath()) ('ADM_v081_'+[Guid]::NewGuid().ToString('N'))
    [void][IO.Directory]::CreateDirectory($TempRoot)
    $ZipPath=Join-Path $TempRoot 'v081_source.zip'
    [IO.File]::WriteAllBytes($ZipPath,$Bytes)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::ExtractToDirectory($ZipPath,(Join-Path $TempRoot 'release'))
    $Probe=Join-Path $TempRoot 'release\llm_experiments\v081\probe'
    $Candidates=New-Object 'System.Collections.Generic.List[string]'
    if ($PythonPath) { $Candidates.Add($PythonPath) }
    $LocalData=[Environment]::GetFolderPath('LocalApplicationData')
    foreach ($Version in @('312','313','314','311','310')) {
        $Candidates.Add((Join-Path $LocalData ('Programs\Python\Python'+$Version+'\python.exe')))
    }
    $Command=Get-Command python.exe -ErrorAction SilentlyContinue
    if ($Command -and $Command.Source -and $Command.Source -notmatch '\\WindowsApps\\') { $Candidates.Add($Command.Source) }
    $Python=$null
    foreach ($Candidate in $Candidates) {
        if (Test-Path -LiteralPath $Candidate -PathType Leaf) { $Python=(Resolve-Path -LiteralPath $Candidate).Path; break }
    }
    if (-not $Python) { throw 'Python 3.10 이상을 찾지 못했습니다. -PythonPath에 기존 python.exe 경로를 지정하세요. 자동 설치하지 않습니다.' }
    $Arguments=@('-X','utf8','-B',(Join-Path $Probe 'launch.py'),'--endpoint',$Endpoint)
    if ($RepoRoot) { $Arguments+=@('--repo-root',$RepoRoot) }
    if ($Baseline) { $Arguments+=@('--baseline',$Baseline) }
    if ($RunName) { $Arguments+=@('--run-name',$RunName) }
    if ($CheckOnly) { $Arguments+='--check-only' }
    if ($InspectOnly) { $Arguments+='--inspect-only' }
    if ($AllTests) { $Arguments+='--all-tests' }
    if ($NoOpen) { $Arguments+='--no-open' }
    Write-Host ('내장 소스 SHA-256: '+$ActualSha256)
    Write-Host ('Python: '+$Python)
    Write-Host ('소스 추출 위치: '+$TempRoot)
    # native stderr 유무가 아니라 프로세스 종료 코드로 판정한다.
    $ErrorActionPreference='Continue'
    & $Python @Arguments
    $ExitCode=$LASTEXITCODE
    $ErrorActionPreference='Stop'
    if ($ExitCode -ne 0) { [Console]::Error.WriteLine('v081이 중단되었습니다. 출력된 증거와 로그를 보존하고 자동 재시도하지 않습니다.') }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    [Console]::Error.WriteLine('기존 결과를 덮어쓰거나 모델을 자동 재실행하지 않습니다.')
    $ExitCode=2
}
exit $ExitCode
