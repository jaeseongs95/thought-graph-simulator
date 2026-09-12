"""기존 v045/v046 요청을 보존하고 결과를 보기 전에 실행 순서를 동결한다."""
from __future__ import annotations
import copy
import itertools
import random
from pathlib import Path
from . import __version__
from .contracts import (ContractError, EXPRS, SCHEMA, SYSTEM, b64, canonical, digest,
                        read_json, require, sha, source_fingerprint, strict_json,
                        unb64, utc_now, wire, write_json)

ARMS = ("original", "commuted", "pipeline")
CONTRACT = "paired-boolean-v047-r1"


def input_key(a: bool, b: bool) -> str:
    require(type(a) is bool and type(b) is bool, "bool 입력 필요")
    return str(int(a)) + str(int(b))


def _check_body(raw: bytes, case: dict, config: dict, contract: str) -> tuple[str, dict]:
    body = strict_json(raw)
    require(isinstance(body, dict) and wire(body) == raw, "v045/v046 HTTP wire 직렬화 불일치")
    mandatory = {"model", "messages", "stream", "keep_alive", "options", "format"}
    require(set(body) in (mandatory, mandatory | {"think"}), "지원하지 않는 요청 필드/format")
    require(body["model"] == config["model"] and body["stream"] is False and body["keep_alive"] == "10m",
            "모델/stream/keep_alive 계약 변경")
    require(canonical(body["format"]) == canonical(SCHEMA), "타입 전용 bool 스키마가 아닙니다.")
    require(type(case["seed"]) is int and case["seed"] >= 0, "원본 seed 오류")
    require(canonical(body["options"]) == canonical(dict(config["options"], seed=case["seed"])),
            "원본 config와 요청 options 불일치")
    require(body.get("think") == config.get("think") and (body.get("think") is None or body.get("think") is False),
            "non-thinking 요청 계약 불일치")
    require(config.get("mode_policy", {}).get("resolved_mode") == "non-thinking", "원본 non-thinking 확인 필요")
    messages = body["messages"]
    require(isinstance(messages, list) and len(messages) == 2 and
            messages[0] == {"role": "system", "content": SYSTEM}, "기존 operator system 문구와 다릅니다.")
    require(set(messages[1]) == {"role", "content"} and messages[1]["role"] == "user" and
            messages[1]["content"].startswith("input: "), "원본 user 메시지 오류")
    values = strict_json(messages[1]["content"][7:])
    require(isinstance(values, dict) and list(values) == ["a", "b", "expression"] and
            type(values["a"]) is bool and type(values["b"]) is bool, "원본 입력/키 순서 오류")
    require(values["expression"] in (EXPRS["original"], EXPRS["commuted"]), "직접식/교환식 요청 필요")
    original = case.get("original_input") if contract == "composition-v046" else case.get("input_literals")
    require(canonical(original) == canonical({"a": values["a"], "b": values["b"]}), "manifest 입력과 원문 불일치")
    if contract == "composition-v046":
        require(case.get("arm") == "commuted" and values["expression"] == EXPRS["commuted"],
                "v046 교환식 기록이 아닙니다.")
    else:
        require(case.get("operation") == "and_not_b" and values["expression"] == EXPRS["original"],
                "v045 직접식 기록이 아닙니다.")
    return input_key(values["a"], values["b"]), body


def validate_baseline(baseline: dict) -> None:
    mf_raw = unb64(baseline["manifest_b64"])
    require(sha(mf_raw) == baseline["manifest_sha256"], "원본 manifest 바이트 해시 불일치")
    mf = strict_json(mf_raw); frozen = mf["frozen"]
    require(mf["run_sha256"] == digest(frozen), "원본 run_sha256 불일치")
    contract = frozen["plan"].get("probe_contract")
    require(baseline["evidence_kind"] == frozen.get("evidence_kind", "live_source_artifacts") and
            baseline["evidence_kind"] in ("live_source_artifacts", "synthetic_fixture"), "합성/실제 원문 출처 라벨 변경")
    require(contract in ("operator-v045", "composition-v046"), "v045/v046 manifest가 아닙니다.")
    require(baseline["config"] == frozen["config"] and baseline["model"] == frozen["model"] and
            baseline["server"] == frozen["ollama_server"], "baseline identity 변경")
    require(isinstance(baseline["model"].get("digest"), str) and
            isinstance(baseline["model"].get("show_sha256"), str), "모델 digest/show_sha256 필요")
    cases = {c["case_id"]: c for c in frozen["plan"]["cases"]}
    require(set(baseline["templates"]) == {"00", "01", "10", "11"}, "네 입력 원문이 모두 필요합니다.")
    signatures = set(); seeds = set()
    for key, entry in baseline["templates"].items():
        raw = unb64(entry["request_b64"])
        require(sha(raw) == entry["request_sha256"], "원본 요청 해시 불일치")
        require(entry["case_id"] in cases, "원본 case ID 누락")
        actual_key, body = _check_body(raw, cases[entry["case_id"]], baseline["config"], contract)
        require(actual_key == key, "입력 키 불일치")
        seeds.add(body["options"]["seed"])
        body["messages"][1]["content"] = "input: <AB_EXPRESSION>"
        signatures.add(sha(wire(body)))
    require(len(signatures) == 1 and len(seeds) == 1, "네 원문 사이의 비입력 설정이 다릅니다.")
    require(baseline["seed"] == next(iter(seeds)), "baseline seed 변경")


def extract_run(run_dir: Path) -> dict:
    mf_path = run_dir / "manifest.json"
    raw = mf_path.read_bytes(); mf = strict_json(raw); frozen = mf["frozen"]
    contract = frozen["plan"].get("probe_contract")
    require(contract in ("operator-v045", "composition-v046"), "대상 계약 아님")
    templates = {}; seeds = set()
    for case in frozen["plan"]["cases"]:
        chosen = ((contract == "operator-v045" and case.get("operation") == "and_not_b") or
                  (contract == "composition-v046" and case.get("arm") == "commuted"))
        if not chosen:
            continue
        case_id = case["case_id"]
        require(isinstance(case_id, str) and case_id and all(c.isalnum() or c in "_-" for c in case_id),
                "안전하지 않은 원본 case ID")
        path = run_dir / "cases" / case_id / "request.wire.json"
        request_raw = path.read_bytes()
        key, body = _check_body(request_raw, case, frozen["config"], contract)
        require(key not in templates, "동일 입력의 중복 원문이 있습니다. 하나의 실행 폴더를 선택하세요.")
        templates[key] = {"case_id": case_id, "request_b64": b64(request_raw),
                          "request_sha256": sha(request_raw), "source_path": str(path.resolve())}
        seeds.add(body["options"]["seed"])
    require(len(seeds) == 1, "원본 공통 seed를 찾지 못했습니다.")
    baseline = {"source_dir": str(run_dir.resolve()), "source_contract": contract,
                "manifest_b64": b64(raw), "manifest_sha256": sha(raw),
                "config": frozen["config"], "model": frozen["model"], "server": frozen["ollama_server"],
                "seed": next(iter(seeds)), "templates": templates,
                "evidence_kind": frozen.get("evidence_kind", "live_source_artifacts"),
                "scope": "원본 요청·설정 수입. 과거 PASS/응답의 재감사 또는 새 추론을 의미하지 않음"}
    validate_baseline(baseline)
    return baseline


def discover(source_root: Path, source_run: Path | None = None) -> tuple[dict, list[dict]]:
    if source_run is not None:
        return extract_run(source_run), []
    require(source_root.is_dir(), "원본 결과 폴더가 없습니다: " + str(source_root))
    candidates = []
    for path in source_root.rglob("manifest.json"):
        try:
            mf = read_json(path)
            contract = mf.get("frozen", {}).get("plan", {}).get("probe_contract")
            if contract in ("operator-v045", "composition-v046"):
                candidates.append((2 if contract == "composition-v046" else 1,
                                   path.stat().st_mtime_ns, str(path), path.parent))
        except (ContractError, OSError, AttributeError):
            continue
    candidates.sort(reverse=True); skipped = []
    for _, _, _, path in candidates:
        try:
            return extract_run(path), skipped
        except (ContractError, KeyError, TypeError, OSError) as exc:
            skipped.append({"source_dir": str(path), "reason": str(exc)})
    detail = "; ".join(x["source_dir"] + ": " + x["reason"] for x in skipped[:5])
    raise ContractError("네 입력의 schema형 v045/v046 원문을 찾지 못했습니다. "
                        "--source-root 또는 --source-run에 실제 결과 폴더를 지정하세요. " + detail)


def make_schedule(seeds: list[int], cycles: int, order_seed: int) -> list[dict]:
    permutations = list(itertools.permutations(ARMS))
    rng = random.Random(order_seed)
    offsets = {key: rng.randrange(6) for key in ("00", "01", "10", "11")}
    blocks = []
    for seed_index, seed in enumerate(seeds):
        for cycle in range(cycles):
            inputs = [(False, False), (False, True), (True, False), (True, True)]
            rng.shuffle(inputs)
            for a, b in inputs:
                key = input_key(a, b)
                order = permutations[(seed_index * cycles + cycle + offsets[key]) % 6]
                block_id = f"s{seed_index:03d}_r{cycle:03d}_ab{key}"
                blocks.append({"id": block_id, "seed": seed, "seed_index": seed_index,
                               "cycle": cycle, "a": a, "b": b, "arms": list(order)})
    return blocks


def slots(plan: dict) -> list[dict]:
    result = []
    for block in plan["blocks"]:
        for position, arm in enumerate(block["arms"]):
            for stage in (("not", "and") if arm == "pipeline" else (arm,)):
                result.append({"id": block["id"] + "__" + stage, "block_id": block["id"],
                               "arm": arm, "stage": stage, "position": position,
                               "seed": block["seed"], "seed_index": block["seed_index"],
                               "cycle": block["cycle"], "a": block["a"], "b": block["b"]})
    return result


def make_request(plan: dict, slot: dict, parent_value: bool | None = None) -> bytes:
    raw = unb64(plan["baseline"]["templates"][input_key(slot["a"], slot["b"])]["request_b64"])
    body = strict_json(raw)
    data = strict_json(body["messages"][1]["content"][7:])
    data["expression"] = EXPRS[slot["stage"]]
    if slot["stage"] == "and":
        require(type(parent_value) is bool, "실제 부모 bool 없이는 AND를 요청하지 않습니다.")
        data["b"] = parent_value
    body["messages"][1]["content"] = "input: " + wire(data).decode("utf-8")
    body["options"]["seed"] = slot["seed"]
    return wire(body)


def prepare(source_root: Path, out: Path, *, source_run: Path | None = None,
            seeds: list[int] | None = None, cycles: int = 6, order_seed: int = 4701729) -> dict:
    require(not out.exists(), "기존 계획을 덮어쓰지 않습니다: " + str(out))
    baseline, skipped = discover(source_root, source_run)
    seeds = list(seeds) if seeds is not None else [baseline["seed"]]
    require(bool(seeds) and len(set(seeds)) == len(seeds) and
            all(type(s) is int and 0 <= s <= 2147483647 for s in seeds), "유효한 서로 다른 seed 필요")
    require(type(cycles) is int and 1 <= cycles <= 100 and len(seeds) * cycles * 16 <= 10000,
            "cycles/최대 호출 수 범위 초과")
    require(type(order_seed) is int and 0 <= order_seed <= 2147483647, "order_seed 오류")
    plan = {"contract": CONTRACT, "software_version": __version__, "created_at": utc_now(),
            "baseline": baseline, "skipped_sources": skipped, "source_fingerprint": source_fingerprint(),
            "seeds": seeds, "cycles": cycles, "order_seed": order_seed,
            "blocks": make_schedule(seeds, cycles, order_seed),
            "max_calls": len(seeds) * cycles * 16,
            "analysis_policy": {"model_correctness_is_not_data_integrity": True,
                "invalid_counts_as_failure": True, "no_retry": True, "no_answer_correction": True,
                "primary_final_pairs": ["commuted-original", "pipeline-original"],
                "pipeline_primary_strict": "NOT와 AND의 실제 값·연결·최종값 모두 정확",
                "scope": "고정 1개 식·4개 입력의 동일 배치 재현. ADM 본 가설 검증 아님",
                "statistics": "paired counts and per-seed descriptive results; no IID p-values"}}
    plan["plan_sha256"] = digest(plan)
    validate_plan(plan)
    write_json(out, plan, exclusive=True)
    return plan


def validate_plan(plan: dict, *, check_sources: bool = True) -> None:
    require(plan.get("contract") == CONTRACT, "계획 계약 불일치")
    material = {k: v for k, v in plan.items() if k != "plan_sha256"}
    require(plan.get("plan_sha256") == digest(material), "동결 계획 해시 불일치")
    validate_baseline(plan["baseline"])
    require(isinstance(plan["seeds"], list) and bool(plan["seeds"]) and
            all(type(s) is int and 0 <= s <= 2147483647 for s in plan["seeds"]) and
            len(set(plan["seeds"])) == len(plan["seeds"]), "계획 seed 범위/중복 오류")
    require(type(plan["cycles"]) is int and 1 <= plan["cycles"] <= 100 and
            type(plan["order_seed"]) is int and 0 <= plan["order_seed"] <= 2147483647,
            "계획 반복/순서 seed 범위 오류")
    require(type(plan["max_calls"]) is int and 0 < plan["max_calls"] <= 10000, "계획 호출 한도 오류")
    require(plan["blocks"] == make_schedule(plan["seeds"], plan["cycles"], plan["order_seed"]),
            "계획된 균형 순서/입력 누락·변경")
    require(plan["max_calls"] == len(slots(plan)) and plan["max_calls"] <= 10000, "계획 호출 수 오류")
    if check_sources:
        require(plan["source_fingerprint"] == source_fingerprint(), "계획 동결 후 실행/평가 소스가 변경됐습니다.")
