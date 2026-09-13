"""외부 동결 계획과 HTTP 원문에서 점수를 다시 계산하는 오프라인 감사."""
from __future__ import annotations
import csv
from collections import Counter
from pathlib import Path
from .contracts import (ContractError, EXPRS, decode_response, digest, read_json, require,
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
    for path in sorted((out / "source_snapshot").glob("*.py")):
        text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        result[path.name] = sha(text.encode("utf-8"))
    return result


def audit_run(plan_path: Path, out: Path, *, write_report: bool = False) -> dict:
    plan = read_json(plan_path); validate_plan(plan)
    require(read_json(out / "plan.snapshot.json") == plan, "결과의 계획이 외부 동결 계획과 다릅니다.")
    manifest = read_json(out / "run_manifest.json"); status = read_json(out / "status.json")
    require(manifest["plan_sha256"] == plan["plan_sha256"], "run manifest 계획 불일치")
    require(manifest["source_fingerprint"] == plan["source_fingerprint"] == _source_snapshot(out),
            "실행 소스 스냅샷 불일치")
    require(manifest["evidence_kind"] == plan["baseline"]["evidence_kind"], "실제/합성 출처 변경")
    require(manifest["new_model_inference"] is (plan["baseline"]["evidence_kind"] != "synthetic_fixture"),
            "실제/합성 실행 라벨 불일치")
    require(type(status.get("complete")) is bool, "완료 상태 bool 필요")
    complete = status["complete"]
    require(not complete or status.get("state") == "complete", "완료 상태 모순")
    before = out / "runtime.before.json"; after = out / "runtime.after.json"
    identity = None
    if before.is_file():
        identity = check_identity(read_json(before), plan["baseline"])
    if complete:
        require(before.is_file() and after.is_file() and status["runtime_identity_verified"] is True,
                "완료 실행의 전/후 모델 식별 자료 누락")
        require(check_identity(read_json(after), plan["baseline"]) == identity, "실행 전/후 모델 식별 변경")
    events = _read_events(out / "events.jsonl"); expected_slots = slots(plan)
    require(len(events) <= len(expected_slots) and (not complete or len(events) == len(expected_slots)),
            "완료 실행에서 요청/blocked 기록 누락 또는 추가")
    require(status["recorded_slots"] == len(events), "기록 수 불일치")
    previous_hash = plan["plan_sha256"]; decoded = {}; entries = {}; resource_rows = []
    call_count = 0
    model = plan["baseline"]["config"]["model"]
    for index, event in enumerate(events):
        slot = expected_slots[index]
        require(event["slot"] == slot, "사전 순서·입력·seed·조건과 event 불일치")
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
            require(type(event["http_status"]) is int and type(event["elapsed_ns"]) is int and event["elapsed_ns"] >= 0,
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
            decoded[slot["id"]] = {"value": value, "status": record_status, "error": error,
                                   "local_correct": type(value) is bool and value is local_expected}
            resource_rows.append({"arm": slot["arm"], "stage": slot["stage"],
                                  "elapsed_ns": event["elapsed_ns"], **usage(response_raw)})
            call_count += 1
        entries[slot["id"]] = event
    require(status["event_tip"] == previous_hash, "마지막 event seal 불일치")
    if complete:
        require(status["inference_calls"] == call_count, "실제 호출 수 불일치")
        expected_dirs = {e["slot"]["id"] for e in events if e["kind"] == "call"}
        actual_dirs = {p.name for p in (out / "calls").iterdir() if p.is_dir()}
        require(actual_dirs == expected_dirs, "완료 실행에 숨겨진/누락된 호출 폴더")
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
                   "final_correct": type(final["value"]) is bool and final["value"] is TABLE[a, b][0],
                   "parent_value": parent["value"] if arm == "pipeline" else None,
                   "not_correct": None, "and_local_correct": None, "trace_correct": None}
            if arm == "pipeline":
                row.update(score_pipeline(a, b, parent["value"], final["value"]))
            trials.append(row)
    report = summarize(plan, trials, resource_rows, decoded, complete)
    report.update({"data_integrity": True, "data_complete": complete,
                   "comparative_analysis_ready": complete and status["runtime_identity_verified"],
                   "plan_sha256": plan["plan_sha256"], "event_tip": previous_hash,
                   "evidence_kind": manifest["evidence_kind"],
                   "new_model_inference": manifest["new_model_inference"],
                   "runtime_identity": identity, "run_state": status["state"], "run_error": status["error"],
                   "recorded_slots": len(events), "inference_calls": call_count,
                   "unrecorded_inference_attempts": status["inference_calls"] - call_count,
                   "max_inference_calls": plan["max_calls"], "trials": trials})
    if write_report:
        write_json(out / "summary.json", report)
        write_markdown(out / "summary.ko.md", report)
        with (out / "trials.csv").open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(trials[0]))
            writer.writeheader(); writer.writerows(trials)
        write_json(out / "audit.json", {"data_integrity": True, "data_complete": complete,
            "plan_sha256": plan["plan_sha256"], "event_tip": previous_hash,
            "model_accuracy_is_not_integrity": True})
    return report


def summarize(plan: dict, trials: list[dict], resources: list[dict], decoded: dict, complete: bool) -> dict:
    arm_reports = {}
    for arm in ARMS:
        rows = [r for r in trials if r["arm"] == arm]
        positives = [r for r in rows if r["expected"]]
        negatives = [r for r in rows if not r["expected"]]
        pos_correct = sum(r["final_correct"] for r in positives)
        neg_correct = sum(r["final_correct"] for r in negatives)
        tables = []
        for seed in plan["seeds"]:
            for cycle in range(plan["cycles"]):
                cells = [r for r in rows if r["seed"] == seed and r["cycle"] == cycle]
                tables.append({"seed": seed, "cycle": cycle, "final_four_of_four": all(r["final_correct"] for r in cells),
                    "trace_four_of_four": all(r["trace_correct"] for r in cells) if arm == "pipeline" else None})
        metrics = {}; costs = [r for r in resources if r["arm"] == arm]
        for key in ("elapsed_ns", "prompt_eval_count", "prompt_eval_cached_count", "eval_count", "total_duration",
                    "load_duration", "prompt_eval_duration", "eval_duration"):
            vals = [r[key] for r in costs if r[key] is not None]
            metrics[key] = {"total": sum(vals) if costs and len(vals) == len(costs) else None,
                            "known_sum": sum(vals), "observed_calls": len(vals), "actual_calls": len(costs)}
        arm_reports[arm] = {"assigned": len(rows), "valid_final_values": sum(type(r["value"]) is bool for r in rows),
            "final_correct": sum(r["final_correct"] for r in rows),
            "final_accuracy": sum(r["final_correct"] for r in rows) / len(rows) if complete else None,
            "strict_trace_correct": sum(r["trace_correct"] for r in rows) if arm == "pipeline" else None,
            "positive_correct": pos_correct, "positive_assigned": len(positives),
            "negative_correct": neg_correct, "negative_assigned": len(negatives),
            "balanced_accuracy": (pos_correct / len(positives) + neg_correct / len(negatives)) / 2 if complete else None,
            "per_input": {key: {"correct": sum(r["final_correct"] for r in rows if input_key(r["a"], r["b"]) == key),
                                  "assigned": sum(input_key(r["a"], r["b"]) == key for r in rows)}
                          for key in ("00", "01", "10", "11")},
            "status_counts": dict(Counter(r["status"] for r in rows)),
            "four_of_four_repeats": sum(t["final_four_of_four"] for t in tables),
            "tables": tables, "costs": metrics}
    pairs = {}
    for contender in ("commuted", "pipeline"):
        paired = {"both_correct": 0, "original_only": 0, "contender_only": 0, "neither_correct": 0}
        seed_deltas = []
        for seed in plan["seeds"]:
            deltas = []
            for block in [b for b in plan["blocks"] if b["seed"] == seed]:
                rows = {r["arm"]: r for r in trials if r["block_id"] == block["id"]}
                left, right = rows["original"]["final_correct"], rows[contender]["final_correct"]
                category = ("both_correct" if left and right else "original_only" if left else
                            "contender_only" if right else "neither_correct")
                paired[category] += 1; deltas.append(int(right) - int(left))
            seed_deltas.append({"seed": seed, "final_accuracy_delta": sum(deltas) / len(deltas) if complete else None})
        pairs[contender + "-original"] = {**paired,
            "final_accuracy_delta": (paired["contender_only"] - paired["original_only"]) / len(plan["blocks"]) if complete else None,
            "per_seed": seed_deltas, "inferential_p_value": None,
            "note": "동일 seed 반복/동일 4개 입력을 독립 과제 표본으로 간주하지 않음"}
    options = plan["baseline"]["config"]["options"]
    return {"arms": arm_reports, "paired_final_outcomes": pairs,
        "call_status_counts": dict(Counter(d["status"] for d in decoded.values())),
        "seeds": plan["seeds"], "cycles": plan["cycles"], "temperature": options.get("temperature"),
        "seed_interpretation": "seed 변경은 새로운 문제 표본이 아니다. temperature=0이면 샘플링 다양성이 생기지 않을 수 있다.",
        "scope": "이 1개 식·4개 입력의 행동 재현. 순수 호출 횟수 효과·내부 원인·ADM 성과·계산량 우월성은 판정하지 않는다.",
        "fairness": "직접 경로와는 최종값끼리 비교하고, 파이프라인의 중간값 포함 성공은 별도 지표로 보고한다."}


def write_markdown(path: Path, report: dict) -> None:
    lines = ["# v047 동일 배치 대조 결과", "",
        f'- 출처: **{report["evidence_kind"]}**',
        f'- 자료 무결성: **{report["data_integrity"]}** / 수집 완료: **{report["data_complete"]}**',
        f'- 비교 가능: **{report["comparative_analysis_ready"]}**',
        f'- 실제 기록된 추론 요청: **{report["inference_calls"]}/{report["max_inference_calls"]}**',
        f'- seed: `{report["seeds"]}`, 반복: `{report["cycles"]}`, temperature: `{report["temperature"]}`', "",
        "자료가 유효하다는 판정과 모델 정답률은 서로 다르다. 실패를 올바르게 기록한 실행도 자료는 유효하다.", "",
        "| 조건 | 최종값 정답 | 양성 조건 정답 | 전체 진리표 4/4 반복 | 중간값 포함 성공 |",
        "|---|---:|---:|---:|---:|"]
    for arm, r in report["arms"].items():
        trace = "측정 대상 아님" if r["strict_trace_correct"] is None else f'{r["strict_trace_correct"]}/{r["assigned"]}'
        lines.append(f'| {arm} | {r["final_correct"]}/{r["assigned"]} | {r["positive_correct"]}/{r["positive_assigned"]} '
                     f'| {r["four_of_four_repeats"]}/{len(r["tables"])} | {trace} |')
    lines += ["", "## 해석", "", report["fairness"], "", report["seed_interpretation"], "", report["scope"], "",
              "## 비교 지표", "", "| 대조 | 원식만 정답 | 대조식만 정답 | 최종 정답률 차이 |", "|---|---:|---:|---:|"]
    for name, p in report["paired_final_outcomes"].items():
        lines.append(f'| {name} | {p["original_only"]} | {p["contender_only"]} | {p["final_accuracy_delta"]} |')
    lines += ["", "실측 호출 수·입력/출력 토큰·서버 시간의 상세값은 `summary.json`에 있다. 누락값은 null이며 0으로 대체하지 않는다.",
              "동일 토큰 수는 서로 다른 크기 모델의 동일 FLOPs를 뜻하지 않는다.", "",
              f'계획 SHA-256: `{report["plan_sha256"]}`', f'마지막 event 해시: `{report["event_tip"]}`', "",
              "해시는 외부 동결 계획 및 원문 사이의 일관성을 검사한다. 전 자료와 해시를 함께 바꾸는 공격이나 실제 서버 실행을 외부에서 증명하는 전자서명은 아니다."]
    if not report["data_complete"]:
        lines += ["", "**미완료 실행: 이 자료를 완결된 성공률 비교로 사용하지 않는다.**", str(report["run_error"])]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
