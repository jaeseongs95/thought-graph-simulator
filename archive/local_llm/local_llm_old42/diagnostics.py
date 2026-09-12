"""원문을 수정하지 않는 다중 오류 진단과 저장 응답 재검사. 네트워크 호출 없음."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .common import ContractError, bytes_hash, read_json, require, strict_json, write_json, write_text
from .protocol import TRANSPORT_SCHEMA as LEGACY_SCHEMA, validate_schema
from .protocol_v2 import TRANSPORT_SCHEMA as V2_SCHEMA


def raw_diagnostics(problem: dict, content: Any, *, v2: bool = False) -> dict:
    """첫 오류 뒤의 문제도 관측한다. 결과를 복구하거나 본 실험 성공으로 승격하지 않는다."""
    output: dict = {"json_valid": False, "schema_valid": False, "schema_error": None,
                    "node_shape_assessable": False, "final_reference_exists": None,
                    "all_local_steps_valid": None, "goal_match": None,
                    "missing_parent_node_ids": [], "invalid_step_node_ids": [],
                    "unrelated_node_ids": None, "empty_binding_node_ids": [],
                    "view_kind_counts": {}, "node_ids": [], "selected_final_reference": None,
                    "all_problem_rules_emitted": None, "selected_component_depth": None,
                    "all_nodes_in_selected_component": None,
                    "note": "원문 무수정 진단. 국소 규칙 일치는 전체 증명 성공이 아님."}
    try:
        value = strict_json(content)
        output["json_valid"] = True
        output["output_key_order"] = list(value) if isinstance(value, dict) else None
        try:
            validate_schema(value, V2_SCHEMA if v2 else LEGACY_SCHEMA)
            output["schema_valid"] = True
        except ContractError as exc:
            output["schema_error"] = str(exc)
        if not isinstance(value, dict) or not isinstance(value.get("nodes"), list):
            return output
        from .evidence import support
        evidence = support(problem, value, core_format=not v2)
        output["support_evidence"] = evidence
        output["selected_component_support_valid"] = evidence.get("selected_support_valid")
        output["selected_component_depth_if_grounded"] = evidence.get("selected_depth_when_valid")
        output["first_invalid_step"] = evidence.get("first_failure")
        output["unrelated_node_ids_independent"] = evidence.get("unrelated_node_ids")
        nodes = value["nodes"]
        id_key, parent_key, rule_key, final_key = (
            ("node_id", "parent_node_ids", "rule_id", "selected_final_node_id") if v2
            else ("id", "parents", "rule", "final"))
        lookup: dict = {}
        rules = {r["id"]: r for r in problem["rules"]}
        kinds: Counter = Counter()
        malformed = False
        for node in nodes:
            if not isinstance(node, dict):
                malformed = True
                continue
            view = node.get("view")
            if isinstance(view, dict):
                kind = view.get("kind")
                if isinstance(kind, str):
                    kinds[kind] += 1
                binding = view.get("bindings" if v2 else "binding")
                if kind == "universal_schema" and (binding == [] or binding == {}):
                    output["empty_binding_node_ids"].append(node.get(id_key))
            key, atom = node.get(id_key), node.get("atom")
            parents, rule_id = node.get(parent_key), node.get(rule_key)
            if not (isinstance(key, str) and key and isinstance(atom, str)
                    and isinstance(parents, list) and all(isinstance(x, str) for x in parents)
                    and (rule_id is None or isinstance(rule_id, str))
                    and rule_key in node):
                malformed = True
                continue
            good = bool(key not in lookup and len(parents) == len(set(parents)))
            if any(x not in lookup for x in parents):
                output["missing_parent_node_ids"].append(key)
                good = False
            elif rule_id is None:
                good = good and not parents and atom in problem["facts"]
            else:
                rule = rules.get(rule_id)
                good = bool(good and rule is not None and atom == rule["conclusion"]
                            and sorted(lookup[x]["atom"] for x in parents) == sorted(rule["premises"]))
            if not good:
                output["invalid_step_node_ids"].append(key)
            # 중복은 진단용 lookup에 덮어쓰지 않으며 위에서 실패로 기록한다.
            lookup.setdefault(key, {"atom": atom, "parents": parents, "rule": rule_id})
        output["view_kind_counts"] = dict(kinds)
        output["node_ids"] = list(lookup)
        output["node_shape_assessable"] = bool(nodes) and not malformed
        final = value.get(final_key)
        output["selected_final_reference"] = final
        if output["node_shape_assessable"]:
            output["final_reference_exists"] = isinstance(final, str) and final in lookup
            output["all_local_steps_valid"] = not output["invalid_step_node_ids"]
            output["all_problem_rules_emitted"] = {n["rule"] for n in lookup.values()
                                                    if n["rule"] is not None} == set(rules)
            if output["final_reference_exists"]:
                output["goal_match"] = lookup[final]["atom"] == problem["goal"]
                if output["all_local_steps_valid"]:
                    seen: set[str] = set()
                    pending = [final]
                    while pending:
                        key = pending.pop()
                        if key not in seen:
                            seen.add(key)
                            pending.extend(lookup[key]["parents"])
                    output["unrelated_node_ids"] = [key for key in lookup if key not in seen]
                    depths = {}
                    for key, node in lookup.items():
                        depths[key] = (0 if node["rule"] is None else
                                       1 + max(depths[parent] for parent in node["parents"]))
                    output["selected_component_depth"] = depths[final]
                    output["all_nodes_in_selected_component"] = len(seen) == len(lookup)
                    output["selected_component_note"] = (
                        "원문 노드를 삭제/수정하지 않은 선택 연결부의 관측. 전체 증명의 유효성 판정을 대체하지 않음")
    except (ContractError, TypeError, ValueError, RecursionError) as exc:
        output["parse_error"] = str(exc)
    return output


def reanalyze(core: Any, source: Path, out: Path) -> dict:
    """검증기는 설치된 기준 소스를 쓴다. 첨부 source_snapshot을 동적으로 실행하지 않는다."""
    from .report import read_records
    from .runner import assess_response
    source, out = source.resolve(), out.resolve()
    require(out != source and not out.is_relative_to(source), "원본 결과 밖의 새 분석 경로를 사용하세요.")
    require(not out.exists() or not any(out.iterdir()), "분석 출력 폴더가 비어 있지 않습니다.")
    manifest = read_json(source / "manifest.json")
    frozen = manifest["frozen"]
    records = read_records(source, manifest)
    source_checks = {}
    for name, expected in frozen.get("runtime_sources_sha256", {}).items():
        require(Path(name).name == name, "소스 스냅샷 경로 오류")
        file = source / "source_snapshot" / name
        source_checks[name] = file.is_file() and bytes_hash(file.read_bytes()) == expected
    require(all(source_checks.values()), "저장된 소스 스냅샷이 manifest와 일치하지 않습니다.")
    snapshot = source / "source_snapshot" / "adm_minimal.py"
    require(snapshot.is_file() and bytes_hash(snapshot.read_bytes()) == frozen["core"]["sha256"],
            "기존 검증기 스냅샷 해시 불일치")
    require(bytes_hash(Path(core.__file__).read_bytes()) == frozen["core"]["sha256"],
            "현재 검증기와 실행 당시 검증기 바이트가 다릅니다. 같은 기준 검증기로 분석하세요.")
    problems = {p["id"]: p for p in frozen["plan"]["problems"]}
    rows = []
    counts: Counter = Counter()
    for record in records:
        case = record["case"]
        folder = source / "cases" / case["case_id"]
        if not (folder / "response.raw.json").is_file():
            counts["no_saved_response"] += 1
            continue
        request = read_json(folder / "request.json")
        response = read_json(folder / "response.raw.json")
        problem = problems[case["problem_id"]]
        outcome, _ = assess_response(core, problem, case,
            frozen["plan"]["reference_depths"][problem["id"]], request["body"], response, frozen["config"].get("mode_policy"))
        diagnostic = outcome.get("raw_diagnostics") or raw_diagnostics(problem,
            response.get("message", {}).get("content"),
            v2=isinstance(request["body"].get("format"), dict)
               and "selected_final_node_id" in request["body"]["format"].get("properties", {}))
        if case.get("task"):
            if case.get("probe_contract") == "micro-v042":
                from .micro_probe import output_schema
            else:
                from .calibration import output_schema
            diagnostic["schema_scope"] = "task_specific_calibration_schema"
            try:
                payload = strict_json(response.get("message", {}).get("content"))
                validate_schema(payload, output_schema(case))
                diagnostic.update(schema_valid=True, schema_error=None)
            except ContractError as exc:
                diagnostic.update(schema_valid=False, schema_error=str(exc))
        old_audit, new_audit = record.get("audit") or {}, outcome.get("audit") or {}
        matches = (outcome["status"] == record["status"]
                   and old_audit.get("valid_completion") == new_audit.get("valid_completion")
                   and old_audit.get("role_adherent") == new_audit.get("role_adherent")
                   and old_audit.get("task_checks") == new_audit.get("task_checks"))
        row = {"case": case, "original_status": record["status"],
               "replayed_status": outcome["status"], "replayed_error": outcome.get("error"),
               "original_decision_reproduced": matches,
               "original_error_text_reproduced": outcome.get("error") == record.get("error"),
               "diagnostics": diagnostic, "task_diagnostics": outcome.get("task_diagnostics"),
               "diagnostic_scope": ("proof_generation" if case.get("task") == "proof" else "non_proof_task" if case.get("task") else "integrated_trace"),
               "audit": outcome.get("audit"), "usage": outcome.get("usage"),
               "wall_seconds": record.get("wall_seconds")}
        rows.append(row)
        counts["proof_structure_applicable_cases"] += int(not case.get("task") or case.get("task") == "proof")
        counts["saved_responses"] += 1
        counts["original_decision_reproduced"] += int(matches)
        counts["status_" + outcome["status"]] += 1
        counts["normal_stop"] += int(response.get("done_reason") == "stop")
        for key in ("json_valid", "schema_valid", "all_local_steps_valid", "all_problem_rules_emitted"):
            counts[key] += int(diagnostic.get(key) is True)
        counts["missing_final_reference"] += int(diagnostic.get("final_reference_exists") is False)
        counts["missing_parent_reference"] += int(bool(diagnostic.get("missing_parent_node_ids")))
        counts["empty_binding"] += int(bool(diagnostic.get("empty_binding_node_ids")))
        counts["final_is_goal_atom"] += int(diagnostic.get("selected_final_reference") == problem["goal"])
        if not case.get("task"):
            counts["integrated_proof_cases_assessed"] += 1
            counts["selected_final_node_atom_matches_goal"] += int(diagnostic.get("goal_match") is True)
        counts["valid_completion"] += int(bool((outcome.get("audit") or {}).get("valid_completion")))
    result = {"analysis_version": "0.4.2", "source_run_sha256": manifest["run_sha256"],
              "source_manifest_sha256": bytes_hash((source / "manifest.json").read_bytes()),
              "source_snapshot_hash_checks": source_checks,
              "source_modified": False, "model_called": False,
              "metric_glossary": {
                  "final_is_goal_atom": "최종 포인터에 노드 ID 대신 목표 원자 문자열을 넣은 건수. 목표 도달 성공 수가 아님.",
                  "selected_final_node_atom_matches_goal": "통합 증명에서 최종 노드가 담은 명제와 실제 목표가 같은 건수.",
                  "all_local_steps_valid": "통합 증명 또는 proof 생성 과제 대상 지표. 분모는 proof_structure_applicable_cases. 다른 분리 과제에는 해당 없음."},
              "assigned_cases": len(frozen["plan"]["cases"]), "counts": dict(counts), "cases": rows,
              "interpretation": "원본 전체 증명 판정은 유지한다. 참조/국소 규칙/표현 형식 오류를 별도 관측한다."}
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "reanalysis.json", result)
    write_json(out / "task_evidence.json", [{"case_id": r["case"]["case_id"],
        "role_id": r["case"]["role_id"], "status": r["replayed_status"],
        "diagnostics": r.get("task_diagnostics")} for r in rows])
    lines = ["# 저장된 로컬 LLM 응답 재분석", "", f"원본 run: `{manifest['run_sha256']}`", "",
             f"배정 {result['assigned_cases']}건 / 저장 응답 재검사 {counts['saved_responses']}건 / "
             f"기존 판정 재현 {counts['original_decision_reproduced']}건", "",
             "| 관측 | 건수 |", "| --- | ---: |"]
    for key, label in (("valid_completion", "원본 과제 전체 요건 충족"),
                       ("missing_final_reference", "최종 노드 참조 없음"),
                       ("missing_parent_reference", "부모 참조 오류"),
                       ("all_local_steps_valid", "개별 사실·규칙 적용은 모두 유효"),
                       ("empty_binding", "빈 도식 바인딩")):
        lines.append(f"| {label} | {counts[key]} |")
    lines += ["", f"증명 구조 지표의 적용 대상은 {counts['proof_structure_applicable_cases']}건이다. 도식 변환·기준 판정 등에는 이 지표를 실패0건으로 적용하지 않는다.",
              "오류 범주는 서로 겹친다. 빈 바인딩을 제거하거나 최종 참조를 수정하지 않았다.",
              "개별 단계가 맞아도 최종 노드 지정·전체 지지 연결성이 틀리면 전체 증명은 실패다.",
              "원본 파일을 변경하지 않았고 LLM을 호출하지 않았다."]
    write_text(out / "reanalysis.md", "\n".join(lines) + "\n")
    return result
