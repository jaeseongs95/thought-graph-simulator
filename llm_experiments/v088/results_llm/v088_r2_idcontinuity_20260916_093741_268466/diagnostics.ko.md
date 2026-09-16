# v088 바이트·후속 참조 진단

실패 trial: 213
존재하지 않는 부모를 출력한 규칙: 261
그 중 모든 누락 이름이 기존 원자와 같은 규칙: 235

| 단계 | 요청 | 고유(시드 포함) | 고유(시드 제외) |
|---|---:|---:|---:|
| continuation/long_mixed/final | 32 | 32 | 32 |
| continuation/long_mixed/rule | 140 | 140 | 124 |
| continuation/long_uniform/final | 32 | 32 | 32 |
| continuation/long_uniform/rule | 140 | 140 | 124 |
| continuation/short_mixed/final | 32 | 32 | 32 |
| continuation/short_mixed/rule | 140 | 140 | 124 |
| continuation/short_uniform/final | 32 | 32 | 32 |
| continuation/short_uniform/rule | 140 | 140 | 124 |
| end_to_end/allocated_id/facts | 128 | 128 | 128 |
| end_to_end/allocated_id/final | 128 | 128 | 128 |
| end_to_end/allocated_id/rule | 560 | 560 | 560 |
| end_to_end/baseline/facts | 128 | 128 | 128 |
| end_to_end/baseline/final | 128 | 128 | 128 |
| end_to_end/baseline/rule | 560 | 560 | 560 |
| end_to_end/shared_selection/compare | 128 | 40 | 20 |
| end_to_end/shared_selection/select | 128 | 96 | 48 |
| rename_probe/atom_alias/rule | 140 | 140 | 70 |
| rename_probe/legacy_long/rule | 140 | 140 | 70 |
| rename_probe/observed/rule | 140 | 140 | 70 |
| rename_probe/short/rule | 140 | 140 | 70 |

고유 바이트 수는 독립 문제 수가 아니다.
과거 사실·재명명 입력은 진단 지원이며 새 모델 증거로 세지 않는다.
초기 이력과 신규 응답을 구별한다. 원자 이름을 부모 ID로 자동 변환하지 않는다.
usage는 응답별 합이며 벽시계 시간이나 API 청구액이 아니다.
