"""고정 목표 A/D/M 역할극의 결정론적 최소 실험계. LLM·네트워크·외부 패키지 없음.

A: 구체 사례 / 보편 명제 도식(논문 A0~A4 번호를 임의로 재정의하지 않음).
D: 실제 지지 DAG에서 재계산한 최장 의존 깊이. M: 검토 대상 0/1/2.
생성 성공과 독립 재검사 성공은 명세의 구성 가능성에 관한 결과이다.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import itertools
import json
import re
import sys
from pathlib import Path
from typing import Any

MAX_NODES = 128
MAX_PLANS = 256
MAX_ATOMS = 10


class Invalid(ValueError):
    """입력 또는 기록이 실험 계약을 위반함."""


def need(condition: bool, message: str) -> None:
    if not condition:
        raise Invalid(message)


def fields(value: Any, keys: str) -> None:
    need(isinstance(value, dict) and set(value) == set(keys.split()),
         "SCHEMA: 필드가 누락되었거나 허용하지 않은 필드가 있습니다.")


def strings(value: Any, allow_empty: bool = False) -> None:
    need(isinstance(value, list) and (allow_empty or bool(value)), "SCHEMA: 문자열 목록 필요")
    need(all(isinstance(x, str) and x for x in value), "SCHEMA: 빈 문자열/비문자열")
    need(len(value) == len(set(value)), "SCHEMA: 중복 값")


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def check_problem(p: dict) -> None:
    fields(p, "id facts rules goal")
    need(isinstance(p["id"], str) and bool(p["id"]), "PROBLEM: id 필요")
    strings(p["facts"])
    need(isinstance(p["rules"], list) and len(p["rules"]) <= 32, "PROBLEM: 규칙 수 초과")
    atoms = set(p["facts"])
    rule_ids = set()
    for r in p["rules"]:
        fields(r, "id premises conclusion")
        strings(r["premises"])
        need(isinstance(r["id"], str) and r["id"] and r["id"] not in rule_ids,
             "PROBLEM: 규칙 id 오류")
        need(isinstance(r["conclusion"], str), "PROBLEM: 결론 형식 오류")
        rule_ids.add(r["id"])
        atoms.update(r["premises"])
        atoms.add(r["conclusion"])
    need(isinstance(p["goal"], str), "PROBLEM: 목표 형식 오류")
    atoms.add(p["goal"])
    need(len(atoms) <= MAX_ATOMS and all(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", a)
                                       for a in atoms), "PROBLEM: 원자명/원자 수 제한 위반")


def load_problems(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    need(isinstance(data, list) and bool(data), "PROBLEM: 문제 목록 필요")
    for p in data:
        check_problem(p)
    need(len({p["id"] for p in data}) == len(data), "PROBLEM: 중복 문제 id")
    return data


# ------------------- 역할극 생성기: 검증기를 호출하지 않음 -------------------
def _plans(p: dict, atom: str, visiting: frozenset[str] = frozenset()) -> list[dict]:
    if atom in visiting:
        return []
    if atom in p["facts"]:
        return [{"atom": atom, "rule": None, "children": [], "depth": 0}]
    plans = []
    for rule in sorted(p["rules"], key=lambda r: r["id"]):
        if rule["conclusion"] != atom:
            continue
        candidates = [_plans(p, a, visiting | {atom}) for a in rule["premises"]]
        for children in itertools.product(*candidates):
            plans.append({"atom": atom, "rule": rule["id"], "children": list(children),
                          "depth": 1 + max(c["depth"] for c in children)})
            need(len(plans) <= MAX_PLANS, "LIMIT: 후보 증명 수 초과")
    return plans


def _generator_ancestors(nodes: list[dict], root: str) -> list[str]:
    lookup = {n["id"]: n for n in nodes}
    seen = set()
    def visit(key: str) -> None:
        if key not in seen:
            seen.add(key)
            for parent in lookup[key]["parents"]:
                visit(parent)
    visit(root)
    return [n["id"] for n in nodes if n["id"] in seen]


def _make_view(p: dict, nodes: list[dict], node: dict, mode: str) -> dict:
    if mode == "instance":
        return {"kind": "instance", "atom": node["atom"]}
    ids = set(_generator_ancestors(nodes, node["id"]))
    used = [n for n in nodes if n["id"] in ids]
    facts = sorted({n["atom"] for n in used if n["rule"] is None})
    rules = [r for r in p["rules"] if r["id"] in {n["rule"] for n in used}]
    atoms = sorted({n["atom"] for n in used})
    reverse = {a: f"X{i}" for i, a in enumerate(atoms)}
    clauses = [{"if": [], "then": reverse[a]} for a in facts]
    clauses += [{"if": sorted(reverse[a] for a in r["premises"]),
                 "then": reverse[r["conclusion"]]} for r in rules]
    clauses = list({canonical(c): c for c in clauses}.values())
    return {"kind": "universal_schema", "quantifier": "forall_boolean_valuations",
            "binding": {v: a for a, v in reverse.items()}, "assumptions": clauses,
            "conclusion": reverse[node["atom"]]}


def simulate(p: dict, a: str = "instance", d: str = "shallow", m: int = 0) -> dict:
    """같은 문제에서 역할을 바꾼다. trace에는 요청 A/D/M 정답 라벨을 저장하지 않는다."""
    check_problem(p)
    need(a in {"instance", "schema"} and d in {"shallow", "deep"}
         and type(m) is int and m in {0, 1, 2}, "ROLE: 지원하지 않는 역할")
    plans = _plans(p, p["goal"])
    need(bool(plans), "UNREACHABLE: 주어진 사실/규칙으로 목표에 도달할 수 없습니다.")
    plans.sort(key=lambda plan: (plan["depth"], canonical(plan)))
    plan = plans[0] if d == "shallow" else plans[-1]
    nodes: list[dict] = []
    emitted: dict[str, str] = {}
    def emit(item: dict) -> str:
        signature = canonical(item)
        if signature in emitted:
            return emitted[signature]
        parents = [emit(c) for c in item["children"]]
        key = f"n{len(nodes)}"
        nodes.append({"id": key, "atom": item["atom"], "rule": item["rule"], "parents": parents})
        emitted[signature] = key
        return key
    final = emit(plan)
    need(len(nodes) <= MAX_NODES, "LIMIT: 증명 노드 수 초과")
    views = {n["id"]: _make_view(p, nodes, n, a) for n in nodes}
    reviews = []
    if m >= 1:
        # 역할 자체도 규칙을 재실행한다. 최종 verify()는 이 판정을 신뢰하지 않는다.
        replayed = {}
        grounded = True
        lookup = {r["id"]: r for r in p["rules"]}
        for node in nodes:
            if node["rule"] is None:
                grounded &= not node["parents"] and node["atom"] in p["facts"]
            else:
                rule = lookup[node["rule"]]
                grounded &= (sorted(replayed[x] for x in node["parents"]) == sorted(rule["premises"])
                             and node["atom"] == rule["conclusion"])
            replayed[node["id"]] = node["atom"]
        reviews.append({"id": "review1", "target_kind": "argument", "target": final,
                        "check": "support_replay", "evidence": [n["id"] for n in nodes],
                        "finding": {"grounded": grounded,
                                    "used_rules": sorted({n["rule"] for n in nodes if n["rule"]}),
                                    "conclusion": nodes[-1]["atom"]}})
    if m >= 2:
        # 정답 문자열만 맞는 무근거 fact를 만들어 평가 기준의 구별 능력을 검사.
        grounded_probe = p["goal"] in p["facts"]
        reviews.append({"id": "review2", "target_kind": "acceptance_criterion",
                        "target": "valid_proof_and_goal", "check": "counterexample_probe",
                        "probe": {"atom": p["goal"], "rule": None, "parents": []},
                        "finding": {"answer_only_accepts": True,
                                    "proof_and_goal_accepts": grounded_probe,
                                    "gap_detected": not grounded_probe}})
    return {"version": 1, "problem_id": p["id"], "problem_sha256": digest(p),
            "nodes": nodes, "final": final, "views": views, "reviews": reviews}


# ------------------- 별도 재검사: 생성기의 좌표/계획/점수를 사용하지 않음 -------------------
def verify(p: dict, trace: dict) -> dict:
    """원문 문제를 별도 입력으로 받아 증명, 표현, 검토를 재계산한다."""
    metrics: dict = {"A": None, "D": None, "M": None}
    try:
        check_problem(p)
        fields(trace, "version problem_id problem_sha256 nodes final views reviews")
        need(type(trace["version"]) is int and trace["version"] == 1, "VERSION: 지원하지 않는 버전")
        need(trace["problem_id"] == p["id"] and trace["problem_sha256"] == digest(p),
             "BINDING: 다른 문제에 대한 기록")
        nodes = trace["nodes"]
        need(isinstance(nodes, list) and 0 < len(nodes) <= MAX_NODES, "GRAPH: 노드 수 제한")
        rules = {r["id"]: r for r in p["rules"]}
        by_id: dict[str, dict] = {}
        depth: dict[str, int] = {}
        closure: dict[str, set[str]] = {}
        for n in nodes:
            fields(n, "id atom rule parents")
            key = n["id"]
            need(isinstance(key, str) and key and key not in by_id, "GRAPH: 중복/잘못된 id")
            need(isinstance(n["atom"], str), "GRAPH: 원자 형식 오류")
            strings(n["parents"], allow_empty=True)
            need(all(x in by_id for x in n["parents"]), "GRAPH: 순환/전방/누락 참조")
            if n["rule"] is None:
                need(not n["parents"] and n["atom"] in p["facts"], "PROOF: 근거 없는 사실")
                depth[key] = 0
            else:
                need(isinstance(n["rule"], str) and n["rule"] in rules, "PROOF: 허용하지 않은 규칙")
                r = rules[n["rule"]]
                need(n["atom"] == r["conclusion"], "PROOF: 규칙의 결론 불일치")
                actual = [by_id[x]["atom"] for x in n["parents"]]
                need(sorted(actual) == sorted(r["premises"]), "PROOF: 전제 불일치/생략/중복")
                depth[key] = 1 + max(depth[x] for x in n["parents"])
            closure[key] = {key}.union(*(closure[x] for x in n["parents"]))
            by_id[key] = n
        final = trace["final"]
        need(isinstance(final, str) and final in by_id, "GOAL: 최종 노드 없음")
        need(by_id[final]["atom"] == p["goal"], "GOAL: 고정 목표 불일치")
        need(closure[final] == set(by_id), "GRAPH: 최종 증명과 무관한 노드")
        metrics["D"] = depth[final]
        need(isinstance(trace["views"], dict) and set(trace["views"]) == set(by_id),
             "VIEW: 노드별 표현 누락/추가")
        observed_a: dict[str, str] = {}
        for key, view in trace["views"].items():
            need(isinstance(view, dict), "VIEW: 표현 객체 필요")
            if view.get("kind") == "instance":
                fields(view, "kind atom")
                need(view["atom"] == by_id[key]["atom"], "VIEW: 사례 표현 불일치")
                observed_a[key] = "instance"
                continue
            fields(view, "kind quantifier binding assumptions conclusion")
            need(view["kind"] == "universal_schema"
                 and view["quantifier"] == "forall_boolean_valuations", "VIEW: 보편 양화 필요")
            binding = view["binding"]
            need(isinstance(binding, dict) and 0 < len(binding) <= MAX_ATOMS,
                 "VIEW: 변수 바인딩 크기 오류")
            need(all(isinstance(k, str) and k and isinstance(v, str) for k, v in binding.items()),
                 "VIEW: 변수 바인딩 형식 오류")
            used = [by_id[x] for x in closure[key]]
            used_atoms = {n["atom"] for n in used}
            need(set(binding.values()) == used_atoms and len(binding) == len(used_atoms),
                 "VIEW: 치환은 사용 원자에 대한 일대일 대응이어야 함")
            conclusion = view["conclusion"]
            need(isinstance(conclusion, str) and binding.get(conclusion) == by_id[key]["atom"],
                 "VIEW: 도식 결론의 접지 불일치")
            expected = set()
            for n in used:
                if n["rule"] is None:
                    expected.add(((), n["atom"]))
                else:
                    r = rules[n["rule"]]
                    expected.add((tuple(sorted(r["premises"])), r["conclusion"]))
            assumptions = view["assumptions"]
            need(isinstance(assumptions, list) and 0 < len(assumptions) <= MAX_NODES,
                 "VIEW: 도식 가정 누락/초과")
            grounded = set()
            for clause in assumptions:
                fields(clause, "if then")
                strings(clause["if"], allow_empty=True)
                need(all(v in binding for v in clause["if"])
                     and isinstance(clause["then"], str) and clause["then"] in binding,
                     "VIEW: 선언하지 않은 도식 변수")
                grounded.add((tuple(sorted(binding[v] for v in clause["if"])),
                              binding[clause["then"]]))
            need(grounded == expected and len(grounded) == len(assumptions),
                 "VIEW: 가정 추가/삭제/중복으로 도식의 의미가 바뀜")
            variables = sorted(binding)
            # 생성기는 Horn 경로를 구성하고, 검증기는 모든 진리값 배정을 검사한다.
            for bits in itertools.product((False, True), repeat=len(variables)):
                valuation = dict(zip(variables, bits))
                holds = all(not all(valuation[x] for x in c["if"]) or valuation[c["then"]]
                            for c in assumptions)
                need(not holds or valuation[conclusion], "VIEW: 보편 도식 반례 발견")
            observed_a[key] = "schema"
        metrics["A"] = observed_a[final]
        reviews = trace["reviews"]
        need(isinstance(reviews, list) and len(reviews) <= 2, "META: 검토 목록 크기 오류")
        review_ids = set(by_id)
        levels = []
        for review in reviews:
            need(isinstance(review, dict), "META: 검토 객체 필요")
            rid = review.get("id")
            need(isinstance(rid, str) and rid and rid not in review_ids, "META: 검토 id 오류")
            review_ids.add(rid)
            kind = review.get("target_kind")
            if kind == "argument":
                fields(review, "id target_kind target check evidence finding")
                need(isinstance(review["target"], str) and review["target"] in by_id,
                     "META: 실재하는 논증을 지정해야 함")
                level = 1
                metrics["M"] = max([0] + levels + [level])
                need(review["check"] == "support_replay", "META: 논증 검토 절차 불일치")
                strings(review["evidence"])
                related = closure[review["target"]]
                need(set(review["evidence"]) == related, "META: 논증 검토 근거 누락/혼입")
                want = {"grounded": True,
                        "used_rules": sorted({by_id[x]["rule"] for x in related if by_id[x]["rule"]}),
                        "conclusion": by_id[review["target"]]["atom"]}
                need(canonical(review["finding"]) == canonical(want), "META: 논증 검토 판정 불일치")
            elif kind == "acceptance_criterion":
                fields(review, "id target_kind target check probe finding")
                need(review["target"] == "valid_proof_and_goal", "META: 평가 기준 대상 불명")
                level = 2
                metrics["M"] = max([0] + levels + [level])
                need(review["check"] == "counterexample_probe", "META: 기준 검토 절차 불일치")
                probe = review["probe"]
                fields(probe, "atom rule parents")
                need(isinstance(probe["atom"], str) and probe["rule"] is None
                     and probe["parents"] == [], "META: 시험 반례 형식 오류")
                answer_only = probe["atom"] == p["goal"]
                strict = answer_only and probe["atom"] in p["facts"]
                want = {"answer_only_accepts": answer_only, "proof_and_goal_accepts": strict,
                        "gap_detected": answer_only and not strict}
                need(canonical(review["finding"]) == canonical(want), "META: 기준 검토 판정 불일치")
            else:
                raise Invalid("META: 검토 대상 종류 불명")
            need(level not in levels, "META: 동일 수준의 중복 검토")
            levels.append(level)
        metrics["M"] = max([0] + levels)
        states = [{"event": n["id"], "A": observed_a[n["id"]], "D": depth[n["id"]], "M": 0}
                  for n in nodes]
        for review, level in zip(reviews, levels):
            reference = review["target"] if level == 1 else final
            states.append({"event": review["id"], "A": observed_a[reference],
                           "D": depth[reference], "M": level})
        return {"valid": True, "metrics": metrics, "states": states,
                "node_count": len(nodes), "error": None}
    except (Invalid, TypeError, KeyError, ValueError, RecursionError) as exc:
        return {"valid": False, "metrics": metrics, "states": [], "error": str(exc)}


def negative_controls(p: dict, trace: dict) -> list[tuple[str, dict]]:
    """같은 목표 문자열을 유지하는 공격을 포함한 고정 반례 묶음."""
    cases = []
    def add(name: str, change) -> None:
        candidate = copy.deepcopy(trace)
        change(candidate)
        cases.append((name, candidate))
    add("untrusted_problem", lambda t: t.update(problem_sha256="0" * 64))
    add("missing_support", lambda t: t["nodes"][-1].update(parents=[]))
    add("self_cycle", lambda t: t["nodes"][-1].update(parents=[t["final"]]))
    add("wrong_rule", lambda t: t["nodes"][-1].update(rule="nonexistent_rule"))
    add("wrong_conclusion", lambda t: t["nodes"][-1].update(atom="wrong_goal"))
    add("ungrounded_fixed_goal", lambda t: t["nodes"][-1].update(rule=None, parents=[]))
    add("duplicate_node", lambda t: t["nodes"].append(copy.deepcopy(t["nodes"][0])))
    add("missing_view", lambda t: t["views"].pop(t["final"]))
    add("empty_schema", lambda t: t["views"][t["final"]].update(assumptions=[]))
    add("no_quantifier", lambda t: t["views"][t["final"]].update(quantifier="some_valuation"))
    add("argument_false_finding", lambda t: t["reviews"][0]["finding"].update(grounded=False))
    add("criterion_false_finding", lambda t: t["reviews"][1]["finding"].update(proof_and_goal_accepts=True))
    add("unresolved_meta_target", lambda t: t["reviews"][0].update(target="missing_node"))
    add("fake_coordinate", lambda t: t.update(A=4, D=99, M=2))
    return cases


def run_suite(problems: list[dict], out: Path) -> dict:
    """전체 조건, 반복 재현, 축별 대조 및 반례 판정을 기록한다."""
    out.mkdir(parents=True, exist_ok=True)
    results = []
    rows = []
    all_reproducible = True
    for p in problems:
        for a, d, m in itertools.product(("instance", "schema"), ("shallow", "deep"), range(3)):
            trace = simulate(p, a, d, m)
            repeat = simulate(p, a, d, m)
            audit = verify(p, trace)
            reproducible = canonical(trace) == canonical(repeat)
            all_reproducible &= reproducible
            role = {"A": a, "D_policy": d, "M": m}
            results.append({"problem_id": p["id"], "role": role, "trace": trace, "audit": audit,
                            "exact_repeat": reproducible, "trace_sha256": digest(trace)})
            rows.append({"problem_id": p["id"], **role, "D_observed": audit["metrics"]["D"],
                         "valid": audit["valid"], "exact_repeat": reproducible,
                         "nodes": audit.get("node_count", 0)})
    lookup = {(r["problem_id"], r["role"]["A"], r["role"]["D_policy"], r["role"]["M"]):
              r["audit"]["metrics"] for r in results}
    contrasts = []
    for p in problems:
        pid = p["id"]
        for d, m in itertools.product(("shallow", "deep"), range(3)):
            x, y = lookup[pid, "instance", d, m], lookup[pid, "schema", d, m]
            contrasts.append({"problem_id": pid, "axis": "A", "context": [d, m],
                              "pass": x["A"] == "instance" and y["A"] == "schema"
                              and x["D"] == y["D"] and x["M"] == y["M"]})
        for a, m in itertools.product(("instance", "schema"), range(3)):
            x, y = lookup[pid, a, "shallow", m], lookup[pid, a, "deep", m]
            contrasts.append({"problem_id": pid, "axis": "D", "context": [a, m],
                              "pass": x["D"] is not None and y["D"] is not None and x["D"] < y["D"]
                              and x["A"] == y["A"] and x["M"] == y["M"]})
        for a, d, m in itertools.product(("instance", "schema"), ("shallow", "deep"), range(2)):
            x, y = lookup[pid, a, d, m], lookup[pid, a, d, m + 1]
            contrasts.append({"problem_id": pid, "axis": "M", "context": [a, d, m],
                              "pass": x["M"] == m and y["M"] == m + 1
                              and x["A"] == y["A"] and x["D"] == y["D"]})
    negatives = []
    for p in problems:
        good = simulate(p, "schema", "deep", 2)
        for name, bad in negative_controls(p, good):
            audit = verify(p, bad)
            negatives.append({"problem_id": p["id"], "mutation": name,
                              "rejected": not audit["valid"], "error": audit["error"]})
    compliance = all(r["audit"]["metrics"]["A"] == r["role"]["A"]
                     and r["audit"]["metrics"]["M"] == r["role"]["M"] for r in results)
    summary = {"problems": len(problems), "conditions": len(results),
               "generation_calls": 2 * len(results) + len(problems),
               "primary_generation_calls": 2 * len(results),
               "valid_traces": sum(r["audit"]["valid"] for r in results),
               "exact_repeats": sum(r["exact_repeat"] for r in results),
               "contrasts": len(contrasts), "contrasts_passed": sum(c["pass"] for c in contrasts),
               "negative_controls": len(negatives),
               "negative_controls_rejected": sum(n["rejected"] for n in negatives),
               "role_compliance": compliance,
               "scope": "deterministic_specification_validation_not_llm_evidence"}
    summary["pass"] = (summary["valid_traces"] == len(results) and all_reproducible and compliance
                       and all(c["pass"] for c in contrasts) and all(n["rejected"] for n in negatives))
    (out / "runs.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, data in (("summary", summary), ("contrasts", contrasts), ("negative_controls", negatives)):
        (out / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out / "metrics.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return summary


def main(argv: list[str] | None = None) -> int:
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "verify"))
    parser.add_argument("--problems", type=Path, default=base / "examples" / "problems.json")
    parser.add_argument("--out", type=Path, default=base / "results")
    parser.add_argument("--trace", type=Path, help="verify에서 사용할 단일 trace JSON 파일")
    args = parser.parse_args(argv)
    try:
        problems = load_problems(args.problems)
        if args.command == "run":
            summary = run_suite(problems, args.out)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0 if summary["pass"] else 1
        need(args.trace is not None, "CLI: verify에는 --trace 파일이 필요합니다.")
        trace = json.loads(args.trace.read_text(encoding="utf-8-sig"))
        need(isinstance(trace, dict), "CLI: trace는 JSON 객체여야 합니다.")
        problem = next((p for p in problems if p["id"] == trace.get("problem_id")), None)
        need(problem is not None, "CLI: 대응하는 원문 문제를 찾지 못했습니다.")
        audit = verify(problem, trace)
        print(json.dumps(audit, ensure_ascii=False, indent=2))
        return 0 if audit["valid"] else 1
    except (Invalid, OSError, ValueError, TypeError, KeyError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
