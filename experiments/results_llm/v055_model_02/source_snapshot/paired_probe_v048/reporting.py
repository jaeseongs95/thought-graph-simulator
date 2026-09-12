"""seed별 기술통계·대응 비교·비용. 미실행을 오답으로 위장하거나 성공 seed를 선별하지 않는다."""
from __future__ import annotations
import csv
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from .plan import ARMS, input_key

METRICS = ("elapsed_ns", "prompt_eval_count", "prompt_eval_cached_count", "eval_count",
           "total_duration", "load_duration", "prompt_eval_duration", "eval_duration")


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        if rows:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
        else:
            stream.write("no_recorded_rows\n")


def _distribution(values: list[int | float | None]) -> dict:
    valid = [x for x in values if x is not None]
    return {"assigned": len(values), "observed": len(valid),
            "mean": statistics.mean(valid) if valid else None,
            "median": statistics.median(valid) if valid else None,
            "min": min(valid) if valid else None, "max": max(valid) if valid else None,
            "scope": "측정값이 존재하는 항목의 기술통계; 누락 개수를 별도 보고"}


def _counts(rows: list[dict], complete: bool) -> dict:
    positives = [r for r in rows if r["expected"]]
    negatives = [r for r in rows if not r["expected"]]
    success = sum(r["final_correct"] is True for r in rows)
    pos = sum(r["final_correct"] is True for r in positives)
    neg = sum(r["final_correct"] is True for r in negatives)
    is_pipeline = rows[0]["arm"] == "pipeline"
    return {
        "assigned": len(rows), "observed_decisions": sum(r["observed"] for r in rows),
        "unrecorded_decisions": sum(not r["observed"] for r in rows),
        "valid_final_values": sum(type(r["value"]) is bool for r in rows),
        "final_correct": success, "final_accuracy": success / len(rows) if complete else None,
        "positive_correct": pos, "positive_assigned": len(positives),
        "negative_correct": neg, "negative_assigned": len(negatives),
        "balanced_accuracy": (pos / len(positives) + neg / len(negatives)) / 2 if complete else None,
        "strict_trace_correct": sum(r["trace_correct"] is True for r in rows) if is_pipeline else None,
        "not_correct": sum(r["not_correct"] is True for r in rows) if is_pipeline else None,
        "and_local_correct": sum(r["and_local_correct"] is True for r in rows) if is_pipeline else None,
        "true_outputs": sum(r["value"] is True for r in rows),
        "false_outputs": sum(r["value"] is False for r in rows),
        "always_false": all(r["value"] is False for r in rows) if complete else None,
    }


def _costs(rows: list[dict], calls: list[dict]) -> dict:
    result = {}
    for key in METRICS:
        values = [c[key] for c in calls]
        known = [v for v in values if v is not None]
        result[key] = {"total": sum(known) if calls and len(known) == len(calls) else None,
            "known_sum": sum(known), "observed_calls": len(known), "actual_calls": len(calls)}
    by_block = defaultdict(list)
    for call in calls:
        by_block[call["block_id"]].append(call)
    expected_calls = 2 if rows[0]["arm"] == "pipeline" else 1
    decision_times = []
    complete_path_times = []
    load_adjusted = []
    cache_inconsistent = 0
    for call in calls:
        cached, prompt = call["prompt_eval_cached_count"], call["prompt_eval_count"]
        if cached is not None and prompt is not None and cached > prompt:
            cache_inconsistent += 1
    for row in rows:
        observed = by_block[row["block_id"]]
        decision_times.append(sum(c["elapsed_ns"] for c in observed) if observed else None)
        full = len(observed) == expected_calls
        complete_path_times.append(sum(c["elapsed_ns"] for c in observed) if full else None)
        coherent = full and all(c["total_duration"] is not None and c["load_duration"] is not None and
                                 c["total_duration"] >= c["load_duration"] for c in observed)
        load_adjusted.append(sum(c["total_duration"] - c["load_duration"] for c in observed) if coherent else None)
    result["decision_http_sum_ns"] = _distribution(decision_times)
    result["complete_path_http_sum_ns"] = _distribution(complete_path_times)
    result["complete_path_server_total_minus_load_ns"] = _distribution(load_adjusted)
    result["load_duration_per_call_ns"] = _distribution([c["load_duration"] for c in calls])
    result["cache_count_inconsistent_calls"] = cache_inconsistent
    result["cache_counts_per_call"] = _distribution([c["prompt_eval_cached_count"] for c in calls])
    result["note"] = ("모든 실제 호출의 비용 포함. complete_path는 예정된 호출 수가 기록된 경로이며 정답 여부로 선별하지 않음. "
        "decision_http_sum은 요청들의 합으로 호스트 파일 기록시간 전체가 아니다. 로딩 차감값은 서버 응답 두 필드의 산술 차이이며 FLOPs가 아니다.")
    return result


def summarize(plan: dict, trials: list[dict], resources: list[dict], decoded: dict, complete: bool) -> dict:
    arm_reports = {}
    per_seed = []
    tables = {}
    by_seed_arm = {}
    for arm in ARMS:
        rows = [r for r in trials if r["arm"] == arm]
        metrics = _counts(rows, complete)
        arm_tables = []
        for seed in plan["seeds"]:
            seed_rows = [r for r in rows if r["seed"] == seed]
            seed_complete = len(seed_rows) == 4 * plan["cycles"] and all(r["observed"] for r in seed_rows)
            c = _counts(seed_rows, complete and seed_complete)
            per_seed.append({"seed": seed, "arm": arm, **c})
            by_seed_arm[seed, arm] = c
            for cycle in range(plan["cycles"]):
                cells = [r for r in seed_rows if r["cycle"] == cycle]
                observed = len(cells) == 4 and all(r["observed"] for r in cells)
                arm_tables.append({"seed": seed, "cycle": cycle, "observed": observed,
                    "final_four_of_four": all(r["final_correct"] is True for r in cells) if observed else None,
                    "trace_four_of_four": all(r["trace_correct"] is True for r in cells) if observed and arm == "pipeline" else None})
        metrics.update({"tables": arm_tables,
            "four_of_four_repeats": sum(t["final_four_of_four"] is True for t in arm_tables),
            "trace_four_of_four_repeats": sum(t["trace_four_of_four"] is True for t in arm_tables) if arm == "pipeline" else None,
            "per_input": {key: {"correct": sum(r["final_correct"] is True for r in rows if input_key(r["a"], r["b"]) == key),
                "assigned": sum(input_key(r["a"], r["b"]) == key for r in rows),
                "observed": sum(r["observed"] for r in rows if input_key(r["a"], r["b"]) == key)}
                for key in ("00", "01", "10", "11")},
            "status_counts": dict(Counter(r["status"] for r in rows)),
            "costs": _costs(rows, [c for c in resources if c["arm"] == arm])})
        arm_reports[arm] = metrics
    paired = {}
    trial_map = {(r["block_id"], r["arm"]): r for r in trials}
    for reference, contender in (("original", "commuted"), ("original", "pipeline"), ("commuted", "pipeline")):
        counts = Counter(both_correct=0, reference_only=0, contender_only=0, neither_correct=0, unobserved_pairs=0)
        deltas = []
        for block in plan["blocks"]:
            left, right = trial_map[block["id"], reference], trial_map[block["id"], contender]
            if not left["observed"] or not right["observed"]:
                counts["unobserved_pairs"] += 1
                continue
            good_l, good_r = left["final_correct"] is True, right["final_correct"] is True
            key = "both_correct" if good_l and good_r else "reference_only" if good_l else "contender_only" if good_r else "neither_correct"
            counts[key] += 1
        for seed in plan["seeds"]:
            left, right = by_seed_arm[seed, reference], by_seed_arm[seed, contender]
            deltas.append({"seed": seed, "assigned_per_arm": left["assigned"],
                "final_accuracy_delta": (right["final_correct"] - left["final_correct"]) / left["assigned"] if complete else None,
                "positive_accuracy_delta": (right["positive_correct"] - left["positive_correct"]) / left["positive_assigned"] if complete else None})
        valid_deltas = [r["final_accuracy_delta"] for r in deltas if r["final_accuracy_delta"] is not None]
        paired[contender + "-" + reference] = {"reference_arm": reference, "contender_arm": contender, **dict(counts),
            "per_seed": deltas, "final_accuracy_delta": statistics.mean(valid_deltas) if complete else None,
            "seed_wins": sum(x > 0 for x in valid_deltas) if complete else None,
            "seed_ties": sum(x == 0 for x in valid_deltas) if complete else None,
            "seed_losses": sum(x < 0 for x in valid_deltas) if complete else None,
            "inferential_p_value": None, "confidence_interval": None,
            "note": "각 seed 내 6회는 순서/재현 반복. 새 문제 표본이 아니며 이 표의 delta는 등록한 seed 집합의 기술통계다."}
    patterns = []
    for seed in plan["seeds"]:
        o, c, p = (by_seed_arm[seed, arm] for arm in ARMS)
        patterns.append({"seed": seed,
            "matches_v047_behavior": (o["always_false"] and c["final_correct"] == c["assigned"] and
                                       p["strict_trace_correct"] == p["assigned"]) if complete else None,
            "all_three_final_perfect": all(x["final_correct"] == x["assigned"] for x in (o, c, p)) if complete else None,
            "pipeline_exceeds_commuted": p["final_correct"] > c["final_correct"] if complete else None})
    grouped = defaultdict(list)
    for call in resources:
        grouped[call["request_sha256"]].append(call)
    repeats = []
    for request_hash, calls in grouped.items():
        first = calls[0]
        signature = {(c["status"], c["value"]) for c in calls}
        hashes = {c["response_content_sha256"] for c in calls if c["response_content_sha256"] is not None}
        repeats.append({"request_sha256": request_hash, "seed": first["seed"], "stage": first["stage"],
            "recorded_calls": len(calls), "unique_content_strings": len(hashes),
            "missing_content_strings": sum(c["response_content_sha256"] is None for c in calls),
            "unique_semantic_status_values": len(signature),
            "identical_valid_boolean": len(calls) >= 2 and len(signature) == 1 and type(first["value"]) is bool,
            "semantic_repeat_instability": len(calls) >= 2 and len(signature) > 1})
    options = plan["baseline"]["config"]["options"]
    return {"contract": "seed-report-v048-r1", "arms": arm_reports, "per_seed": per_seed,
        "paired_final_outcomes": paired, "behavior_patterns": patterns,
        "matching_v047_seeds": sum(p["matches_v047_behavior"] is True for p in patterns) if complete else None,
        "request_repeats": repeats,
        "repeated_request_groups": sum(r["recorded_calls"] >= 2 for r in repeats),
        "unstable_request_groups": sum(r["semantic_repeat_instability"] for r in repeats),
        "call_status_counts": dict(Counter(d["status"] for d in decoded.values())),
        "seeds": plan["seeds"], "seed_count": len(plan["seeds"]), "cycles": plan["cycles"],
        "temperature": options.get("temperature"), "model": plan["baseline"]["config"]["model"],
        "discovery_seeds_excluded": plan["reference"]["discovery_seeds"],
        "reference_only_scores": plan["reference"]["reference_only_scores"],
        "seed_interpretation": "새 seed는 생성 조건의 확장이지 새 논리 문제의 표본이 아니다. 동일 seed의 여섯 순서는 독립 문제로 세지 않는다.",
        "scope": plan["analysis_policy"]["scope"],
        "fairness": "직접 경로는 최종값끼리 비교. 파이프라인의 중간값 포함 성공은 별도. 발견 v047 점수는 새 결과에 합산하지 않음."}


def _shown(value):
    return "측정 없음" if value is None else str(value)


def _ms(value):
    return "측정 없음" if value is None else f"{value / 1_000_000:.3f}"


def write_markdown(path: Path, report: dict) -> None:
    lines = ["# v048 다중-seed 대조 결과", "",
        f'- 출처: **{report["evidence_kind"]}** / 실제 새 모델 추론 표기: **{report["new_model_inference"]}**',
        f'- 자료 무결성: **{report["data_integrity"]}** / 수집 완료: **{report["data_complete"]}** / 비교 가능: **{report["comparative_analysis_ready"]}**',
        f'- 실제 기록된 요청: **{report["inference_calls"]}/{report["max_inference_calls"]}**; blocked는 호출 수에 넣지 않음',
        f'- 모델: `{report["model"]}` / temperature: `{report["temperature"]}` / 각 seed 반복: `{report["cycles"]}`',
        f'- 새 seed: `{report["seeds"]}`',
        f'- 발견 seed 제외: `{report["discovery_seeds_excluded"]}` / 기준선 고정 방식: `{report["reference_anchor"]}`',
        "", "자료의 유효성과 모델의 정답률은 서로 다른 판정이다.", "",
        "| 조건 | 최종값 정답/배정 | 관측한 판단 | 양성 정답/배정 | 진리표 4/4 반복 | 중간값 포함 |",
        "|---|---:|---:|---:|---:|---:|"]
    for arm in ARMS:
        r = report["arms"][arm]
        trace = "측정 대상 아님" if r["strict_trace_correct"] is None else f'{r["strict_trace_correct"]}/{r["assigned"]}'
        lines.append(f'| {arm} | {r["final_correct"]}/{r["assigned"]} | {r["observed_decisions"]} | '
                     f'{r["positive_correct"]}/{r["positive_assigned"]} | {r["four_of_four_repeats"]}/{len(r["tables"])} | {trace} |')
    lines += ["", "## Seed별 결과", "", "| seed | original | commuted | pipeline 최종 | pipeline 전체 경로 | v047 행동 재현 |",
              "|---:|---:|---:|---:|---:|---|"]
    rows = {(r["seed"], r["arm"]): r for r in report["per_seed"]}
    patterns = {r["seed"]: r for r in report["behavior_patterns"]}
    for seed in report["seeds"]:
        o, c, p = (rows[seed, arm] for arm in ARMS)
        line = f'| {seed} | ' + " | ".join(f'{r["final_correct"]}/{r["assigned"]}' for r in (o, c, p))
        lines.append(line + f' | {p["strict_trace_correct"]}/{p["assigned"]} | {_shown(patterns[seed]["matches_v047_behavior"])} |')
    lines += ["", "v047 행동 재현 = 원식은 유효한 false만 출력하고, 교환식 최종값과 파이프라인 전체 경로는 모두 정확함.",
              "", "## 대응 비교", "", "| 대조 | 기준만 정답 | 대조만 정답 | seed 승/무/패 | 평균 정확도 차이 |", "|---|---:|---:|---|---:|"]
    for name, p in report["paired_final_outcomes"].items():
        lines.append(f'| {name} | {p["reference_only"]} | {p["contender_only"]} | '
                     f'{_shown(p["seed_wins"])}/{_shown(p["seed_ties"])}/{_shown(p["seed_losses"])} | {_shown(p["final_accuracy_delta"])} |')
    lines += ["", "## 실제 자원 사용", "", "| 조건 | 호출 | 입력 토큰 합 | 출력 토큰 합 | 완결 경로 요청시간 중앙값 ms | 평균 ms | 모델 로딩 합 ms |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for arm in ARMS:
        c = report["arms"][arm]["costs"]
        lines.append(f'| {arm} | {c["eval_count"]["actual_calls"]} | {_shown(c["prompt_eval_count"]["total"])} | '
                     f'{_shown(c["eval_count"]["total"])} | {_ms(c["complete_path_http_sum_ns"]["median"])} | '
                     f'{_ms(c["complete_path_http_sum_ns"]["mean"])} | {_ms(c["load_duration"]["total"])} |')
    lines += ["", "실제 호출 비용은 실패 응답을 포함한다. 경로 시간은 파이프라인 두 HTTP 요청을 합산하며, 호스트 작업 전체 시간은 아니다.",
              "누락 토큰/시간은 null로 보존한다. 캐시·로딩·원문은 summary.json/calls.csv에 남긴다. 토큰 수는 모델 간 동일 FLOPs가 아니다.",
              "", "## 재현성과 범위", "", report["seed_interpretation"], "", report["fairness"], "", report["scope"],
              f'동일 요청 반복 그룹: {report["repeated_request_groups"]}; 그중 의미/형식 상태가 달라진 그룹: {report["unstable_request_groups"]}.',
              "p-value와 문제 일반화 신뢰구간은 계산하지 않는다. 원인/우월성을 자동 확정하거나 특정 seed만 선택하지 않는다.",
              "", f'계획 SHA-256: `{report["plan_sha256"]}`', f'마지막 event 해시: `{report["event_tip"]}`',
              "해시는 외부 동결 계획과 보존 원문의 일관성을 확인한다. 모든 자료와 해시를 함께 바꾸는 공격 또는 외부 서버 실행 자체를 증명하는 서명은 아니다."]
    if report["temperature"] == 0:
        lines += ["", "기준선 temperature=0을 보존했다. seed 변경이 출력 다양성을 보장하지 않는다."]
    if not report["data_complete"]:
        lines = lines[:2] + ["**미완료 실행. 미실행은 모델 오답이 아니다. 완결 성공률·대응 효과는 산출하지 않았다.**", ""] + lines[2:]
        lines += ["", "중단 사유: " + str(report["run_error"]), "식별 오류: " + str(report["identity_errors"])]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
