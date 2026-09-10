"""배정한 모든 조건을 분모에 남기는 결과 집계. 관측하지 않은 값은 0으로 채우지 않는다."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .common import bytes_hash, digest, read_json, require, write_json


def read_records(out: Path, manifest: dict) -> list[dict]:
    frozen = manifest["frozen"]
    require(manifest["run_sha256"] == digest(frozen), "manifest 해시 불일치")
    records = []
    for case in frozen["plan"]["cases"]:
        folder = out / "cases" / case["case_id"]
        path = folder / "record.json"
        if not path.is_file():
            continue
        record = read_json(path)
        require(record["case"] == case and record["run_sha256"] == manifest["run_sha256"],
                f"결과의 실험/문제/조건 결합 불일치: {case['case_id']}")
        for name, expected in record.get("artifacts_sha256", {}).items():
            require(name in {"request.json", "request.wire.json", "response.raw.json", "trace.json", "timing.json", "gpu.json"},
                    "허용하지 않은 산출물 경로")
            artifact = folder / name
            require(artifact.is_file() and bytes_hash(artifact.read_bytes()) == expected,
                    f"산출물이 변경되었거나 누락됨: {artifact}")
        if frozen.get("config", {}).get("protocol") == "adm-json-v2":
            declared = record.get("artifacts_sha256", {})
            for name in ("request.json", "request.wire.json", "response.raw.json", "trace.json", "timing.json", "gpu.json"):
                require(not (folder / name).is_file() or name in declared,
                        f"존재하는 산출물의 해시 선언 누락: {name}")
            if record.get("status") in {"accepted", "role_mismatch", "invalid_trace", "invalid_task", "protocol_error", "truncated"}:
                require({"request.json", "request.wire.json", "response.raw.json"} <= set(declared),
                        "응답 완료 record의 필수 원문 산출물이 누락됨")
        records.append(record)
    return records


def make_contrasts(plan: dict, records: list[dict]) -> list[dict]:
    index = {(c["problem_id"], c["repeat"], c["role"]["A"], c["role"]["D_policy"], c["role"]["M"]): c
             for c in plan["cases"] if c["role"]["kind"] == "directed"}
    observed = {r["case"]["case_id"]: r for r in records}
    contrasts = []
    for key, left in index.items():
        pid, repeat, a, d, m = key
        candidates = []
        if a == "instance":
            candidates.append(("A", (pid, repeat, "schema", d, m)))
        if d == "shallow":
            candidates.append(("D", (pid, repeat, a, "deep", m)))
        if m < 2:
            candidates.append(("M", (pid, repeat, a, d, m + 1)))
        for axis, right_key in candidates:
            if right_key not in index:
                continue
            right = index[right_key]
            x = observed.get(left["case_id"])
            y = observed.get(right["case_id"])
            detail = {"axis": axis, "problem_id": pid, "repeat": repeat,
                      "left": left["case_id"], "right": right["case_id"],
                      "pass": False, "status": "not_completed", "support_graph_equal": None}
            if x is not None and y is not None:
                ax, ay = x.get("audit") or {}, y.get("audit") or {}
                if not (ax.get("valid_completion") and ay.get("valid_completion")
                        and ax.get("role_adherent") and ay.get("role_adherent")
                        and x["status"] == "accepted" and y["status"] == "accepted"):
                    detail["status"] = "invalid_or_role_mismatch"
                else:
                    u, v = ax["observed"], ay["observed"]
                    if axis == "A":
                        passed = (u["A"] == "instance" and v["A"] == "schema"
                                  and u["D"] == v["D"] and u["M_target"] == v["M_target"])
                    elif axis == "D":
                        passed = (u["D"] < v["D"] and u["A"] == v["A"]
                                  and u["M_target"] == v["M_target"])
                    else:
                        passed = (u["M_target"] + 1 == v["M_target"]
                                  and u["A"] == v["A"] and u["D"] == v["D"])
                    detail["pass"] = bool(passed)
                    detail["status"] = "passed" if passed else "coordinate_contrast_failed"
                    detail["support_graph_equal"] = ax["support_graph_sha256"] == ay["support_graph_sha256"]
            contrasts.append(detail)
    return contrasts


def _rate(count: int, denominator: int) -> float | None:
    return count / denominator if denominator else None


def build_summary(plan: dict, records: list[dict]) -> tuple[dict, list[dict], list[dict]]:
    lookup = {r["case"]["case_id"]: r for r in records}
    is_calibration = plan.get("experiment_kind") == "calibration"
    rows = []
    groups: dict[str, dict] = {}
    for case in plan["cases"]:
        record = lookup.get(case["case_id"])
        audit = (record.get("audit") or {}) if record else {}
        usage = (record.get("usage") or {}) if record else {}
        raw = (record.get("raw_diagnostics") or {}) if record else {}
        usable = record is not None and record["status"] in {"accepted", "role_mismatch", "invalid_trace"}
        row = {"case_id": case["case_id"], "problem_id": case["problem_id"],
               "role": case["role_id"], "repeat": case["repeat"], "seed": case["seed"],
               "status": record["status"] if record else "not_started",
               "fixed_goal_match": audit.get("fixed_goal_match"),
               "proof_valid": audit.get("proof_valid"),
               "representation_assessable": audit.get("representation_assessable"),
               "review_assessable": audit.get("review_assessable"),
               "representation_valid": audit.get("representation_valid"),
               "review_valid": audit.get("review_valid"),
               "valid_completion": bool(usable and audit.get("valid_completion")),
               "role_adherent": audit.get("role_adherent") if usable else None,
               "A_observed": audit.get("observed", {}).get("A"),
               "D_observed": audit.get("observed", {}).get("D"),
               "M_target_observed": audit.get("observed", {}).get("M_target"),
               "D_target": audit.get("D_target"),
               "raw_json_valid": raw.get("json_valid"),
               "wire_schema_valid": raw.get("schema_valid"),
               "final_reference_exists": raw.get("final_reference_exists"),
               "all_local_steps_valid": raw.get("all_local_steps_valid"),
               "missing_parent_reference": bool(raw.get("missing_parent_node_ids")) if raw else None,
               "empty_binding": bool(raw.get("empty_binding_node_ids")) if raw else None,
               "wall_seconds": record.get("wall_seconds") if record else None,
               "prompt_tokens": usage.get("prompt_eval_count"),
               "cached_prompt_tokens": usage.get("prompt_eval_cached_count"),
               "output_tokens": usage.get("eval_count"),
               "load_seconds": usage.get("load_seconds"),
               "prompt_eval_seconds": usage.get("prompt_eval_seconds"),
               "generation_seconds": usage.get("generation_seconds"),
               "tokens_per_second": usage.get("tokens_per_second"),
               "size_vram_bytes": record.get("gpu", {}).get("size_vram") if record else None,
               "error": record.get("error") if record else None}
        rows.append(row)
        group = groups.setdefault(case["role_id"], {"assigned": 0, "recorded": 0,
                                                  "valid": 0, "adherent": 0})
        group["assigned"] += 1
        group["recorded"] += int(record is not None)
        group["valid"] += int(row["valid_completion"])
        group["adherent"] += int(row["role_adherent"] is True)
    for name, group in groups.items():
        group["valid_rate_all_assigned"] = _rate(group["valid"], group["assigned"])
        group["adherence_rate_all_assigned"] = (
            None if name == "neutral" else _rate(group["adherent"], group["assigned"]))
    contrasts = [] if is_calibration else make_contrasts(plan, records)
    controls = [c for r in records for c in (r.get("audit") or {}).get("negative_controls", [])]
    applied = [c for c in controls if c["applicable"]]
    cost = {}
    for metric in ("prompt_eval_count", "prompt_eval_cached_count", "eval_count"):
        known = [(r.get("usage") or {}).get(metric) for r in records]
        cost[f"known_{metric}_sum"] = sum(x for x in known if x is not None)
        cost[f"unknown_{metric}_cases"] = sum(
            1 for r, value in zip(records, known) if value is None and r.get("api_attempted") is not False)
    cost["known_api_wall_seconds_sum"] = sum(r["wall_seconds"] for r in records
                                            if r.get("wall_seconds") is not None)
    cost["note"] = "실패 호출도 포함. 미수신 비용은 null/unknown이며 0으로 추정하지 않음. 비용 절감 결론이 아님."
    assigned = len(plan["cases"])
    directed = [] if is_calibration else [row for row in rows if row["role"] != "neutral"]
    valid_count = sum(row["valid_completion"] for row in rows)
    adherence_count = sum(row["role_adherent"] is True for row in directed)
    complete = len(records) == assigned
    passed = (complete and valid_count == assigned and adherence_count == len(directed)
              and all(c["pass"] for c in contrasts) and bool(applied)
              and all(c["rejected"] for c in applied))
    if is_calibration:
        passed = complete and valid_count == assigned and all(r["status"] == "accepted" for r in records)
    summary = {"experiment_kind": "calibration" if is_calibration else "joint",
               "scope": plan["scope"], "assigned_cases": assigned,
               "recorded_cases": len(records), "not_recorded_cases": assigned - len(records),
               "complete": complete, "valid_completions": valid_count,
               "valid_rate_all_assigned": _rate(valid_count, assigned),
               "directed_cases": len(directed), "role_adherent_cases": adherence_count,
               "adherence_rate_all_assigned_directed": _rate(adherence_count, len(directed)),
               "planned_contrasts": len(contrasts),
               "passed_contrasts": sum(c["pass"] for c in contrasts),
               "negative_control_instances": len(applied),
               "negative_controls_rejected": sum(c["rejected"] for c in applied),
               "negative_controls_not_applicable": len(controls) - len(applied),
               "negative_control_note": "반복 변조 검사 수이며 독립 LLM 표본 수가 아님",
               "all_assigned_passed": passed, "status_counts": dict(Counter(row["status"] for row in rows)),
               "by_role": groups, "cost": cost, "plan_warnings": plan["warnings"],
               "interpretation": "고정 목표의 형식 기록에서 지시한 A/D/M 조작을 따르는지 관측. "
                                 "내부 사고 좌표, 차원 독립성의 일반 증명, H7b 라우터 검증이 아님."}
    summary["raw_diagnostic_counts"] = {
        "final_reference_missing": sum(row["final_reference_exists"] is False for row in rows),
        "all_local_steps_valid": sum(row["all_local_steps_valid"] is True for row in rows),
        "missing_parent_reference": sum(row["missing_parent_reference"] is True for row in rows),
        "empty_binding": sum(row["empty_binding"] is True for row in rows),
        "representation_assessable": sum(row["representation_assessable"] is True for row in rows),
        "review_assessable": sum(row["review_assessable"] is True for row in rows),
    }
    if is_calibration:
        summary["interpretation"] = "분리 교정 8과제의 수행 여부. 통합 A/D/M 실험 결과에 합산하지 않음."
    return summary, rows, contrasts


def write_report(out: Path) -> dict:
    manifest = read_json(out / "manifest.json")
    records = read_records(out, manifest)
    summary, rows, contrasts = build_summary(manifest["frozen"]["plan"], records)
    write_json(out / "summary.json", summary)
    write_json(out / "contrasts.json", contrasts)
    with (out / "metrics.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        # 텍스트 셀의 스프레드시트 수식 실행 방지. JSON에는 원문이 남는다.
        for row in rows:
            safe = {k: ("'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v)
                    for k, v in row.items()}
            writer.writerow(safe)
    is_calibration = summary["experiment_kind"] == "calibration"
    title = "# 로컬 LLM 분리 교정 결과" if is_calibration else "# 로컬 LLM 고정 목표 A/D/M 실험 결과"
    lines = [title, "",
             f"실험 식별 해시: `{manifest['run_sha256']}`", "",
             f"배정 {summary['assigned_cases']}건 / 기록 {summary['recorded_cases']}건 / "
             f"미기록 {summary['not_recorded_cases']}건",
             f"유효한 고정 목표 증명 기록: {summary['valid_completions']} / {summary['assigned_cases']}",
             f"지정 역할 준수: {summary['role_adherent_cases']} / {summary['directed_cases']}",
             f"축별 대조: {summary['passed_contrasts']} / {summary['planned_contrasts']}", "",
             "실패·중단·미실행 조건을 분모에서 제외하지 않았다. 중립 조건은 역할 준수율에서만 제외한다.", "",
             "| 역할 | 배정 | 기록 | 유효 | 역할 준수 |", "| --- | ---: | ---: | ---: | ---: |"]
    for name, group in summary["by_role"].items():
        adherence = "해당 없음" if name == "neutral" else str(group["adherent"])
        lines.append(f"| {name} | {group['assigned']} | {group['recorded']} | {group['valid']} | {adherence} |")
    if is_calibration:
        lines = [title, "", f"실험 식별 해시: `{manifest['run_sha256']}`", "",
                 f"배정 {summary['assigned_cases']}건 / 기록 {summary['recorded_cases']}건 / "
                 f"교정 과제 성공 {summary['valid_completions']}건", "",
                 "| 교정 과제 | 상태 |", "| --- | --- |"]
        lines += [f"| {row['role']} | {row['status']} |" for row in rows]
    lines += ["", "## 실패 구분", "",
              "`metrics.csv`의 proof_valid / representation_valid / review_valid를 함께 본다. "
              "증명 자체가 무효라 표현/검토를 검사할 수 없으면 해당 값은 null이다. "
              "각 층위 진단은 원문을 고쳐서 통과시킨 결과가 아니다. 최종 유효성은 원본 전체 검사로 결정한다.",
              "", "```json", json.dumps(summary["raw_diagnostic_counts"], ensure_ascii=False, indent=2), "```",
              "", "## 비용", "", "```json", json.dumps(summary["cost"], ensure_ascii=False, indent=2),
              "```", "", "## 해석 범위", "", summary["interpretation"], "",
              "반복 시드는 같은 문제의 반복 측정이다. 독립된 문제 수나 새 표본으로 부풀리지 않는다. "
              "토큰 수·시간은 서로 다른 출력 작업량과 캐시·최초 로딩을 포함하므로 곧바로 효율 향상으로 읽지 않는다."]
    if summary["plan_warnings"]:
        lines += ["", "## 문제 구성 경고", ""] + summary["plan_warnings"]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary
