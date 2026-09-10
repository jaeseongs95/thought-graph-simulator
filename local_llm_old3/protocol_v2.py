"""v2 전송 형식. 명제/노드/규칙 이름을 분리하고 동적 객체 키를 없앤다.

기존 verify()의 의미 계약은 그대로다. 변환은 명시된 이름·배열 위치만 바꾼다.
누락된 부모, 목표 참조, 표현, 검토, 정답을 생성하거나 고치지 않는다.
"""
from __future__ import annotations

import copy
from typing import Any

from .common import require, strict_json
from .protocol import BOOL, STRING, NULL_OR_STRING, array, obj, validate_schema

PROTOCOL = "adm-json-v2"
NODE_ID = {"type": "string", "minLength": 1, "maxLength": 160}
INSTANCE = obj({"kind": {"const": "instance"}, "atom": STRING})
SCHEMA_VIEW = obj({
    "kind": {"const": "universal_schema"},
    "quantifier": {"const": "forall_boolean_valuations"},
    "bindings": array(obj({"variable": STRING, "atom": STRING}), 1, 10),
    "clauses": array(obj({"if": array(STRING, maximum=10), "then": STRING}), 1),
    "conclusion_var": STRING,
})
VIEW = {"anyOf": [INSTANCE, SCHEMA_VIEW]}
BARE_NODE = obj({"node_id": NODE_ID, "atom": STRING, "rule_id": NULL_OR_STRING,
                 "parent_node_ids": array(NODE_ID, maximum=10)})
NODE = obj(dict(BARE_NODE["properties"], view=VIEW))
ARGUMENT_REVIEW = obj({
    "id": STRING, "target_kind": {"const": "argument"}, "target_node_id": NODE_ID,
    "check": {"const": "support_replay"}, "evidence_node_ids": array(NODE_ID, 1),
    "finding": obj({"grounded": BOOL, "used_rules": array(STRING, maximum=32),
                    "conclusion": STRING}),
})
CRITERION_REVIEW = obj({
    "id": STRING, "target_kind": {"const": "acceptance_criterion"},
    "target": {"const": "valid_proof_and_goal"}, "check": {"const": "counterexample_probe"},
    "probe": obj({"atom": STRING, "rule": {"type": "null"},
                  "parents": array(STRING, maximum=0)}),
    "finding": obj({"answer_only_accepts": BOOL, "proof_and_goal_accepts": BOOL,
                    "gap_detected": BOOL}),
})
# 이름을 사전순으로 정렬해도 생성 순서가 nodes -> final 참조 -> reviews다.
TRANSPORT_SCHEMA = obj({
    "nodes": array(NODE, 1),
    "selected_final_node_id": NODE_ID,
    "verification_reviews": array({"anyOf": [ARGUMENT_REVIEW, CRITERION_REVIEW]}, maximum=2),
})
PROOF_SCHEMA = obj({"nodes": array(BARE_NODE, 1), "selected_final_node_id": NODE_ID})
VIEWS_SCHEMA = obj({"node_views": array(obj({"node_id": NODE_ID, "view": VIEW}), 1)})


def view_to_core(view: dict) -> dict:
    validate_schema(view, VIEW)
    if view["kind"] == "instance":
        return copy.deepcopy(view)
    pairs = view["bindings"]
    variables = [pair["variable"] for pair in pairs]
    atoms = [pair["atom"] for pair in pairs]
    require(len(variables) == len(set(variables)), "TRANSPORT: 중복 도식 변수")
    require(len(atoms) == len(set(atoms)), "TRANSPORT: 중복 도식 원자 바인딩")
    return {"kind": view["kind"], "quantifier": view["quantifier"],
            "binding": {pair["variable"]: pair["atom"] for pair in pairs},
            "assumptions": copy.deepcopy(view["clauses"]),
            "conclusion": view["conclusion_var"]}


def nodes_to_core(nodes: list[dict]) -> list[dict]:
    ids = [node["node_id"] for node in nodes]
    require(len(ids) == len(set(ids)), "TRANSPORT: 중복 노드 id")
    return [{"id": n["node_id"], "atom": n["atom"], "rule": n["rule_id"],
             "parents": copy.deepcopy(n["parent_node_ids"])} for n in nodes]


def reviews_to_core(reviews: list[dict]) -> list[dict]:
    output = []
    for review in reviews:
        item = copy.deepcopy(review)
        if item["target_kind"] == "argument":
            item["target"] = item.pop("target_node_id")
            item["evidence"] = item.pop("evidence_node_ids")
        output.append(item)
    return output


def parse_payload(content: str) -> dict:
    value = strict_json(content)
    validate_schema(value, TRANSPORT_SCHEMA)
    nodes_to_core(value["nodes"])
    for node in value["nodes"]:
        view_to_core(node["view"])
    return value


def to_trace(core: Any, problem: dict, payload: dict) -> dict:
    validate_schema(payload, TRANSPORT_SCHEMA)
    return {"version": 1, "problem_id": problem["id"], "problem_sha256": core.digest(problem),
            "nodes": nodes_to_core(payload["nodes"]),
            "final": payload["selected_final_node_id"],
            "views": {node["node_id"]: view_to_core(node["view"]) for node in payload["nodes"]},
            "reviews": reviews_to_core(payload["verification_reviews"])}


def proof_only_trace(core: Any, problem: dict, payload: dict) -> dict:
    """증명 단독 교정 과제 전용. A/M을 모델 성과로 평가하지 않는다."""
    validate_schema(payload, PROOF_SCHEMA)
    nodes = nodes_to_core(payload["nodes"])
    return {"version": 1, "problem_id": problem["id"], "problem_sha256": core.digest(problem),
            "nodes": nodes, "final": payload["selected_final_node_id"],
            "views": {n["id"]: {"kind": "instance", "atom": n["atom"]} for n in nodes},
            "reviews": []}
