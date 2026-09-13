"""Frozen v064 direct-D plan and request construction.

This module reads only the declared v058 evidence members.  It never imports or
executes a source snapshot from that evidence.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import common
import measure


CONTRACT = "v064-plan-r1"
_BASELINE_DIRECTION = "허용된 유효한 증명 중 최종 지지 깊이가 가장 작은 경로를 선택한다."
_DIRECTION_TEXT = {
    "shallow": _BASELINE_DIRECTION,
    "neutral": "허용된 유효한 증명 경로 하나를 선택한다.",
    "deep": "허용된 유효한 증명 중 최종 지지 깊이가 가장 큰 경로를 선택한다.",
}


def _member_json(files: dict[str, bytes], name: str) -> dict:
    if name not in files:
        raise ValueError("required baseline member missing: " + name)
    value = common.load(files[name])
    if not isinstance(value, dict):
        raise ValueError("baseline JSON object required: " + name)
    return value


def _baseline_material(baseline_path: Path, spec: dict) -> tuple[str, dict, dict]:
    raw = Path(baseline_path).read_bytes()
    digest = common.sha(raw)
    if digest != spec["baseline_sha256"]:
        raise ValueError("baseline SHA-256 does not match frozen protocol")
    files = common.unzip(raw)
    source_plan = None
    for name in ("run/plan.snapshot.json", "external_plan/v058.plan.json"):
        if name in files:
            source_plan = _member_json(files, name)
            break
    if source_plan is None:
        raise ValueError("v058 plan snapshot missing")
    request_name = "run/calls/" + spec["baseline_request_id"] + "/request.wire.json"
    request = _member_json(files, request_name)
    try:
        identity = deepcopy(source_plan["identities"]["reference"])
    except (KeyError, TypeError) as exc:
        raise ValueError("v058 reference identity missing") from exc
    if request.get("model") != spec["model"]:
        raise ValueError("baseline request model differs from frozen protocol")
    if identity.get("model") != spec["model"] or identity.get("digest") != spec["model_digest"]:
        raise ValueError("baseline identity differs from frozen protocol")
    return digest, request, identity


def _slots(spec: dict) -> list[dict]:
    problems = spec["problems"]
    seeds = spec["seeds"]
    orders = spec["orders"]
    if len(problems) * len(seeds) != len(orders):
        raise ValueError("protocol orders must cover each problem-seed block once")
    slots: list[dict] = []
    previous_id = None
    previous_direction = None
    for problem_index, problem in enumerate(problems):
        problem_id = problem.get("id")
        if not isinstance(problem_id, str):
            raise ValueError("problem id must be a string")
        for seed_index, seed in enumerate(seeds):
            block = problem_index * len(seeds) + seed_index
            order = orders[block]
            if not isinstance(order, list) or set(order) != set(_DIRECTION_TEXT) or len(order) != 3:
                raise ValueError("each block must contain shallow, neutral, deep once")
            for period, direction in enumerate(order):
                slot_id = f"b{block:02d}_p{problem_index}_{direction}"
                slot = {
                    "id": slot_id,
                    "problem_id": problem_id,
                    "seed": seed,
                    "seed_index": seed_index,
                    "block": block,
                    "period": period,
                    "direction": direction,
                    "previous_call_id": previous_id,
                    "previous_direction": previous_direction,
                }
                slots.append(slot)
                previous_id = slot_id
                previous_direction = direction
    if len(slots) != spec["max_inference_calls"]:
        raise ValueError("slot count differs from frozen inference budget")
    return slots


def _actions(slots: list[dict], block_count: int) -> list[dict]:
    actions: list[dict] = []
    for block in range(block_count):
        block_slots = [slot for slot in slots if slot["block"] == block]
        if len(block_slots) != 3:
            raise ValueError("each block must contain exactly three calls")
        actions.append({"kind": "metadata", "id": f"b{block:02d}_before"})
        actions.extend({"kind": "call", "id": slot["id"]} for slot in block_slots)
        actions.append({"kind": "metadata", "id": f"b{block:02d}_after"})
    return actions


def build_plan(baseline_path: Path, run_name: str, provenance: str = "live") -> dict:
    """Build the frozen 18-call plan from the declared v058 evidence ZIP."""
    if provenance not in {"live", "synthetic"}:
        raise ValueError("provenance must be live or synthetic")
    spec = common.spec()
    if spec.get("contract") != "v064-direct-D-r1":
        raise ValueError("unexpected v064 protocol contract")
    for problem in spec["problems"]:
        if measure.depth_ranges(problem) != spec["depth_ranges"].get(problem["id"]):
            raise ValueError("frozen depth range disagrees with input proof paths")
    baseline_sha256, baseline_request, identity = _baseline_material(Path(baseline_path), spec)
    slots = _slots(spec)
    plan = {
        "contract": CONTRACT,
        "run_name": common.check_run_name(run_name),
        "provenance": provenance,
        "protocol": deepcopy(spec),
        "protocol_sha256": common.sha((common.ROOT / "data/protocol.json").read_bytes()),
        "source_hashes": common.source_hashes(),
        "baseline_sha256": baseline_sha256,
        "baseline_request": baseline_request,
        "identity": identity,
        "slots": slots,
        "actions": _actions(slots, len(spec["problems"]) * len(spec["seeds"])),
    }
    plan["plan_sha256"] = common.sha(common.wire(plan))
    return plan


def _problem(plan: dict, problem_id: str) -> dict:
    for problem in plan["protocol"]["problems"]:
        if problem.get("id") == problem_id:
            return problem
    raise ValueError("slot refers to unknown protocol problem: " + str(problem_id))


def request_for(plan: dict, slot: dict) -> dict:
    """Create a request by changing only the seed, direction sentence, and problem.

    Expected depths, an oracle, and scoring output are intentionally absent from
    this function.
    """
    if plan.get("contract") != CONTRACT:
        raise ValueError("v064 plan contract required")
    direction = slot.get("direction")
    if direction not in _DIRECTION_TEXT:
        raise ValueError("unknown direction")
    body = deepcopy(plan["baseline_request"])
    try:
        messages = body["messages"]
        options = body["options"]
        content = messages[0]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("baseline request has unexpected shape") from exc
    if (len(messages) != 1 or messages[0].get("role") != "user" or
            not isinstance(content, str) or not isinstance(options, dict)):
        raise ValueError("baseline request has unexpected message shape")
    if content.count(_BASELINE_DIRECTION) != 1:
        raise ValueError("baseline shallow direction sentence is not unique")
    problem_marker = "\n\nproblem: "
    if content.count(problem_marker) != 1:
        raise ValueError("baseline problem marker is not unique")
    prefix, _marker, _old_problem = content.partition(problem_marker)
    problem = _problem(plan, slot.get("problem_id"))
    messages[0]["content"] = (prefix.replace(_BASELINE_DIRECTION, _DIRECTION_TEXT[direction])
                              + problem_marker + common.wire(problem).decode("utf-8"))
    options["seed"] = slot.get("seed")
    if not isinstance(options["seed"], int) or isinstance(options["seed"], bool):
        raise ValueError("slot seed must be an integer")
    limit = plan["protocol"]["request_utf8_byte_limit"]
    if len(common.wire(body)) > limit:
        raise ValueError("request exceeds frozen UTF-8 byte limit")
    return body
