"""오프라인 실행 준비 검사. 모델의 의미적 실패를 연구 표본에서 배제하지 않는다.

v0.2 이관은 동결된 배포 소스와 요청 바이트가 일치할 때만 허용한다.
첨부 source_snapshot의 Python은 읽고 해시만 검사하며 실행하지 않는다.
내부 해시는 변경 탐지용이며 외부 전자서명/독립적 진본 보장은 아니다.
"""
from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path
from typing import Any

from .common import (bytes_hash, read_json, require, source_fingerprint, wire_json,
                     source_text_identity, require_core_compatible)
from .design import build_plan
from .model_policy import response_channels
from .report import read_records

# 이전에 배포한 v0.2.0 소스에서 동결. 사용자 입력에서 승인 목록을 만들지 않는다.
LEGACY_V02_SOURCE_FINGERPRINT = {
    "__init__.py": "7af4bb119f7d7d6904b1b3eb878aa9026775ace5126feebfae19fbe0952c1059",
    "__main__.py": "8e03ddda1c0b632c806004ff300351382b2651a12651186d5f7f739188309196",
    "audit.py": "9856eb445da5669fcc8a9f059d4c7ea20d2f9f0ce32cb0eb52b2860cc25e2834",
    "calibration.py": "53a1f9e8bc9f1974881390f4c886641ce540497d385dccbbaaf80a10feb7036f",
    "client.py": "20828bec12e77800883be188d3b4258dca033db00831c91dfec2764254babe27",
    "common.py": "358cd6775c0e85d1fadbeb4615d0bbe11d5dd7cbf17e6f13aed706ace3a9a881",
    "design.py": "09806b9c7bbd9c86ac1766ea009a5614644d655edd515d117e089632f83d8f77",
    "diagnostics.py": "6d359fa6dd1f84362ed90cf84c393e4a0324d4de67e9a4ddc66d6dbceb375c8a",
    "prompts.py": "1a2f1e3a21c7abfbf329f49cb8c8b846d3acafe09ea4a58e2289bdb2b109881c",
    "prompts_v2.py": "e392d05b0807467826f7693f9ebc52f65dc9e8ec21bf9f84595c7353db4ba822",
    "protocol.py": "c9d5a0c43fbcc8093433c52759ad9fc311c256b182680c0a003c23580d2a2f35",
    "protocol_v2.py": "458546c3230adad7323b237ed9b34dab7f268d4385099cd56fce3271db39319a",
    "report.py": "0c2fe6f6647feecfc7ef173abcdb2a70b770477b6e9edd5f71f6d31a56845eae",
    "runner.py": "17af2e20ebab0efb1bf1155b6e6abf1bb9524e42125646d0b584c1c64a6300df",
    "selfcheck.py": "b432eb5125c721ed43f851374a294231a123b8bff4a9028fafb93a4213c25ef8"
}


def normalized_config(config: dict) -> dict:
    result = copy.deepcopy(config)
    result.setdefault("prompt_profile", "legacy-v2")
    return result


def validate_gate(core: Any, gate: Path, config: dict, next_plan: dict,
                  mode: str = "readiness") -> dict:
    """LLM 호출 없이 보존된 모든 smoke 응답을 재검사한다.

    readiness: 기록 완결성, 같은 실험 입력/설정, 정상 API 종료, 검사기 정상 여부.
    strict: 위 조건에 더해 모든 응답의 의미·역할 성공을 요구하는 별도 성능 게이트.
    """
    from .runner import assess_response, request_body
    require(mode in {"readiness", "strict"}, "알 수 없는 게이트 모드")
    gate = gate.resolve()
    manifest = read_json(gate / "manifest.json")
    frozen = manifest["frozen"]
    previous = frozen["plan"]
    require(previous["profile"] == "smoke" and previous.get("experiment_kind", "joint") == "joint",
            "게이트에는 통합 smoke 결과 폴더를 지정하세요.")
    require(normalized_config(frozen["config"]) == normalized_config(config),
            "smoke와 모델·프롬프트 프로필·추론·샘플링 설정이 다릅니다.")
    require(previous["seed"] == next_plan["seed"], "smoke와 주 실험의 시작 시드가 다릅니다.")
    require(previous["problems"] == next_plan["problems"][:1], "smoke는 주 실험의 첫 문제와 같아야 합니다.")
    expected_plan = build_plan(core, next_plan["problems"], "smoke", previous["repeats"], next_plan["seed"])
    require(previous == expected_plan, "smoke 조건표가 표준 배정과 다릅니다. 일부 조건만 고를 수 없습니다.")

    saved_sources = frozen["runtime_sources_sha256"]
    current_sources = source_fingerprint()
    same_sources = saved_sources == current_sources
    legacy = (frozen.get("extension_version") == "0.2.0"
              and saved_sources == LEGACY_V02_SOURCE_FINGERPRINT
              and normalized_config(config)["prompt_profile"] == "legacy-v2")
    require(same_sources or legacy,
            "승인되지 않은 런타임 변경입니다. 현재 소스로 smoke를 실행하세요. "
            "기존 v0.2 결과는 기본 legacy-v2 프로필에서만 이관할 수 있습니다.")
    for name, expected in saved_sources.items():
        require(Path(name).name == name, "소스 스냅샷 경로 오류")
        path = gate / "source_snapshot" / name
        require(path.is_file() and bytes_hash(path.read_bytes()) == expected,
                f"소스 스냅샷 누락/해시 불일치: {name}")
    core_snapshot = gate / "source_snapshot" / "adm_minimal.py"
    require(core_snapshot.is_file(), "검증기 스냅샷 누락")
    snapshot_bytes = core_snapshot.read_bytes()
    require(bytes_hash(snapshot_bytes) == frozen["core"]["sha256"],
            "검증기 스냅샷 자체가 실행 manifest와 다릅니다.")
    current_core = source_text_identity(Path(core.__file__).read_bytes())
    snapshot_core = source_text_identity(snapshot_bytes)
    require_core_compatible(snapshot_core, current_core,
                            "smoke와 현재 검증기의 실제 소스 내용이 다릅니다.")

    records = read_records(gate, manifest)
    require(len(records) == len(previous["cases"]), "smoke가 완료되지 않았습니다.")
    problems = {p["id"]: p for p in previous["problems"]}
    rows = []
    for record in records:
        case = record["case"]
        folder = gate / "cases" / case["case_id"]
        problem = problems[case["problem_id"]]
        expected = request_body(config, case, problem)
        saved_request = read_json(folder / "request.json")
        require(saved_request.get("case_id") == case["case_id"]
                and saved_request.get("run_sha256") == manifest["run_sha256"], "smoke 요청 결합 오류")
        require(saved_request["body"] == expected, "smoke 요청 내용 변경")
        wire = folder / "request.wire.json"
        require(wire.is_file() and wire.read_bytes() == wire_json(expected).encode("utf-8"),
                "smoke HTTP 원문 누락/변경")
        require(saved_request.get("wire_sha256") == bytes_hash(wire.read_bytes()), "smoke HTTP 원문 해시 불일치")
        require((folder / "response.raw.json").is_file(), "smoke 응답 누락")
        response = read_json(folder / "response.raw.json")
        message = response.get("message")
        require(response.get("model") == expected["model"] and response.get("done") is True
                and response.get("done_reason") == "stop", "smoke API 모델/종료 조건이 정상적이지 않습니다.")
        require(isinstance(message, dict) and message.get("role") == "assistant"
                and isinstance(message.get("content"), str), "smoke assistant 응답 형식 오류")
        require(not message.get("tool_calls"), "smoke에 실행하지 않은 도구 호출이 있습니다.")
        response_channels(expected, response, config.get("mode_policy"))
        require(expected.get("think") is not False or not message.get("thinking"), "smoke thinking 설정 불일치")
        require(record.get("status") not in {"harness_error", "transport_error", "interrupted", "interrupted_unknown", "truncated", "mode_error"},
                "smoke에 하네스·통신 오류 또는 중단/길이 제한이 있습니다.")
        saved_gpu_digest = (record.get("gpu") or {}).get("digest")
        require(not saved_gpu_digest or saved_gpu_digest == frozen["model"]["digest"], "smoke 실행 모델 digest 불일치")
        outcome, _ = assess_response(core, problem, case, previous["reference_depths"][problem["id"]], expected, response, config.get("mode_policy"))
        require(outcome["status"] not in {"harness_error", "mode_error"}, "검증기 자체 검사에서 오류가 발견됐습니다.")
        require(outcome["status"] == record["status"], "smoke 저장 상태와 원문 재판정이 다릅니다.")
        if mode == "strict":
            require(outcome["status"] == "accepted", "strict 성능 게이트: smoke에 의미/역할 실패가 있습니다.")
        rows.append({"case_id": case["case_id"], "role": case["role_id"],
                     "replayed_status": outcome["status"], "error": outcome.get("error")})
    counts = dict(Counter(row["replayed_status"] for row in rows))
    return {"passed": True, "mode": mode, "source_run_sha256": manifest["run_sha256"],
            "source_manifest_sha256": bytes_hash((gate / "manifest.json").read_bytes()),
            "source_compatibility": "same_runtime" if same_sources else "pinned_v02_legacy_requests",
            "replayed_cases": len(rows), "status_counts": counts,
            "model_failures_retained": sum(row["replayed_status"] != "accepted" for row in rows),
            "request_bytes_verified": True, "model_called": False,
            "live_model_digest_checked": False, "cases": rows,
            "note": "실행 준비 통과와 성능 통과는 별도다. 모델 실패는 원래 실패 상태로 남긴다. "
                    "실제 실행 직전 서버 버전과 모델 digest는 다시 조회한다."}
