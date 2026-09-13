# v063: v062 실패 원자료의 오프라인 진단 도구

v062는 공식 증명 성공 0/40으로 다음 깊이 실험의 사전 기준을 충족하지 못했다. v063은 **새 LLM 실험이 아니다.** 기존 v062 evidence를 읽고 오류 위치를 설명하는 소스 버전이다. [분석과 3자 교차토론](docs/V062_ANALYSIS.ko.md)에 판단과 이견을 기록했다.

원래 점수·actual_D·진입 판정을 그대로 유지한다. 별도로 최종 규칙과 목표의 문자열 일치, 기록된 최종 부모 연결 안팎의 노드와 오류를 보여 준다. 보정된 풀이, 조상만의 깊이, 새 성공률·프롬프트·실행 계획은 만들지 않는다.

진단의 `final_ancestor_ids`는 `final_node_id` 자신을 포함하고, 원문에 기록된 parents를 거슬러 도달하는 노드들의 집합이다. 이름이 중복되거나 최종 노드가 없어 연결을 명확히 정할 수 없으면 해당 위치 진단은 null로 둔다.

## 실행

Python 3.10 이상과 표준 라이브러리를 사용한다. 배포본의 `llm_experiments/v057`~`v063` 상대 위치를 유지한다. 원래 v062 evidence ZIP은 따로 보존해야 하며 소스 ZIP에 포함하지 않는다.

`windows/Run-v063.cmd`를 더블클릭하면 자체시험 후 기존 자료를 분석하고 독립 검산한다. 새 모델 호출이나 Ollama 시작은 없다. 다음 사용 가능한 `v063_forensics_XX` 폴더에 결과를 저장한다.

```powershell
windows\Run-v063.cmd -NoPause
```

원본 ZIP 위치가 다르면 `-EvidenceBundle <경로>`를 지정한다. 자체시험을 이미 마쳤다면 `-SkipSelfTest`를 사용할 수 있다. 기본 기대 SHA256은 검토한 v062_construction_01 ZIP의 `baea752ac1a55dc7a20b42b41ced69b3c8e126105f65deea8ebecc8dde3f09fd`다. 다른 정당한 v062 실행 자료를 분석할 때는 기대 해시를 확인해 `-ExpectedSha256 <SHA256>`도 명시해야 한다.

수동 실행은 `llm_experiments/v063/probe`에서 한다.

```powershell
python -X utf8 -B -m unittest discover -s tests -v
python -X utf8 -B tools/run_forensics.py ../../v062/results_llm/v062_construction_01_evidence.zip --out ../results_llm/v063_forensics_01
```

이미 존재하는 출력 폴더는 거부한다. 결과는 `analysis.json`, `independent.json`, `summary.ko.md`, `completion.json`이다. completion이 없으면 중단된 출력일 수 있으므로 완료로 취급하지 않는다. 입력 ZIP은 읽기만 하고 덮어쓰지 않는다.

## 개별 도구와 검증 범위

```powershell
python -X utf8 -B tools/analyze_v062.py <v062_evidence.zip> --out <새_analysis.json>
python -X utf8 -B tools/verify_forensics.py <v062_evidence.zip> <analysis.json> --out <새_receipt.json>
```

개별 도구는 엄격히 검산 가능한 v062 자료를 받으며, 진단 보고서의 입력 해시를 실제 제공된 ZIP과 대조한다. 전체 실행 도구는 이에 더해 사용자가 기대한 입력 해시를 시작 전에 검사한다.

이전 독립 검산기는 기존 공식 측정·계획·원문 일관성을 검사한다. 새 검산기는 분석기를 import하지 않고 추가 진단과 보고서 전체를 별도로 재구성한다. 두 도구가 공유하는 이전 검산 명세 자체의 오류나 외부 실행 인증까지 보장하지는 않는다.

이전 `parse_error` 설명 문구는 진단의 근거로 사용하지 않고, `raw_parse_category`를 원문에서 재생성해 비교한다. 이전 v062 소스·결과·검산 보증을 소급 변경하지 않는다. 상세한 단일 오류 원인은 `analysis.json`의 원문과 노드 오류를 함께 읽는다.

## 배포 검사

```powershell
python -X utf8 -B tools/build_release.py --out ../releases/v063_forensics_source_r1.zip
python -X utf8 -B tools/build_release.py --check ../releases/v063_forensics_source_r1.zip
```

최종 ZIP을 새 빈 폴더에 풀어 자체시험하고 별도 소스 감사를 수행한다. 검사·감사 결과는 ZIP 밖 `../validation/FINAL_REVIEW.ko.md`에 남긴다. 테스트용 합성 응답과 실제 모델 연구 결과를 합산하지 않는다.
