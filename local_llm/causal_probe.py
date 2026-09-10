"""12회 원인 분리 진단. 기본 실험을 바꾸거나 과거 응답을 교정하지 않는다.

증명: 동일 3문제에서 기존/간결 프롬프트 대응 6회.
도식: 동일 지시에서 format만 union/schema_only/json으로 변경 3회.
기준: 서로 다른 정답 패턴 3회. 모델 판단의 정답은 요청에 넣지 않는다.
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .calibration import output_schema
from .calibration_v4 import fixtures
from .common import ContractError, REPO, digest, load_core, require, wire_json, write_json
from .design import reference_depths
from .protocol_v2 import SCHEMA_VIEW

CONTRACT = "causal-v041"


def build_probe_plan(core: Any, seed: int = 1729) -> dict:
    require(type(seed) is int and 0 <= seed < 2**31 - 1000, "시드 범위 오류")
    fixed = fixtures()
    problems = {p["id"]: copy.deepcopy(p) for p, _ in fixed}
    cases = []

    def add(name: str, task: str, problem: dict, variant: str, **kwargs: Any) -> None:
        case = {"problem_id": problem["id"], "problem_sha256": core.digest(problem),
                "role": {"kind": "neutral", "A": None, "D_policy": None, "M": None},
                "role_id": name, "task": task, "repeat": 0, "seed": seed,
                "calibration_version": 4, "probe_contract": CONTRACT,
                "probe_variant": variant, **kwargs}
        case["case_id"] = digest(case)[:24]
        cases.append(case)

    for p, _ in fixed:
        for variant in ("baseline", "compact"):
            add(f"proof_{p['id']}_{variant}", "proof", p, variant, depth_policy="deep")
    p, proof = fixed[2]
    for variant in ("union", "schema_only", "json"):
        add(f"schema_{p['id']}_{variant}", "schema", p, variant,
            view_scope="final_node_only", provided_proof=copy.deepcopy(proof))
    p = fixed[0][0]
    given = copy.deepcopy(p)
    given["id"] = "K11"
    given["facts"].append(given["goal"])
    problems[given["id"]] = given
    for index, problem, atom in ((1, p, p["goal"]), (2, p, p["facts"][0]),
                                  (3, given, given["goal"])):
        add(f"criterion_{index:02d}_compact", "criterion", problem, "compact", probe_atom=atom)
    random.Random(seed + 701117).shuffle(cases)
    for p in problems.values():
        core.check_problem(p)
    return {"profile": "causal-probe", "experiment_kind": "calibration", "probe_contract": CONTRACT,
            "repeats": 1, "seed": seed, "problems": list(problems.values()), "roles": [],
            "cases": cases, "assigned_calls": len(cases),
            "reference_depths": {p["id"]: reference_depths(p) for p in problems.values()},
            "warnings": [], "scope": "paired_component_diagnostic_not_ADM_validation",
            "design_note": "증명 대응은 프롬프트 묶음의 효과다. 예시/길이 각각의 효과를 분리했다고 하지 않는다. "
                           "도식 3조건은 messages가 같고 format만 다르다. schema_only는 호스트 강제다."}


def compact_messages(problem: dict, case: dict) -> list[dict]:
    task = case["task"]
    content = "문제: " + wire_json(problem)
    if task == "proof":
        system = (
            "주어진 facts와 rules만 사용해 goal의 유효한 증명 하나를 JSON으로 제출한다.\n"
            "규칙의 premises는 동시에 모두 필요한 명제들이다. 노드를 바로 앞 노드에 자동 연결하지 않는다.\n"
            "사실 노드는 rule_id=null, parent_node_ids=[]이고 atom은 facts 원소다.\n"
            "규칙 노드의 atom은 그 규칙 conclusion이다. parent_node_ids는 해당 premises의 원자를 가진 "
            "이미 제출한 노드 ID를 정확히 가리켜야 한다. 같은 지지 노드를 여러 갈래에서 재사용할 수 있다.\n"
            "한 분기에서 같은 원자를 다시 도출하거나 facts를 규칙으로 다시 도출하지 않는다.\n"
            "사실 깊이=0, 규칙 깊이=1+max(부모 깊이). 가능한 증명 중 최종 깊이가 가장 큰 것을 선택한다.\n"
            "선택한 최종 노드와 그 조상만 부모부터 제출한다. 대안 경로는 넣지 않는다.\n"
            "출력은 nodes와 selected_final_node_id 두 필드다. 각 노드는 "
            "node_id, atom, rule_id, parent_node_ids만 가진다. view/review는 쓰지 않는다. "
            "node_id와 명제 atom/규칙 id를 구분한다. JSON 외 문장은 쓰지 않는다."
        )
    elif task == "schema":
        system = (
            "고정 증명은 수정하지 않는다. 최종 노드에 대한 universal_schema view 딱 하나만 JSON으로 작성한다.\n"
            "출력은 {node_views:[{node_id,view}]} 형태다. node_id는 제공한 selected_final_node_id다.\n"
            "view의 필드는 kind,quantifier,bindings,clauses,conclusion_var다. kind=universal_schema, "
            "quantifier=forall_boolean_valuations다.\n"
            "최종 노드와 지지 조상 전체의 서로 다른 원자를 bindings의 {variable,atom} 항목으로 일대일 대응한다.\n"
            "clauses의 각 항목은 {if:[변수들],then:변수}다. 실제 사실은 if=[], 실제 사용 규칙은 "
            "모든 전제 변수를 if에 넣는다. 부분 증명에 있는 사실과 사용 규칙을 각각 한 번씩 모두 포함한다.\n"
            "결론을 새 사실로 추가하지 않는다. conclusion_var는 최종 원자에 대응하는 변수다.\n"
            "중간 노드 view나 instance view를 반환하지 않는다. JSON 외 문장은 쓰지 않는다."
        )
        content += "\n고정 증명: " + wire_json(case["provided_proof"])
    else:
        system = (
            "주어진 problem과 독립된 단독 probe에 대해 아래 정의를 그대로 계산한다.\n"
            "answer_only_accepts := (probe.atom == problem.goal)\n"
            "proof_and_goal_accepts := answer_only_accepts AND (probe.atom IN problem.facts)\n"
            "gap_detected := (answer_only_accepts != proof_and_goal_accepts)\n"
            "probe는 rule=null, parents=[]다. rules를 통한 도출 가능성은 이 단독 사실 주장의 근거가 아니다.\n"
            "위 세 필드의 boolean 값을 가진 JSON 객체 하나만 반환한다."
        )
        content += "\nprobe: " + wire_json({"atom": case["probe_atom"], "rule": None, "parents": []})
    return [{"role": "system", "content": system}, {"role": "user", "content": content}]


def make_request(config: dict, case: dict, problem: dict) -> dict:
    require(case.get("probe_contract") == CONTRACT, "원인 분리 계약 불일치")
    variant = case["probe_variant"]
    if variant == "baseline":
        # 기존 요청 팩토리를 그대로 사용한다. 새 case 표지는 프롬프트에 보내지 않는다.
        from .runner import request_body
        old_case = copy.deepcopy(case)
        old_case.pop("probe_contract")
        old_config = copy.deepcopy(config)
        old_config["prompt_profile"] = "factorized-v4"
        return request_body(old_config, old_case, problem)
    schema: dict | str = output_schema(case)
    if case["task"] == "schema":
        require(variant in {"union", "schema_only", "json"}, "도식 진단 변형 오류")
        if variant == "schema_only":
            # A를 모델이 선택한 성과로 세지 않는 문법 가용성 진단이다.
            schema["properties"]["node_views"]["items"]["properties"]["view"] = copy.deepcopy(SCHEMA_VIEW)
        elif variant == "json":
            schema = "json"
    else:
        require(variant == "compact", "프롬프트 진단 변형 오류")
    prompt = compact_messages(problem, case)
    body = {"model": config["model"], "messages": prompt, "stream": False,
            "keep_alive": "10m", "format": schema,
            "options": dict(config["options"], seed=case["seed"])}
    if config.get("think") is not None:
        body = {"model": config["model"], "messages": prompt, "stream": False,
                "think": config["think"], "keep_alive": "10m", "format": schema,
                "options": dict(config["options"], seed=case["seed"])}
    return body


def summarize_probe(plan: dict, records: list[dict]) -> dict:
    lookup = {r["case"]["case_id"]: r for r in records}
    pairs: dict[str, dict] = {}
    cases = []
    for c in plan["cases"]:
        r = lookup.get(c["case_id"])
        item = {"case_id": c["case_id"], "task": c["task"], "problem_id": c["problem_id"],
                "variant": c["probe_variant"], "status": r["status"] if r else "not_started",
                "accepted": bool(r and r["status"] == "accepted"),
                "audit": (r or {}).get("audit"), "usage": (r or {}).get("usage"),
                "host_forced_schema_kind": c["probe_variant"] == "schema_only"}
        cases.append(item)
        if c["task"] == "proof":
            pairs.setdefault(c["problem_id"], {})[c["probe_variant"]] = {
                k: item[k] for k in ("case_id", "status", "accepted")}
    return {"contract": CONTRACT, "cases": cases,
            "proof_pairs": [{"problem_id": pid, **entry} for pid, entry in pairs.items()],
            "not_an_ADM_success_rate": True,
            "interpretation": "대응 결과는 진단 단서다. 단일 시드 결과로 원인의 확률·모델 전체 능력을 확정하지 않는다. "
                              "baseline/compact는 프롬프트 묶음 비교, 도식 3조건은 format만 바꾼 비교다."}


def main(argv: list[str] | None = None) -> int:
    from .__main__ import generation_arguments, generation_config
    from .client import APIError
    from .runner import run
    parser = argparse.ArgumentParser(description="원인 분리 진단 12회. --plan-only는 네트워크/추론 없음")
    generation_arguments(parser)
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--allow-core-change", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--save-plan", type=Path)
    args = parser.parse_args(argv)
    try:
        require(args.prompt_profile == "factorized-v4", "이 진단은 고정된 baseline/compact 대응을 사용합니다.")
        core, info = load_core(args.allow_core_change)
        plan = build_probe_plan(core, args.seed)
        if args.save_plan:
            require(not args.save_plan.exists(), "조건표 파일이 이미 존재합니다.")
            write_json(args.save_plan, plan)
        if args.plan_only:
            print(json.dumps({"assigned_calls": plan["assigned_calls"], "model_called": False,
                              "cases": [{"id": c["role_id"], "variant": c["probe_variant"]} for c in plan["cases"]],
                              "note": plan["design_note"]}, ensure_ascii=False, indent=2))
            return 0
        config = generation_config(args)
        out = args.out or REPO / "results_llm" / f"v041_probe_{datetime.now():%Y%m%d_%H%M%S}"
        print(f"원인 분리 진단: 12회 / 모델: {args.model} / 결과: {out}", flush=True)
        return run(core, info, plan, config, out, args.resume,
                   fail_on_model_failure=args.fail_on_model_failure)
    except (ContractError, APIError, OSError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
