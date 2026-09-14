"""모델 호출 전 문제 계약만 검증한다. 생성 응답/부모 연결을 보정하지 않는다."""
from __future__ import annotations
from collections import Counter
import common
import measure


def candidate_graph(problem: dict, rule_ids: list[str]) -> dict:
    """오프라인 양성 대조용. live request/response 처리에서는 호출하지 않는다."""
    nodes = [{"id": f"f{i}", "atom": atom, "rule": None, "parents": []}
             for i, atom in enumerate(problem["facts"])]
    atom_ids = {n["atom"]: n["id"] for n in nodes}
    rules = {r["id"]: r for r in problem["rules"]}
    if len(set(rule_ids)) != len(rule_ids):
        raise ValueError("후보 규칙 중복")
    for i, rid in enumerate(rule_ids):
        r = rules[rid]
        if not r["premises"] or any(a not in atom_ids for a in r["premises"]):
            raise ValueError("비위상/도달 불가 후보")
        if r["conclusion"] in atom_ids:
            raise ValueError("후보의 중복 결론")
        n = {"id": f"n{i}", "atom": r["conclusion"], "rule": rid,
             "parents": [atom_ids[a] for a in r["premises"]]}
        nodes.append(n)
        atom_ids[n["atom"]] = n["id"]
    return {"nodes": nodes, "final_node_id": atom_ids[problem["goal"]]}


def validate(s: dict) -> dict:
    if s["generator_variants"] != ["base"] or len(s["problems"]) != 4:
        raise ValueError("v078은 4개 구조와 base 한 군으로 동결됨")
    if len(s["seeds"]) != 2 or s["candidate_orders"] != [[0, 1], [1, 0]]:
        raise ValueError("seed/후보 순서 계약")
    ids = [p["id"] for p in s["problems"]]
    if len(set(ids)) != 4 or any(i in ("T02", "E01_shared_fork", "E02_two_vs_four") for i in ids):
        raise ValueError("기존 개발 문제를 새 문제로 재명명하지 않음")
    out=[]; families=Counter(); ref_calls=model_max=target_calls=0
    for p in s["problems"]:
        if set(p) != {"id", "facts", "rules", "goal"}:
            raise ValueError("모델 문제 객체에 정답/설계층 메타데이터 금지")
        m=s["problem_metadata"][p["id"]]; paths=s["reference_plans"][p["id"]]
        if set(paths) != set(s["reference_conditions"]): raise ValueError("후보 개수")
        ds=[]; ns=[]; covered=[]
        for condition in s["reference_conditions"]:
            sequence=paths[condition];g=candidate_graph(p, sequence);result=measure.assess(p,g)
            if result["strict_valid"] is not True: raise ValueError("후보의 전체 goal ancestry/증명 오류")
            ds.append(result["actual_D"]);ns.append(sum(n["rule"] is not None for n in g["nodes"]))
            covered.extend(sequence)
        if Counter(covered) != Counter(r["id"] for r in p["rules"]):
            raise ValueError("숨은 경로/미사용 규칙/후보 간 중복 규칙")
        if ds[0] >= ds[1] or ds != measure.depth_ranges(p) or ds != s["depth_ranges"][p["id"]]:
            raise ValueError("D 범위/후보 깊이 불일치")
        if ds != [m["shallow_D"], m["deep_D"]] or ns != [m["shallow_rule_count"], m["deep_rule_count"]]:
            raise ValueError("메타데이터와 실제 구조 불일치")
        family=m["family"];families[family]+=1
        if family == "equal_rule_count":
            if ns[0] != ns[1]: raise ValueError("동일 규칙 수 조건 위반")
        elif family == "inverted_rule_count":
            if ns[0] <= ns[1]: raise ValueError("규칙 수-D 역전 조건 위반")
        else: raise ValueError("알 수 없는 설계층")
        if len(g["nodes"]) > 16: raise ValueError("기존 graph 크기 계약 초과")
        ref_calls += 2 * (sum(ns) + 4)
        model_max += 8 * (max(ns) + 2)
        target_calls += 6 * (sum(ns) + 4) + 8
        out.append({"problem_id":p["id"],"family":family,"depths":ds,"rule_counts":ns})
    expected={"reference_generator_calls":ref_calls,"max_model_generator_calls":model_max,
              "max_inference_calls":32+ref_calls+model_max,
              "expected_inference_calls_if_all_target_routes_selected":target_calls,
              "max_action_slots":32+ref_calls+model_max+16,
              "assigned_model_trials":32,"assigned_control_trials":16,"assigned_model_pairs":16,
              "selector_calls":32,"metadata_slots":16}
    if families != {"equal_rule_count":2,"inverted_rule_count":2}: raise ValueError("설계층 수")
    if any(s[k] != v for k,v in expected.items()): raise ValueError("추론/시행 예산 불일치")
    return {"validated":True,"distinct_structural_problems":4,"cases":out,
            **expected,"actual_model_inference":False}

if __name__ == "__main__":
    import json
    print(json.dumps(validate(common.spec()),ensure_ascii=False,indent=2))
