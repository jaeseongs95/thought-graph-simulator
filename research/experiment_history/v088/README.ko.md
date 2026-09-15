# v088 소스 및 실제 검증 자료

`Run-v088-Auto.ps1`은 소스 ZIP이 내장된 사용자 실행 파일입니다. `v088_실험설계_검증결과.md`와 소스 내부 사전등록을 먼저 읽으세요. 기존 v087 evidence ZIP은 별도로 보존해야 합니다.

## 포함 범위

validation에는 최종 설치본의 고유 자체시험 85개(84 통과/1 제외), calibration 1,504개, 전체 합성 3,136호출의 독립 검산·요약·진단·로그, 소스 일치 결과가 있습니다. 해당 호출은 모의 응답이며 실제 Qwen 추론은 0회입니다.

사용자 원본 evidence와 약 139.4MiB의 합성 전체 evidence는 이 묶음에 중복 포함하지 않았습니다. 모든 재현 코드는 소스 ZIP에 있으며 별도 원본 v087 evidence를 사용합니다. 로그 속 절대 경로는 실행 기록이고 사용자의 경로 조건이 아닙니다.

## 재현

PS1 `-CheckOnly -AllTests`는 설치·전체 자체시험·calibration·계획 생성까지 실행합니다. 실제 Ollama를 조회하지 않습니다. 설치 후 probe 디렉터리에서 다음을 실행하면 전체 합성 evidence를 새 폴더에 생성하고 검산합니다.

```text
python -X utf8 -B reproduce_synthetic.py --baseline <원본 v087 evidence.zip> --out <존재하지 않는 새 검증 폴더>
```

`validation/final_artifact_check.py`는 개발 경로에서 실제 수행한 포장 일치 검사이며 환경 독립 실행 진입점은 아닙니다. 사용자 재현에는 위 소스의 실행기를 사용하세요. PowerShell 네이티브 파서 시험은 개발 Linux 환경에서 제외됐으며 Windows 완료를 주장하지 않습니다.

A의 단일 규칙, B의 지원된 초기 사실에서의 연속 생성, C의 새 선택·facts를 포함한 D 종단은 각각 별도 평가입니다. 합성 성공률과 이전 evidence를 새 연구 관측으로 합산하지 않습니다.
