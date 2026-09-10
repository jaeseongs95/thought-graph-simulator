"""추가 문제 구조. 학습/예시 정답으로 런타임 생성기를 호출하지 않는다.

동일한 문제는 A/D/M 모든 역할에서 그대로 사용한다. 규칙명/배열 위치에
'shortcut/direct/deep' 정답 단서를 넣지 않는다. 이름/배열 순서만 시드로 재배치한다.
"""
from __future__ import annotations

import copy
import random

from .common import require

# 사례 전체의 위상은 프롬프트의 3원자/3규칙 설명용 그래프와 다르다.
STRUCTURES = [
    {"id": "transfer_01", "facts": ["a", "b"], "rules": [
        {"id": "u1", "premises": ["a"], "conclusion": "c"},
        {"id": "u2", "premises": ["b"], "conclusion": "d"},
        {"id": "u3", "premises": ["c", "d"], "conclusion": "g"},
        {"id": "u4", "premises": ["c", "b"], "conclusion": "e"},
        {"id": "u5", "premises": ["e"], "conclusion": "f"},
        {"id": "u6", "premises": ["f"], "conclusion": "g"}], "goal": "g"},
    {"id": "transfer_02", "facts": ["a", "b"], "rules": [
        {"id": "u1", "premises": ["a"], "conclusion": "c"},
        {"id": "u2", "premises": ["c"], "conclusion": "d"},
        {"id": "u3", "premises": ["c", "b"], "conclusion": "e"},
        {"id": "u4", "premises": ["d", "e"], "conclusion": "g"},
        {"id": "u5", "premises": ["a", "b"], "conclusion": "h"},
        {"id": "u6", "premises": ["h"], "conclusion": "g"}], "goal": "g"},
    {"id": "transfer_03", "facts": ["a", "b"], "rules": [
        {"id": "u1", "premises": ["a"], "conclusion": "c"},
        {"id": "u2", "premises": ["c"], "conclusion": "d"},
        {"id": "u3", "premises": ["d"], "conclusion": "c"},
        {"id": "u4", "premises": ["d", "b"], "conclusion": "e"},
        {"id": "u5", "premises": ["e"], "conclusion": "g"},
        {"id": "u6", "premises": ["a", "b"], "conclusion": "h"},
        {"id": "u7", "premises": ["h"], "conclusion": "i"},
        {"id": "u8", "premises": ["i"], "conclusion": "g"},
        {"id": "u9", "premises": ["a"], "conclusion": "x"}], "goal": "g"},
]


def transfer_problems(seed: int = 1729) -> list[dict]:
    require(type(seed) is int and 0 <= seed < 2**31 - 1000, "데이터 시드 범위 오류")
    results = copy.deepcopy(STRUCTURES)
    for index, p in enumerate(results):
        rng = random.Random(seed + 390001 + index)
        atoms = sorted(set(p["facts"]) | {p["goal"]} |
                       {a for r in p["rules"] for a in r["premises"]} |
                       {r["conclusion"] for r in p["rules"]})
        names = [f"Atom{k:02d}" for k in range(1, len(atoms) + 1)]
        rng.shuffle(names)
        renamed = dict(zip(atoms, names))
        p["facts"] = [renamed[a] for a in p["facts"]]
        p["goal"] = renamed[p["goal"]]
        ids = [f"rule{k:02d}" for k in range(1, len(p["rules"]) + 1)]
        rng.shuffle(ids)
        for r, key in zip(p["rules"], ids):
            r.update(id=key, premises=[renamed[a] for a in r["premises"]],
                     conclusion=renamed[r["conclusion"]])
            rng.shuffle(r["premises"])
        rng.shuffle(p["facts"])
        rng.shuffle(p["rules"])
    return results


def structure_size(problem: dict) -> dict:
    atoms = set(problem["facts"]) | {problem["goal"]}
    for rule in problem["rules"]:
        atoms.update(rule["premises"])
        atoms.add(rule["conclusion"])
    return {"atoms": len(atoms), "facts": len(problem["facts"]), "rules": len(problem["rules"]),
            "premise_arities": sorted(len(r["premises"]) for r in problem["rules"])}
