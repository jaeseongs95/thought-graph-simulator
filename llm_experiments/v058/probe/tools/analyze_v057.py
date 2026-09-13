"""Recompute v057 observations directly from ZIP requests/responses (stdlib only)."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import itertools
import json
import math
from pathlib import Path
import zipfile


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse(data):
    def finite(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("non-finite float")
        return result
    return json.loads(data, object_pairs_hook=_pairs,
                      parse_float=finite,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def depth_options(problem):
    """Enumerate acyclic supports from facts; never infer depth from output length."""
    rules = problem["rules"]
    facts = set(problem["facts"])

    def depths(atom, active):
        if atom in active:
            return set()
        result = {0} if atom in facts else set()
        for rule in rules:
            if rule["conclusion"] != atom:
                continue
            parents = [depths(p, active | {atom}) for p in rule["premises"]]
            for values in itertools.product(*parents):
                result.add(1 + max(values, default=0))
        return result

    terminals = {}
    for rule in rules:
        if rule["conclusion"] == problem["goal"]:
            parents = [depths(p, {problem["goal"]}) for p in rule["premises"]]
            terminals[rule["id"]] = {1 + max(values, default=0)
                                    for values in itertools.product(*parents)}
    return depths(problem["goal"], set()), terminals


def graph_diagnostics(problem, payload):
    errors = set()
    if not isinstance(payload, dict) or set(payload) != {"nodes", "final_node_id"}:
        return {"errors": ["graph_schema"], "actual_depth": None, "final_rule_id": None}
    nodes = payload["nodes"]
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 16 or not isinstance(payload["final_node_id"], str):
        return {"errors": ["graph_schema"], "actual_depth": None, "final_rule_id": None}
    rules = {r["id"]: r for r in problem["rules"]}
    seen, depths = {}, {}
    for node in nodes:
        if (not isinstance(node, dict) or set(node) != {"id", "atom", "rule", "parents"}
                or not all(isinstance(node.get(k), str) and 1 <= len(node[k]) <= 128 for k in ["id", "atom"])
                or not (node["rule"] is None or isinstance(node["rule"], str) and 1 <= len(node["rule"]) <= 128)
                or not isinstance(node["parents"], list) or len(node["parents"]) > 16
                or not all(isinstance(p, str) and 1 <= len(p) <= 128 for p in node["parents"])):
            errors.add("graph_schema")
            continue
        nid, atom, rid, parents = (node[k] for k in ["id", "atom", "rule", "parents"])
        if nid in seen:
            errors.add("duplicate_node_id")
        if len(set(parents)) != len(parents):
            errors.add("duplicate_parent")
        if rid is None:
            if atom not in problem["facts"]:
                errors.add("unsupported_fact")
            if parents:
                errors.add("fact_has_parents")
            depths[nid] = 0
        else:
            rule = rules.get(rid)
            if rule is None:
                errors.add("unknown_rule")
            if any(p not in seen for p in parents):
                errors.add("missing_or_forward_parent")
            if rule and atom != rule["conclusion"]:
                errors.add("wrong_conclusion")
            if rule and Counter(seen[p]["atom"] for p in parents if p in seen) != Counter(rule["premises"]):
                errors.add("premise_mismatch")
            if all(p in depths for p in parents):
                depths[nid] = 1 + max((depths[p] for p in parents), default=0)
        seen[nid] = node
    final_id = payload["final_node_id"]
    final = seen.get(final_id)
    if final is None:
        errors.add("final_missing")
    else:
        if final["atom"] != problem["goal"]:
            errors.add("wrong_goal")
        ancestors, stack = set(), [final_id]
        while stack:
            node_id = stack.pop()
            if node_id in ancestors:
                continue
            ancestors.add(node_id)
            if node_id in seen:
                stack.extend(seen[node_id]["parents"])
        if set(seen) - ancestors:
            errors.add("extraneous_nodes")
    return {"errors": sorted(errors), "actual_depth": depths.get(final_id) if not errors else None,
            "final_rule_id": final["rule"] if final else None}


def analyze(path):
    rows = []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("duplicate archive member")

        def read(name):
            if archive.getinfo(name).file_size > 32 * 1024 * 1024:
                raise ValueError("oversized member")
            return parse(archive.read(name))

        plan = read("external_plan/v057.plan.json")
        slots = {s["id"]: s for s in plan["slots"]}
        if len(slots) != len(plan["slots"]):
            raise ValueError("duplicate plan slot")
        actions = {a["id"]: a["index"] for a in plan["actions"] if a["kind"] == "call"}
        expected = {f"run/calls/{cid}/{file}" for cid in slots
                    for file in ["request.wire.json", "response.raw.json"]}
        observed = {n for n in names if n.startswith("run/calls/") and not n.endswith("/")}
        if expected != observed:
            raise ValueError("missing or unexpected call artifacts")
        for cid, slot in slots.items():
            request = read(f"run/calls/{cid}/request.wire.json")
            response = read(f"run/calls/{cid}/response.raw.json")
            problem = parse(request["messages"][0]["content"].split("problem: ", 1)[1])
            possible, terminals = depth_options(problem)
            if not possible or any(len(d) != 1 for d in terminals.values()):
                raise ValueError("terminal-depth ambiguity")
            try:
                payload = parse(response["message"]["content"])
                parse_error = None
            except (ValueError, KeyError, TypeError):
                payload, parse_error = None, "payload_parse"
            task = slot["mode"]
            actual, implied, final_rule = None, None, None
            if parse_error:
                errors = [parse_error]
            elif task == "graph":
                result = graph_diagnostics(problem, payload)
                errors, actual, final_rule = result["errors"], result["actual_depth"], result["final_rule_id"]
            else:
                errors = []
                if not isinstance(payload, dict) or set(payload) != {"final_rule_id"} or not isinstance(payload["final_rule_id"], str):
                    errors.append("choice_schema")
                else:
                    final_rule = payload["final_rule_id"]
                    if final_rule not in terminals:
                        errors.append("invalid_choice")
                    else:
                        implied = next(iter(terminals[final_rule]))
            direction = slot["direction"]
            target = min(possible) if direction == "shallow" else max(possible) if direction == "deep" else None
            measured = actual if task == "graph" else implied
            counterpart = cid.replace(task + "__", ("choice" if task == "graph" else "graph") + "__", 1)
            rows.append({"call_id": cid, "model": slot["model_key"], "task": task,
                         "problem": problem["id"], "order": slot["arm"], "direction": direction,
                         "seed_index": slot["seed_index"], "seed": request["options"]["seed"],
                         "block": slot["block"], "action_index": actions[cid],
                         "choice_first": actions[cid if task == "choice" else counterpart] < actions[counterpart if task == "choice" else cid],
                         "errors": errors, "task_valid": not errors, "actual_depth": actual,
                         "implied_depth": implied, "final_rule_id": final_rule,
                         "first_goal_rule": next(iter(terminals)),
                         "first_goal_selected": final_rule == next(iter(terminals)),
                         "direction_pass": measured == target and not errors if target is not None else None,
                         "done": response.get("done"), "done_reason": response.get("done_reason"),
                         "prompt_eval_cached_count": response.get("prompt_eval_cached_count")})
    groups, cells, schedule_cells = [], [], []
    for model, task in itertools.product(["reference", "candidate"], ["graph", "choice"]):
        subset = [r for r in rows if (r["model"], r["task"]) == (model, task)]
        pairs = []
        for problem, order, seed in itertools.product(["K01", "T02"], ["original", "swapped"], range(10)):
            directed = [r for r in subset if (r["problem"], r["order"], r["seed_index"]) == (problem, order, seed) and r["direction"] != "neutral"]
            if len(directed) != 2:
                raise ValueError("incomplete direction pair")
            if all(r["direction_pass"] for r in directed):
                pairs.append([problem, order, seed])
        robust = [[problem, seed] for problem, seed in itertools.product(["K01", "T02"], range(10))
                  if all([problem, order, seed] in pairs for order in ["original", "swapped"])]
        groups.append({"model": model, "task": task, "observed": len(subset),
                       "valid": sum(r["task_valid"] for r in subset),
                       "directed_pass": sum(r["direction_pass"] is True for r in subset),
                       "first_goal_selected": sum(r["first_goal_selected"] for r in subset),
                       "directed_first_goal_selected": sum(r["first_goal_selected"] for r in subset if r["direction"] != "neutral"),
                       "errors_overlapping": dict(Counter(e for r in subset for e in r["errors"])),
                       "selective_pairs": pairs, "both_order_pairs": robust})
        for problem, order, direction in itertools.product(["K01", "T02"], ["original", "swapped"], ["shallow", "deep", "neutral"]):
            cell = [r for r in subset if (r["problem"], r["order"], r["direction"]) == (problem, order, direction)]
            base = {"model": model, "task": task, "problem": problem, "order": order, "direction": direction}
            cells.append({**base, "observed": len(cell), "valid": sum(r["task_valid"] for r in cell),
                          "actual_depths": dict(Counter(str(r["actual_depth"]) for r in cell)),
                          "implied_depths": dict(Counter(str(r["implied_depth"]) for r in cell)),
                          "final_rules": dict(Counter(str(r["final_rule_id"]) for r in cell)),
                          "successful_seed_indices": [r["seed_index"] for r in cell if r["direction_pass"]]})
            for first in [False, True]:
                part = [r for r in cell if r["choice_first"] == first]
                schedule_cells.append({**base, "choice_first": first, "observed": len(part),
                                       "pass": sum(r["direction_pass"] is True for r in part) if direction != "neutral" else None,
                                       "seed_indices": [r["seed_index"] for r in part],
                                       "cached_counts": [r["prompt_eval_cached_count"] for r in part]})
    return {"contract": "v057-independent-descriptive-analysis-r1",
            "evidence_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "observed_calls": len(rows), "groups": groups, "cells": cells,
            "schedule_cells": schedule_cells, "rows": rows,
            "limits": ["Descriptive fixed-problem repeats; seeds are not new problem samples.",
                       "Seed index, execution order and prior request/cache state are confounded.",
                       "Choice implied depth is not generated proof depth.",
                       "Semantic diagnostic recomputation is not a complete evidence-integrity audit."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = analyze(args.evidence)
    with args.out.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


if __name__ == "__main__":
    main()
