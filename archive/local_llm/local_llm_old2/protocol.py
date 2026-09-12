"""조건 공통 출력 스키마와 무보정 변환. A/D/M 정답을 문법에 강제하지 않는다."""
from __future__ import annotations

import copy
from typing import Any

from .common import ContractError, require, strict_json


def obj(properties: dict, **extra: Any) -> dict:
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False, **extra}


def array(items: dict, minimum: int = 0, maximum: int = 128) -> dict:
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum}


STRING = {"type": "string", "minLength": 1, "maxLength": 160}
BOOL = {"type": "boolean"}
NULL_OR_STRING = {"anyOf": [STRING, {"type": "null"}]}
INSTANCE = obj({"kind": {"const": "instance"}, "atom": STRING})
SCHEMA_VIEW = obj({
    "kind": {"const": "universal_schema"},
    "quantifier": {"const": "forall_boolean_valuations"},
    "binding": {"type": "object", "minProperties": 1, "maxProperties": 10,
                "additionalProperties": STRING},
    "assumptions": array(obj({"if": array(STRING, maximum=10), "then": STRING}), 1),
    "conclusion": STRING,
})
ARGUMENT_REVIEW = obj({
    "id": STRING, "target_kind": {"const": "argument"}, "target": STRING,
    "check": {"const": "support_replay"}, "evidence": array(STRING, 1),
    "finding": obj({"grounded": BOOL, "used_rules": array(STRING, maximum=32),
                    "conclusion": STRING}),
})
CRITERION_REVIEW = obj({
    "id": STRING, "target_kind": {"const": "acceptance_criterion"},
    "target": {"const": "valid_proof_and_goal"},
    "check": {"const": "counterexample_probe"},
    "probe": obj({"atom": STRING, "rule": {"type": "null"},
                  "parents": array(STRING, maximum=0)}),
    "finding": obj({"answer_only_accepts": BOOL, "proof_and_goal_accepts": BOOL,
                    "gap_detected": BOOL}),
})
TRANSPORT_SCHEMA = obj({
    "nodes": array(obj({
        "id": STRING, "atom": STRING, "rule": NULL_OR_STRING,
        "parents": array(STRING, maximum=10),
        "view": {"anyOf": [INSTANCE, SCHEMA_VIEW]},
    }), 1),
    "final": STRING,
    "reviews": array({"anyOf": [ARGUMENT_REVIEW, CRITERION_REVIEW]}, maximum=2),
})


def validate_schema(value: Any, schema: dict, path: str = "$") -> None:
    """위 스키마에서 사용하는 키워드만 구현한 엄격한 검사기. 범용 JSON Schema가 아니다."""
    allowed = {"anyOf", "type", "const", "properties", "required", "additionalProperties",
               "minItems", "maxItems", "items", "minLength", "maxLength",
               "minProperties", "maxProperties"}
    require(not (set(schema) - allowed), f"검사기가 지원하지 않는 스키마: {path}")
    if "anyOf" in schema:
        for choice in schema["anyOf"]:
            try:
                validate_schema(value, choice, path)
                return
            except ContractError:
                pass
        raise ContractError(f"SCHEMA {path}: 허용된 형식 중 어느 것과도 맞지 않습니다.")
    if "const" in schema:
        require(type(value) is type(schema["const"]) and value == schema["const"],
                f"SCHEMA {path}: 상수 불일치")
    kind = schema.get("type")
    if kind is None:
        return
    expected = {"object": dict, "array": list, "string": str, "boolean": bool,
                "null": type(None)}
    require(kind in expected and type(value) is expected[kind],
            f"SCHEMA {path}: {kind} 형식 필요")
    if kind == "object":
        require(schema.get("minProperties", 0) <= len(value) <= schema.get("maxProperties", 1000),
                f"SCHEMA {path}: 객체 크기 제한")
        props = schema.get("properties", {})
        require(set(schema.get("required", [])) <= set(value), f"SCHEMA {path}: 필수 필드 누락")
        extra = schema.get("additionalProperties", True)
        for key, item in value.items():
            require(isinstance(key, str) and bool(key), f"SCHEMA {path}: 빈/잘못된 키")
            if key in props:
                validate_schema(item, props[key], f"{path}.{key}")
            elif extra is False:
                raise ContractError(f"SCHEMA {path}: 허용하지 않은 필드 {key}")
            elif isinstance(extra, dict):
                validate_schema(item, extra, f"{path}.{key}")
    elif kind == "array":
        require(schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 1000),
                f"SCHEMA {path}: 배열 크기 제한")
        for index, item in enumerate(value):
            validate_schema(item, schema["items"], f"{path}[{index}]")
    elif kind == "string":
        require(schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 100000),
                f"SCHEMA {path}: 문자열 길이 제한")


def parse_payload(content: str) -> dict:
    # 코드 블록 제거, 중괄호 탐색, 자동완성, JSON 수리 등을 하지 않는다.
    value = strict_json(content)
    validate_schema(value, TRANSPORT_SCHEMA)
    ids = [node["id"] for node in value["nodes"]]
    require(len(ids) == len(set(ids)), "TRANSPORT: 중복 노드 id")
    return value


def to_trace(core: Any, problem: dict, payload: dict) -> dict:
    """LLM이 낸 view 위치만 옮긴다. 외부 계약 식별자·해시만 호스트에서 붙인다."""
    validate_schema(payload, TRANSPORT_SCHEMA)
    ids = [n["id"] for n in payload["nodes"]]
    require(len(ids) == len(set(ids)), "TRANSPORT: 중복 노드 id")
    return {
        "version": 1, "problem_id": problem["id"], "problem_sha256": core.digest(problem),
        "nodes": [{k: copy.deepcopy(n[k]) for k in ("id", "atom", "rule", "parents")}
                  for n in payload["nodes"]],
        "final": payload["final"],
        "views": {n["id"]: copy.deepcopy(n["view"]) for n in payload["nodes"]},
        "reviews": copy.deepcopy(payload["reviews"]),
    }
