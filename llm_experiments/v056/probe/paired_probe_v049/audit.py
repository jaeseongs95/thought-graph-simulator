"""외부 동결 계획과 HTTP 원문에서 점수를 다시 계산하는 오프라인 감사."""
from __future__ import annotations
import csv
from collections import Counter
from pathlib import Path
from .contracts import (ContractError, EXPRS, canonical, decode_response, digest, read_json, require, require_external_plan, utc_now,
                        sha, strict_json, usage, write_json)
from .oracle import AND_TABLE, TABLE, evaluate, score_pipeline
from .plan import ARMS, input_key, make_request, slots, validate_plan
from .runner import check_identity


def _read_events(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    lines = path.read_bytes().splitlines()
    require(all(line.strip() for line in lines), "event 로그의 빈 행")
    return [strict_json(line) for line in lines]


def _source_snapshot(out: Path) -> dict:
    result = {}
    root = out / "source_snapshot"
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        result[path.relative_to(root).as_posix()] = sha(text.encode("utf-8"))
    return result


def audit_run(plan_path: Path, out: Path, *, write_report: bool = False) -> dict:
    """실패한 재감사에서 이전 PASS 파생 보고서를 현재 결과로 남겨 두지 않는다."""
    try:
        require_external_plan(plan_path, out)
        return _audit_run(plan_path, out, write_report=write_report)
    except (ContractError, OSError, KeyError, TypeError, ValueError) as exc:
        if write_report and out.is_dir():
            failure = {"contract": "v049-audit-failure-r1", "data_integrity": False,
                "data_complete": False, "comparative_analysis_ready": False,
                "last_audit_state": "failed", "at": utc_now(),
                "error": type(exc).__name__ + ": " + str(exc),
                "note": "직전 PASS 파생 요약은 무효화했다. 요청·응답·계획·event 원문은 수정하지 않았다."}
            write_json(out / "audit.json", failure)
            write_json(out / "summary.json", failure)
            (out / "summary.ko.md").write_text(
                "# v049 감사 실패\n\n이 실행을 비교 가능한 PASS 자료로 사용하지 마세요.\n\n"
                + failure["error"] + "\n\n" + failure["note"] + "\n", encoding="utf-8")
        raise


def _audit_run(plan_path: Path, out: Path, *, write_report: bool = False) -> dict:
    require(all(not p.is_symlink() for p in out.rglob("*")), "링크가 포함된 실행 원문은 감사하지 않습니다.")
    plan = read_json(plan_path); validate_plan(plan)
    require(canonical(read_json(out / "plan.snapshot.json")) == canonical(plan), "결과의 계획이 외부 동결 계획과 다릅니다.")
    manifest = read_json(out / "run_manifest.json"); status = read_json(out / "status.json")
    require(manifest["plan_sha256"] == plan["plan_sha256"], "run manifest 계획 불일치")
    require(manifest["source_fingerprint"] == plan["source_fingerprint"] == _source_snapshot(out),
            "실행 소스 스냅샷 불일치")
    require(manifest["evidence_kind"] == plan["baseline"]["evidence_kind"], "실제/합성 출처 변경")
    require(manifest["new_model_inference"] is (plan["baseline"]["evidence_kind"] != "synthetic_fixture"),
            "실제/합성 실행 라벨 불일치")
    require(type(status.get("complete")) is bool, "완료 상태 bool 필요")
    require(type(status.get("recorded_slots")) is int and type(status.get("inference_calls")) is int and
            type(status.get("runtime_identity_verified")) is bool and
            type(status.get("response_identity_mismatch")) is bool, "상태 필드 자료형 오류")
    require(status.get("state") in ("running", "complete", "interrupted", "incomplete"), "알 수 없는 실행 상태")
    require(manifest.get("retry_policy") == "none" and manifest.get("warmup_calls") == 0 and
            manifest.get("max_inference_calls") == plan["max_calls"], "실행 정책과 계획 불일치")
    complete = status["complete"]
    require(not complete or status.get("state") == "complete", "완료 상태 모순")
    identity = None
    identity_errors = []
    required_names = ["runtime.before.json"] + [f"runtime.round_{cycle:03d}.json" for cycle in range(1, plan["cycles"])] + ["runtime.after.json"]
    checkpoint_names = status.get("identity_checkpoints")
    require(isinstance(checkpoint_names, list) and len(set(checkpoint_names)) == len(checkpoint_names) and
            checkpoint_names == required_names[:len(checkpoint_names)], "모델 식별 점검 순서 오류")
    for name in required_names:
        path = out / name
        if path.is_file():
            try:
                found = check_identity(read_json(path), plan["baseline"])
                if identity is None:
                    identity = found
                require(found == identity, "실행 중 모델 식별 변경")
            except (ContractError, KeyError, TypeError, ValueError) as exc:
                identity_errors.append({"checkpoint": name, "error": str(exc)})
        elif name in checkpoint_names:
            raise ContractError("확인했다고 기록한 모델 식별 원문이 없습니다: " + name)
    if complete:
        require(checkpoint_names == required_names and not identity_errors and
                status["runtime_identity_verified"] is True and not status["response_identity_mismatch"],
                "완료 실행의 모델 식별 점검 누락/실패")
    events = _read_events(out / "events.jsonl"); expected_slots = slots(plan)
    require(len(events) <= len(expected_slots) and (not complete or len(events) == len(expected_slots)),
            "완료 실행에서 요청/blocked 기록 누락 또는 추가")
    require(status["recorded_slots"] == len(events), "기록 수 불일치")
    previous_hash = plan["plan_sha256"]; decoded = {}; entries = {}; resource_rows = []
    call_count = 0
    response_identity_errors = 0
    transport_failures = 0
    model = plan["baseline"]["config"]["model"]
    for index, event in enumerate(events):
        slot = expected_slots[index]
        require(canonical(event["slot"]) == canonical(slot), "사전 순서·입력·seed·조건과 event 불일치")
        require(event["previous_hash"] == previous_hash, "event hash 연결 누락")
        material = {k: v for k, v in event.items() if k != "event_hash"}
        require(event["event_hash"] == digest(material), "event 해시 불일치")
        previous_hash = event["event_hash"]
        parent_id = slot["block_id"] + "__not"; parent_value = None
        if slot["stage"] == "and":
            require(parent_id in entries, "AND의 부모 event가 없습니다.")
            parent_event = entries[parent_id]
            require(event["parent"] == {"id": parent_id, "response_sha256": parent_event["response_sha256"]},
                    "부모 ID/원문 해시 연결 변경")
            parent_value = decoded[parent_id]["value"]
        else:
            require(event["parent"] is None, "불필요한 부모 연결")
        if event["kind"] == "blocked":
            require(slot["stage"] == "and" and parent_value is None and
                    event["reason"] == "parent_has_no_valid_boolean", "정당하지 않은 자식 호출 생략")
            require(not (out / "calls" / slot["id"]).exists(), "blocked인데 실제 호출 자료가 있습니다.")
            decoded[slot["id"]] = {"value": None, "status": "blocked", "local_correct": False}
        else:
            require(event["kind"] == "call", "알 수 없는 event 종류")
            require(slot["stage"] != "and" or type(parent_value) is bool,
                    "부모값 없이 호출한 AND")
            folder = out / "calls" / slot["id"]
            request_raw = (folder / "request.wire.json").read_bytes()
            response_raw = (folder / "response.raw.json").read_bytes()
            require(sha(request_raw) == event["request_sha256"] and sha(response_raw) == event["response_sha256"],
                    "HTTP 요청/응답 원문 해시 변경")
            require(request_raw == make_request(plan, slot, parent_value), "사전 계약과 실제 전송 바이트 불일치")
            require(type(event["http_status"]) is int and 0 <= event["http_status"] <= 599 and
                    (event["transport_error"] is None or isinstance(event["transport_error"], str)) and
                    type(event["elapsed_ns"]) is int and event["elapsed_ns"] >= 0,
                    "전송 메타데이터 자료형 오류")
            # 기존 평가 점수를 읽지 않고 실제 expression을 별도 파서로 해석한다.
            body = strict_json(request_raw)
            inp = strict_json(body["messages"][1]["content"][7:])
            local_expected = evaluate(inp["expression"], inp["a"], inp["b"])
            table_expected = (TABLE[slot["a"], slot["b"]][1] if slot["stage"] == "not" else
                              AND_TABLE[slot["a"], parent_value] if slot["stage"] == "and" else
                              TABLE[slot["a"], slot["b"]][0])
            require(local_expected is table_expected, "독립 파서와 수동 진리표가 불일치합니다.")
            value = None; error = None; record_status = "transport_error"
            if event["http_status"] == 200 and event["transport_error"] is None:
                try:
                    value = decode_response(response_raw, model)["value"]
                    record_status = "correct_local" if value is local_expected else "wrong_boolean"
                except ContractError as exc:
                    error = str(exc); record_status = "invalid_response"
            else:
                error = event["transport_error"] or "HTTP " + str(event["http_status"])
            content_hash = None
            try:
                envelope = strict_json(response_raw)
                if isinstance(envelope, dict):
                    message = envelope.get("message")
                    if isinstance(message, dict) and isinstance(message.get("content"), str):
                        content_hash = sha(message["content"].encode("utf-8"))
                    if isinstance(envelope.get("model"), str) and envelope["model"] != model:
                        response_identity_errors += 1
                        record_status = "response_identity_error"
            except ContractError:
                pass
            if event["http_status"] != 200 or event["transport_error"] is not None:
                transport_failures += 1
            decoded[slot["id"]] = {"value": value, "status": record_status, "error": error,
                                   "local_correct": type(value) is bool and value is local_expected}
            resource_rows.append({"call_id": slot["id"], "block_id": slot["block_id"],
                "seed": slot["seed"], "cycle": slot["cycle"], "position": slot["position"],
                "arm": slot["arm"], "stage": slot["stage"], "event_index": index,
                "request_sha256": event["request_sha256"], "response_content_sha256": content_hash,
                "value": value, "status": record_status,
                "elapsed_ns": event["elapsed_ns"], **usage(response_raw)})
            call_count += 1
        entries[slot["id"]] = event
    require(status["response_identity_mismatch"] is (response_identity_errors > 0), "응답 모델 불일치 상태 변경")
    if complete:
        require(transport_failures == 0 and response_identity_errors == 0, "실행 오류가 있는데 완료로 표시됐습니다.")
    require(status["event_tip"] == previous_hash, "마지막 event seal 불일치")
    if complete:
        require(status["inference_calls"] == call_count, "실제 호출 수 불일치")
        expected_dirs = {e["slot"]["id"] for e in events if e["kind"] == "call"}
        actual_dirs = {p.name for p in (out / "calls").iterdir() if p.is_dir()}
        require(actual_dirs == expected_dirs, "완료 실행에 숨겨진/누락된 호출 폴더")
        expected_files = {name + "/" + leaf for name in expected_dirs
                          for leaf in ("request.wire.json", "response.raw.json")}
        actual_files = {p.relative_to(out / "calls").as_posix()
                        for p in (out / "calls").rglob("*") if p.is_file()}
        require(actual_files == expected_files, "완료 실행에 미등록/누락된 요청·응답 파일")
    else:
        require(call_count <= status["inference_calls"] <= call_count + 1, "미완료 실행의 시도 수 불일치")
    trials = []
    for block in plan["blocks"]:
        a, b = block["a"], block["b"]
        for arm in ARMS:
            final_stage = "and" if arm == "pipeline" else arm
            final = decoded.get(block["id"] + "__" + final_stage,
                                {"value": None, "status": "not_recorded"})
            parent = decoded.get(block["id"] + "__not", {"value": None, "status": "not_recorded"})
            row = {"block_id": block["id"], "seed": block["seed"], "cycle": block["cycle"],
                   "a": a, "b": b, "arm": arm, "order_position": block["arms"].index(arm),
                   "expected": TABLE[a, b][0], "value": final["value"], "status": final["status"],
                   "observed": final["status"] != "not_recorded",
                   "final_correct": (type(final["value"]) is bool and final["value"] is TABLE[a, b][0]) if final["status"] != "not_recorded" else None,
                   "parent_value": parent["value"] if arm == "pipeline" else None,
                   "not_correct": None, "and_local_correct": None, "trace_correct": None}
            if arm == "pipeline":
                row.update(score_pipeline(a, b, parent["value"], final["value"]))
            if not row["observed"]:
                row.update(final_correct=None, not_correct=None, and_local_correct=None, trace_correct=None)
            trials.append(row)
    from .reporting import summarize, write_markdown, write_csv
    report = summarize(plan, trials, resource_rows, decoded, complete)
    report.update({"data_integrity": True, "data_complete": complete,
                   "comparative_analysis_ready": complete and status["runtime_identity_verified"],
                   "plan_sha256": plan["plan_sha256"], "event_tip": previous_hash,
                   "evidence_kind": manifest["evidence_kind"],
                   "new_model_inference": manifest["new_model_inference"],
                   "runtime_identity": identity, "identity_errors": identity_errors, "run_state": status["state"], "run_error": status["error"],
                   "recorded_slots": len(events), "inference_calls": call_count,
                   "unrecorded_inference_attempts": status["inference_calls"] - call_count,
                   "max_inference_calls": plan["max_calls"], "trials": trials,
                   "reference_anchor": plan["reference"]["anchor"],
                   "reference_plan_sha256": plan["reference"]["plan_sha256"],
                   "source_fingerprint": plan["source_fingerprint"]})
    if write_report:
        write_json(out / "summary.json", report)
        write_markdown(out / "summary.ko.md", report)
        write_csv(out / "calls.csv", resource_rows)
        write_csv(out / "seeds.csv", report["per_seed"])
        write_csv(out / "request_repeats.csv", report["request_repeats"])
        write_json(out / "seed_results.json", {"data_complete": complete, "per_seed": report["per_seed"],
            "paired_final_outcomes": report["paired_final_outcomes"], "behavior_patterns": report["behavior_patterns"]})
        with (out / "trials.csv").open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(trials[0]))
            writer.writeheader(); writer.writerows(trials)
        write_json(out / "audit.json", {"data_integrity": True, "data_complete": complete,
            "plan_sha256": plan["plan_sha256"], "event_tip": previous_hash,
            "model_accuracy_is_not_integrity": True})
    return report


