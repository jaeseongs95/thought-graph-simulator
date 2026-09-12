"""문제·목표를 고정한 조건표. 참조 깊이는 모델 프롬프트에 전달하지 않는다."""
from __future__ import annotations

import itertools
import random
from functools import lru_cache
from typing import Any

from .common import digest, require


def role_id(role: dict) -> str:
    if role["kind"] == "neutral":
        return "neutral"
    return f'{role["A"]}_{role["D_policy"]}_M{role["M"]}'


def all_roles() -> list[dict]:
    roles = [{"kind": "neutral", "A": None, "D_policy": None, "M": None}]
    roles.extend({"kind": "directed", "A": a, "D_policy": d, "M": m}
                 for a, d, m in itertools.product(("instance", "schema"),
                                                 ("shallow", "deep"), range(3)))
    return roles


def reference_depths(problem: dict) -> dict:
    """같은 원자가 한 지지 경로에 재등장하지 않는 증명의 가능한 깊이 집합.

    기존 생성기 simulate/_plans를 호출하지 않는다. 규칙 선택이나 참조 trace를
    모델에 제공하지 않는다. 사실은 깊이 0에서 끝내는 기존 생성기 규약을 따른다.
    """
    states = 0
    @lru_cache(maxsize=None)
    def visit(atom: str, ancestors: frozenset[str]) -> frozenset[int]:
        nonlocal states
        states += 1
        require(states <= 20000, "참조 깊이 탐색 한도 초과")
        if atom in ancestors:
            return frozenset()
        if atom in problem["facts"]:
            return frozenset({0})
        output: set[int] = set()
        for rule in problem["rules"]:
            if rule["conclusion"] != atom:
                continue
            maxima = {0}
            for premise in rule["premises"]:
                choices = visit(premise, ancestors | {atom})
                maxima = {max(x, y) for x in maxima for y in choices}
                if not maxima:
                    break
            output.update(1 + item for item in maxima)
        return frozenset(output)
    values = sorted(visit(problem["goal"], frozenset()))
    return {"reachable": bool(values), "depths": values,
            "minimum": min(values) if values else None,
            "maximum": max(values) if values else None,
            "has_depth_contrast": len(values) > 1,
            "definition": "simple_branch_paths_facts_are_terminal"}


def build_plan(core: Any, problems: list[dict], profile: str,
               repeats: int | None, seed: int) -> dict:
    require(profile in {"smoke", "pilot", "full"}, "알 수 없는 프로필")
    require(type(seed) is int and 0 <= seed < 2**31 - 1000, "시드 범위 오류")
    require(isinstance(problems, list) and bool(problems), "문제가 없습니다.")
    for problem in problems:
        core.check_problem(problem)
    require(len({p["id"] for p in problems}) == len(problems), "중복 문제 id")
    count = repeats if repeats is not None else (3 if profile == "full" else 1)
    require(type(count) is int and 1 <= count <= 100, "반복 횟수는 1~100이어야 합니다.")
    chosen = problems[:1] if profile == "smoke" else problems
    roles = all_roles()
    if profile == "smoke":
        wanted = {"neutral", "instance_shallow_M0", "schema_shallow_M0",
                  "instance_deep_M0", "instance_shallow_M1", "instance_shallow_M2"}
        roles = [r for r in roles if role_id(r) in wanted]
    references = {p["id"]: reference_depths(p) for p in chosen}
    cases = []
    for repeat in range(count):
        block = []
        for problem in chosen:
            for role in roles:
                item = {"problem_id": problem["id"], "problem_sha256": core.digest(problem),
                        "role": role, "role_id": role_id(role), "repeat": repeat,
                        "seed": seed + repeat}
                item["case_id"] = digest(item)[:24]
                block.append(item)
        # 반복 블록 안의 문제/조건 순서를 섞는다. 모든 조건의 예산·스키마는 동일하다.
        random.Random(seed + repeat + 100003).shuffle(block)
        cases.extend(block)
    require(len({c["case_id"] for c in cases}) == len(cases), "실험 case id 충돌")
    warnings = []
    for pid, ref in references.items():
        if not ref["reachable"]:
            warnings.append(f"{pid}: 도달 불가능한 목표. 성공하지 못해도 제외하지 않습니다.")
        elif not ref["has_depth_contrast"]:
            warnings.append(f"{pid}: 서로 다른 깊이의 증명이 없어 D 대조는 통과할 수 없습니다.")
    return {"profile": profile, "repeats": count, "seed": seed,
            "problems": chosen, "roles": roles, "cases": cases,
            "assigned_calls": len(cases), "reference_depths": references,
            "warnings": warnings,
            "scope": "fixed_goal_formal_trace_role_following_not_latent_cognition"}
