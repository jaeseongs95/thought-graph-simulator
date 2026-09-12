# 현재 PowerShell 프로세스에만 설정한다. 다운로드·로그인·추론은 하지 않는다.
# 이미 실행 중인 Ollama를 강제 종료하지 않는다.
$ErrorActionPreference = "Stop"

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    throw "Ollama 명령을 찾지 못했습니다. Windows용 Ollama를 설치하고 새 터미널을 여세요."
}

$listener = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    throw "11434 포트가 사용 중입니다. 트레이의 Ollama를 Quit하거나 기존 서버를 정상 종료한 뒤 다시 실행하세요."
}

$env:OLLAMA_HOST = "127.0.0.1:11434"
$env:OLLAMA_NO_CLOUD = "1"
$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_MAX_LOADED_MODELS = "1"
$env:OLLAMA_CONTEXT_LENGTH = "8192"
$env:OLLAMA_KV_CACHE_TYPE = "f16"

Write-Host "로컬 전용 Ollama 서버를 시작합니다. 이 창은 열어 두세요."
Write-Host "다른 PowerShell 창에서 모델 다운로드와 local_llm 명령을 실행하세요."
& ollama serve
exit $LASTEXITCODE
