"""Production measurement for v064 proof-DAG responses."""
from __future__ import annotations

from collections import Counter
from itertools import product

import common


_RESULT_KEYS = ("format_valid", "proof_valid", "strict_valid", "actual_D", "final_rule_id", "error_codes")
_STATUSES = {"ok", "invalid_json", "invalid_schema", "incomplete_response", "http_error", "transport_error", "identity_error"}


def _result(*, format_valid, proof_valid, strict_valid, actual_D, final_rule_id, error_codes):
    return {
        "format_valid": format_valid,
        "proof_valid": proof_valid,
        "strict_valid": strict_valid,
        "actual_D": actual_D,
        "final_rule_id": final_rule_id,
        "error_codes": sorted(set(error_codes)),
    }


def _schema_valid(payload) -> bool:
    if not isinstance(payload, dict) or set(payload) != {"nodes", "final_node_id"}:
        return False
    nodes = payload["nodes"]
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 16:
        return False
    if not _text(payload["final_node_id"]):
        return False
    for node in nodes:
        if not isinstance(node, dict) or set(node) != {"id", "atom", "rule", "parents"}:
            return False
        if not _text(node["id"]) or not _text(node["atom"]):
            return False
        if node["rule"] is not None and not _text(node["rule"]):
            return False
        parents = node["parents"]
        if not isinstance(parents, list) or len(parents) > 16 or not all(_text(parent) for parent in parents):
            return False
    return True


def _text(value) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= 128


def _cycle(nodes: dict[str, dict]) -> bool:
    colors: dict[str, int] = {}

    def visit(node_id: str) -> bool:
        color = colors.get(node_id, 0)
        if color == 1:
            return True
        if color == 2:
            return False
        colors[node_id] = 1
        for parent in nodes[node_id]["parents"]:
            if parent in nodes and visit(parent):
                return True
        colors[node_id] = 2
        return False

    return any(visit(node_id) for node_id in nodes if colors.get(node_id, 0) == 0)


def _ancestors(nodes: dict[str, dict], final_id: str) -> set[str]:
    found, pending = set(), [final_id]
    while pending:
        node_id = pending.pop()
        if node_id not in found and node_id in nodes:
            found.add(node_id)
            pending.extend(nodes[node_id]["parents"])
    return found


def _depth(nodes: dict[str, dict], final_id: str) -> int:
    cache: dict[str, int] = {}

    def visit(node_id: str) -> int:
        if node_id not in cache:
            node = nodes[node_id]
            cache[node_id] = 0 if node["rule"] is None else 1 + max(visit(parent) for parent in node["parents"])
        return cache[node_id]

    return visit(final_id)


def _topological_order(emitted_nodes: list[dict]) -> bool:
    """Require every parent to have appeared before its child in the response."""
    seen: set[str] = set()
    for node in emitted_nodes:
        if any(parent not in seen for parent in node["parents"]):
            return False
        seen.add(node["id"])
    return True


def depth_ranges(problem: dict) -> list[int]:
    """Return the minimum and maximum reachable proof depth for an acyclic input.

    This is a preflight property of the supplied problem, never a property read
    by request generation.
    """
    facts = problem.get("facts")
    rules = problem.get("rules")
    goal = problem.get("goal")
    if (not isinstance(facts, list) or not all(_text(fact) for fact in facts)
            or len(facts) != len(set(facts)) or not isinstance(rules, list) or not _text(goal)):
        raise ValueError("invalid proof problem")
    by_conclusion: dict[str, list[dict]] = {}
    rule_ids = set()
    for rule in rules:
        if (not isinstance(rule, dict) or set(rule) != {"id", "premises", "conclusion"}
                or not _text(rule["id"]) or rule["id"] in rule_ids
                or not isinstance(rule["premises"], list) or not all(_text(atom) for atom in rule["premises"])
                or not _text(rule["conclusion"])):
            raise ValueError("invalid proof rule")
        rule_ids.add(rule["id"])
        by_conclusion.setdefault(rule["conclusion"], []).append(rule)
    colors: dict[str, int] = {}

    def acyclic(atom: str) -> None:
        color = colors.get(atom, 0)
        if color == 1:
            raise ValueError("cyclic input problem")
        if color == 2:
            return
        colors[atom] = 1
        for rule in by_conclusion.get(atom, []):
            for premise in rule["premises"]:
                acyclic(premise)
        colors[atom] = 2

    for atom in set(by_conclusion) | set(facts):
        acyclic(atom)
    memo: dict[str, set[int]] = {}

    def depths(atom: str) -> set[int]:
        if atom not in memo:
            values = {0} if atom in facts else set()
            for rule in by_conclusion.get(atom, []):
                parent_sets = [depths(premise) for premise in rule["premises"]]
                for parent_depths in product(*parent_sets):
                    values.add(1 + max(parent_depths, default=-1))
            memo[atom] = values
        return memo[atom]

    values = depths(goal)
    if not values:
        raise ValueError("unreachable input goal")
    return [min(values), max(values)]


def assess(problem: dict, payload) -> dict:
    """Assess every emitted node; no pruning or proof repair is performed."""
    if not _schema_valid(payload):
        return _result(format_valid=False, proof_valid=None, strict_valid=None, actual_D=None,
                       final_rule_id=None, error_codes=["schema_invalid"])
    errors: list[str] = []
    nodes: dict[str, dict] = {}
    for node in payload["nodes"]:
        if node["id"] in nodes:
            errors.append("duplicate_id")
        else:
            nodes[node["id"]] = node
    rules = {rule["id"]: rule for rule in problem.get("rules", []) if isinstance(rule, dict) and isinstance(rule.get("id"), str)}
    facts = set(problem.get("facts", []))
    final = nodes.get(payload["final_node_id"])
    final_rule_id = None if final is None else final["rule"]
    if final is None:
        errors.append("missing_final_node")
    elif final["atom"] != problem.get("goal"):
        errors.append("final_goal_mismatch")
    for node in nodes.values():
        parents = node["parents"]
        if len(parents) != len(set(parents)):
            errors.append("duplicate_parent")
        missing = [parent for parent in parents if parent not in nodes]
        if missing:
            errors.append("missing_parent")
        rule_id = node["rule"]
        if rule_id is None:
            if parents:
                errors.append("fact_with_parents")
            if node["atom"] not in facts:
                errors.append("unreachable_fact")
            continue
        rule = rules.get(rule_id)
        if rule is None:
            errors.append("unregistered_rule")
            continue
        if node["atom"] != rule.get("conclusion"):
            errors.append("wrong_atom")
        if not missing and Counter(nodes[parent]["atom"] for parent in parents) != Counter(rule.get("premises", [])):
            errors.append("premise_counter_mismatch")
    if _cycle(nodes):
        errors.append("cycle")
    proof_valid = not errors
    if not proof_valid:
        return _result(format_valid=True, proof_valid=False, strict_valid=False, actual_D=None,
                       final_rule_id=final_rule_id, error_codes=errors)
    strict_errors: list[str] = []
    if _ancestors(nodes, payload["final_node_id"]) != set(nodes):
        strict_errors.append("extra_unused_node")
    if not _topological_order(payload["nodes"]):
        strict_errors.append("non_topological_order")
    if strict_errors:
        return _result(format_valid=True, proof_valid=True, strict_valid=False, actual_D=None,
                       final_rule_id=final_rule_id, error_codes=strict_errors)
    return _result(format_valid=True, proof_valid=True, strict_valid=True,
                   actual_D=_depth(nodes, payload["final_node_id"]), final_rule_id=final_rule_id,
                   error_codes=[])


def parse_response(raw, http_status, error, model):
    """Parse an Ollama-like envelope without assigning semantic validity.

    The runner supplies transport and identity observations; schema validation is
    deliberately deferred to :func:`assess`.
    """
    if http_status is None or not 200 <= http_status < 300:
        return ("transport_error" if http_status is None else "http_error", None)
    if error is not None:
        return ("transport_error", None)
    if model is None:
        return ("identity_error", None)
    if not isinstance(raw, dict):
        return ("invalid_json", None)
    if raw.get("model") != model:
        return ("identity_error", None)
    if raw.get("done") is not True or raw.get("done_reason") != "stop":
        return ("incomplete_response", None)
    message = raw.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant" or message.get("tool_calls"):
        return ("invalid_schema", None)
    content = message.get("content")
    if not isinstance(content, str):
        return ("invalid_schema", None)
    try:
        payload = common.load(content)
    except (UnicodeError, ValueError):
        return ("invalid_json", None)
    return ("ok", payload)
