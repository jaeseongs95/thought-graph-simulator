"""감사된 v047을 읽고 결과를 보기 전에 seed·순서·판정 규칙을 동결한다."""
from __future__ import annotations
import copy
import itertools
from pathlib import Path
from . import __version__
from .contracts import (ContractError, EXPRS, b64, canonical, digest, read_json,
                        require, require_external_plan, sha, source_fingerprint, strict_json, unb64,
                        utc_now, wire, write_json)
from paired_probe_v047.plan import validate_baseline, validate_plan as validate_legacy_plan

ARMS = ("original", "commuted", "pipeline")
CONTRACT = "seed-boolean-v048-r1"
SEED_DOMAIN = "thought-graph-simulator/v048/seed-expansion/2026-09-11"
ORDER_SEED = 4801729
DEFAULT_SEED_COUNT = 10
MAX_CALLS = 10000
POLICY = {
    "scope": "고정 1개 식·4개 입력에서 발견 seed를 제외한 생성 seed 대조. 표현 일반화·ADM 조작은 수행하지 않음",
    "primary_pair": "commuted-original",
    "secondary_pairs": ["pipeline-original", "pipeline-commuted"],
    "primary_measure": "각 seed의 4입력×6순서 최종값 정확도 차이",
    "additional_measures": ["양성 조건", "전체 진리표 반복", "중간값 포함 파이프라인", "실측 자원"],
    "statistics": "seed별 기술통계. 요청·입력·순서 반복에 IID p-value 또는 문제 일반화 신뢰구간을 부여하지 않음",
    "invalid_response": "모델 형식 오류는 배정 분모에 포함한 실패. 부모 bool 없으면 AND만 blocked",
    "missing_execution": "수집 미완료 시 완결 비교값은 null. 미실행을 모델 오답으로 표시하지 않음",
    "model_identity_mismatch": "다른 응답 모델은 추론 기반시설 오류로 중단",
    "no_retry": True, "no_answer_correction": True, "warmup_calls": 0,
    "discovery_seed_in_new_sample": False, "posthoc_selection": False,
    "timing": "전 호출 포함; 로딩·캐시 별도 보고; 파이프라인은 실제 두 호출 합산; 동일 FLOPs로 해석하지 않음",
    "schedule": "round별 모든 seed·입력을 섞고, 각 seed·입력은 6회에 여섯 경로 순열을 모두 사용",
    "runtime_checks": "추론 전·round 경계·추론 후 모델/서버 식별 확인",
}


def input_key(a: bool, b: bool) -> str:
    require(type(a) is bool and type(b) is bool, "bool 입력 필요")
    return str(int(a)) + str(int(b))


def default_seeds(excluded: list[int], count: int = DEFAULT_SEED_COUNT) -> list[int]:
    """응답을 참조하지 않는 공개 문자열 SHA-256 결정 절차. 발견 seed는 제외한다."""
    result = []
    index = 0
    while len(result) < count:
        candidate = int(sha(f"{SEED_DOMAIN}/{index}".encode()), 16) % 2147483647 + 1
        index += 1
        if candidate not in excluded and candidate not in result:
            result.append(candidate)
    return result


def _rank(order_seed: int, *parts) -> str:
    return digest([order_seed, *parts])


def make_schedule(seeds: list[int], cycles: int, order_seed: int) -> list[dict]:
    """프롬프트/seed는 유지하고 배치 순서만 사전 균형화한다. Python PRNG 버전에 의존하지 않는다."""
    permutations = list(itertools.permutations(ARMS))
    blocks = []
    for cycle in range(cycles):
        wave = []
        for seed_index, seed in enumerate(seeds):
            for a, b in ((False, False), (False, True), (True, False), (True, True)):
                key = input_key(a, b)
                perm_order = sorted(permutations,
                    key=lambda perm: _rank(order_seed, "permutations", seed, key, cycle // 6, perm))
                wave.append({"id": f"s{seed_index:03d}_r{cycle:03d}_ab{key}",
                    "seed": seed, "seed_index": seed_index, "cycle": cycle,
                    "a": a, "b": b, "arms": list(perm_order[cycle % 6])})
        wave.sort(key=lambda block: _rank(order_seed, "wave", cycle, block["seed"], block["a"], block["b"]))
        blocks.extend(wave)
    return blocks


def slots(plan: dict) -> list[dict]:
    result = []
    for block in plan["blocks"]:
        for position, arm in enumerate(block["arms"]):
            for stage in (("not", "and") if arm == "pipeline" else (arm,)):
                result.append({"id": block["id"] + "__" + stage, "block_id": block["id"],
                    "arm": arm, "stage": stage, "position": position, "seed": block["seed"],
                    "seed_index": block["seed_index"], "cycle": block["cycle"],
                    "a": block["a"], "b": block["b"]})
    return result


def make_request(plan: dict, slot: dict, parent_value: bool | None = None) -> bytes:
    """원문 템플릿에서 seed·식·실제 부모값만 바꾼다. 정답 계산기는 호출하지 않는다."""
    body = strict_json(unb64(plan["baseline"]["templates"][input_key(slot["a"], slot["b"])]["request_b64"]))
    values = strict_json(body["messages"][1]["content"][7:])
    values["expression"] = EXPRS[slot["stage"]]
    if slot["stage"] == "and":
        require(type(parent_value) is bool, "실제 부모 bool 없이는 AND 호출 금지")
        values["b"] = parent_value
    body["messages"][1]["content"] = "input: " + wire(values).decode("utf-8")
    body["options"]["seed"] = slot["seed"]
    return wire(body)


def _inventory(run: Path) -> dict[str, str]:
    """파생 summary를 제외한 입력 증거의 바이트 목록. 원문은 변경하지 않는다."""
    names = {"plan.snapshot.json", "run_manifest.json", "status.json", "events.jsonl",
             "runtime.before.json", "runtime.after.json"}
    paths = [run / name for name in sorted(names)]
    paths += sorted((run / "calls").rglob("*.json"))
    paths += sorted((run / "source_snapshot").glob("*.py"))
    return {path.relative_to(run).as_posix(): sha(path.read_bytes()) for path in paths}


def import_reference(run: Path, external_plan: Path | None, *, accept_snapshot: bool) -> tuple[dict, dict]:
    require(run.is_dir(), "v047 실행 폴더가 없습니다: " + str(run))
    require((external_plan is not None) != accept_snapshot,
            "--baseline-plan 외부 동결 계획 또는 --accept-snapshot 중 하나를 지정하세요.")
    path = run / "plan.snapshot.json" if accept_snapshot else external_plan
    assert path is not None
    require(accept_snapshot or path.resolve() != (run / "plan.snapshot.json").resolve(),
            "동일한 snapshot을 외부 동결 계획으로 표시할 수 없습니다. --accept-snapshot을 명시하세요.")
    if not accept_snapshot:
        require_external_plan(path, run)
    before_inventory = _inventory(run)
    raw = path.read_bytes()
    legacy = strict_json(raw)
    validate_legacy_plan(legacy)
    # 기존 성공 점수를 믿지 않는다. 배포한 고정 v047 감사기로 원문을 재계산한다.
    from paired_probe_v047.audit import audit_run as audit_legacy_run
    report = audit_legacy_run(path, run, write_report=False)
    require(report["data_integrity"] and report["data_complete"] and report["comparative_analysis_ready"],
            "완결·비교 가능한 v047 원문만 기준선으로 수입합니다. 모델 정답률은 선택 기준이 아닙니다.")
    after_inventory = _inventory(run)
    require(before_inventory == after_inventory and path.read_bytes() == raw,
            "기준선 수입 중 원문/계획 파일이 변경됐습니다. 불안정한 기준선은 수입하지 않습니다.")
    reference = {
        "contract": "audited-v047-reference-r1", "source_run": str(run.resolve()),
        "source_plan": str(path.resolve()), "anchor": "snapshot_only" if accept_snapshot else "external_plan",
        "plan_b64": b64(raw), "plan_bytes_sha256": sha(raw), "plan_sha256": legacy["plan_sha256"],
        "event_tip": report["event_tip"], "discovery_seeds": legacy["seeds"],
        "recorded_inference_calls": report["inference_calls"],
        "evidence_kind": report["evidence_kind"], "audited_at": utc_now(),
        "artifact_hashes": after_inventory,
        "reference_only_scores": {arm: {key: report["arms"][arm][key] for key in
            ("assigned", "final_correct", "positive_correct", "strict_trace_correct")}
            for arm in ARMS},
        "scope": "prepare 시 v047 원문 재감사. v048 점수와 합산하지 않음. 해시는 외부 서버 실행의 전자서명이 아님",
    }
    reference["receipt_sha256"] = digest(reference)
    return copy.deepcopy(legacy["baseline"]), reference


def prepare(baseline_run: Path, out: Path, *, baseline_plan: Path | None = None,
            accept_snapshot: bool = False, seeds: list[int] | None = None,
            cycles: int = 6, order_seed: int = ORDER_SEED) -> dict:
    require(not out.exists(), "기존 계획은 덮어쓰지 않습니다: " + str(out))
    baseline, reference = import_reference(baseline_run, baseline_plan, accept_snapshot=accept_snapshot)
    chosen = list(seeds) if seeds is not None else default_seeds(reference["discovery_seeds"])
    require(isinstance(chosen, list) and bool(chosen) and
            all(type(s) is int and 0 <= s <= 2147483647 for s in chosen) and
            len(set(chosen)) == len(chosen), "seed는 범위 내의 서로 다른 정수여야 합니다.")
    require(not set(chosen).intersection(reference["discovery_seeds"]),
            "발견에 사용한 seed는 새 seed 표본에 포함하지 않습니다.")
    require(type(cycles) is int and 6 <= cycles <= 60 and cycles % 6 == 0 and
            len(chosen) * cycles * 16 <= MAX_CALLS, "cycles는 6의 배수, 호출 수는 10000 이하이어야 합니다.")
    require(type(order_seed) is int and 0 <= order_seed <= 2147483647, "order seed 범위 오류")
    plan = {
        "contract": CONTRACT, "software_version": __version__, "created_at": utc_now(),
        "baseline": baseline, "reference": reference, "source_fingerprint": source_fingerprint(),
        "seeds": chosen, "seed_selection": {"method": "explicit_before_run" if seeds is not None else "sha256_domain",
            "domain": None if seeds is not None else SEED_DOMAIN, "default_count": DEFAULT_SEED_COUNT,
            "excluded_discovery_seeds": reference["discovery_seeds"]},
        "cycles": cycles, "order_seed": order_seed,
        "blocks": make_schedule(chosen, cycles, order_seed), "max_calls": len(chosen) * cycles * 16,
        "analysis_policy": copy.deepcopy(POLICY),
    }
    plan["plan_sha256"] = digest(plan)
    validate_plan(plan)
    write_json(out, plan, exclusive=True)
    return plan


def validate_plan(plan: dict, *, check_sources: bool = True) -> None:
    expected_keys = {"contract", "software_version", "created_at", "baseline", "reference", "source_fingerprint",
        "seeds", "seed_selection", "cycles", "order_seed", "blocks", "max_calls", "analysis_policy", "plan_sha256"}
    require(isinstance(plan, dict) and set(plan) == expected_keys and plan["contract"] == CONTRACT,
            "v048 계획 필드/계약 불일치")
    require(plan["plan_sha256"] == digest({k: v for k, v in plan.items() if k != "plan_sha256"}), "동결 계획 해시 불일치")
    require(plan["software_version"] == __version__ and canonical(plan["analysis_policy"]) == canonical(POLICY),
            "실험/판정 정책은 수동 편집할 수 없습니다.")
    reference = plan["reference"]
    require(reference["contract"] == "audited-v047-reference-r1" and reference["anchor"] in ("external_plan", "snapshot_only"),
            "v047 참조 계약 오류")
    require(reference["receipt_sha256"] == digest({k: v for k, v in reference.items() if k != "receipt_sha256"}),
            "v047 참조 영수증 해시 불일치")
    raw = unb64(reference["plan_b64"])
    require(sha(raw) == reference["plan_bytes_sha256"], "v047 계획 원문 해시 불일치")
    legacy = strict_json(raw)
    validate_legacy_plan(legacy, check_sources=check_sources)
    require(legacy["plan_sha256"] == reference["plan_sha256"] and
            canonical(plan["baseline"]) == canonical(legacy["baseline"]), "수입한 v047 설정이 변경됐습니다.")
    require(reference["discovery_seeds"] == legacy["seeds"] and
            reference["evidence_kind"] == legacy["baseline"]["evidence_kind"], "발견 seed/출처 변경")
    validate_baseline(plan["baseline"])
    seeds = plan["seeds"]
    require(isinstance(seeds, list) and bool(seeds) and all(type(s) is int and 0 <= s <= 2147483647 for s in seeds)
            and len(set(seeds)) == len(seeds) and not set(seeds).intersection(reference["discovery_seeds"]),
            "seed 범위/중복/발견 seed 재사용 오류")
    selection = plan["seed_selection"]
    require(set(selection) == {"method", "domain", "default_count", "excluded_discovery_seeds"} and
            selection["excluded_discovery_seeds"] == reference["discovery_seeds"] and
            selection["default_count"] == DEFAULT_SEED_COUNT, "seed 선택 정책 오류")
    if selection["method"] == "sha256_domain":
        require(selection["domain"] == SEED_DOMAIN and seeds == default_seeds(reference["discovery_seeds"]),
                "기본 seed 생성 절차/목록 변경")
    else:
        require(selection["method"] == "explicit_before_run" and selection["domain"] is None, "알 수 없는 seed 선택법")
    require(type(plan["cycles"]) is int and 6 <= plan["cycles"] <= 60 and plan["cycles"] % 6 == 0 and
            type(plan["order_seed"]) is int and 0 <= plan["order_seed"] <= 2147483647, "반복/순서 seed 범위 오류")
    require(type(plan["max_calls"]) is int and 0 < plan["max_calls"] <= MAX_CALLS and
            plan["max_calls"] == len(seeds) * plan["cycles"] * 16, "호출 한도 오류")
    require(canonical(plan["blocks"]) == canonical(make_schedule(seeds, plan["cycles"], plan["order_seed"])),
            "사전 동결 seed·순서·입력 누락/변경")
    if check_sources:
        require(plan["source_fingerprint"] == source_fingerprint(), "계획 동결 후 실행/감사 소스가 변경됐습니다.")
