"""v048 전체 seed를 유지하는 표현 2×2 대조. 계획 생성은 오프라인이다."""
from __future__ import annotations
import copy
from pathlib import Path
from . import __version__
from .contracts import (EXPRS, b64, canonical, digest, read_json, require, sha,
                        source_fingerprint, strict_json, unb64, utc_now, wire, write_json)

ARMS = ("original", "commuted", "original_open", "commuted_open", "pipeline")
DIRECT = ARMS[:-1]
CONTRACT = "expression-factorial-v049-r1"
ORDER_SEED = 4901729
CYCLES = 2
POLICY = {
    "scope": "동일 a AND NOT b의 피연산자 순서×바깥 괄호 2×2 표현 대조. NOT b의 괄호는 유지",
    "seed_policy": "v048의 전체 10 seed 재사용. 성공/실패 seed 선택 금지. 새 seed 검증으로 세지 않음",
    "factors": {"operand_order": ["a-first", "not-b-first"], "outer_parentheses": [True, False]},
    "expressions": {arm: EXPRS[arm] for arm in DIRECT},
    "primary_contrasts": ["commuted-original", "commuted_open-original_open",
                           "original-original_open", "commuted-commuted_open"],
    "interaction": "(commuted-original)-(commuted_open-original_open)",
    "pipeline_comparators": list(DIRECT),
    "statistics": "seed별 기술통계; 동일 seed의 2회는 재현 확인. IID p-value·일반문제 신뢰구간 없음",
    "schedule": "각 입력·cycle의 10 seed에 5조건 위치·직전조건 균형인 10개 순서를 배정. cycle1은 cycle0의 역순",
    "order_limit": "균형은 seed 전체의 경로 위치·블록 내부 직전조건 기준. seed 하나의 모든 120순열 또는 HTTP위치 통제 아님",
    "cycles": CYCLES, "no_retry": True, "no_answer_correction": True, "warmup_calls": 0,
    "invalid_response": "모델 형식 오류는 실패; 부모 bool 없으면 AND만 blocked. 오답 bool은 그대로 전달",
    "missing_execution": "미실행은 오답이 아님. 미완료시 전체 비교차·상호작용은 null",
    "timing": "실패 포함 모든 실제 호출의 토큰·캐시·로딩·시간. 경로 요청시간은 두 HTTP시간의 합; FLOPs 아님",
    "model_identity_mismatch": "다른 모델 응답은 인프라 오류로 중단",
    "test_before_run": "외부 계획·실행 코드·기준선 식별 고정. 성공률은 기준선 선택 조건이 아님",
}

def input_key(a: bool, b: bool) -> str:
    require(type(a) is bool and type(b) is bool, "bool 입력 필요")
    return str(int(a)) + str(int(b))

def order_rows() -> list[list[str]]:
    """5조건에 대한 10개 균형순서. 합성시험에서 위치와 직전조건 빈도를 별도 계산한다."""
    base = [0, 1, 4, 2, 3]
    forward = [[ARMS[(i + shift) % 5] for i in base] for shift in range(5)]
    return forward + [list(reversed(row)) for row in forward]

def make_schedule(seeds: list[int], cycles: int, order_seed: int) -> list[dict]:
    require(len(seeds) == 10 and cycles == CYCLES, "등록 설계는 seed 10개·반복 2회입니다.")
    sequences = order_rows(); result = []
    for cycle in range(cycles):
        wave = []
        for a, b in ((False,False),(False,True),(True,False),(True,True)):
            key = input_key(a,b)
            ranked = sorted(seeds, key=lambda s: digest([order_seed,"assign",key,s]))
            for seed_index, seed in enumerate(seeds):
                arms = sequences[ranked.index(seed)]
                if cycle == 1: arms = list(reversed(arms))
                wave.append({"id": f"s{seed_index:03d}_r{cycle:03d}_ab{key}", "seed":seed,
                    "seed_index":seed_index,"cycle":cycle,"a":a,"b":b,"arms":list(arms)})
        wave.sort(key=lambda x: digest([order_seed,"wave",cycle,x["seed"],x["a"],x["b"]]))
        result.extend(wave)
    return result

def slots(plan: dict) -> list[dict]:
    result = []
    for block in plan["blocks"]:
        for position, arm in enumerate(block["arms"]):
            for stage in (("not","and") if arm == "pipeline" else (arm,)):
                result.append({"id":block["id"]+"__"+stage,"block_id":block["id"],"arm":arm,
                    "stage":stage,"position":position,"seed":block["seed"],"seed_index":block["seed_index"],
                    "cycle":block["cycle"],"a":block["a"],"b":block["b"]})
    return result

def make_request(plan: dict, slot: dict, parent_value: bool | None = None) -> bytes:
    """원래 템플릿의 식과 seed만 바꾼다. 부모는 실제 반환값만 받으며 정답표는 쓰지 않는다."""
    body = strict_json(unb64(plan["baseline"]["templates"][input_key(slot["a"],slot["b"])]["request_b64"]))
    values = strict_json(body["messages"][1]["content"][7:])
    values["expression"] = EXPRS[slot["stage"]]
    if slot["stage"] == "and":
        require(type(parent_value) is bool, "실제 부모 bool 없이는 AND 호출 금지")
        values["b"] = parent_value
    body["messages"][1]["content"] = "input: " + wire(values).decode("utf-8")
    body["options"]["seed"] = slot["seed"]
    return wire(body)

def prepare(baseline_bundle: Path, out: Path) -> dict:
    from .evidence import import_v048
    require(not out.exists(), "기존 계획은 덮어쓰지 않습니다: " + str(out))
    baseline, reference = import_v048(baseline_bundle)
    legacy = strict_json(unb64(reference["plan_b64"]))
    require(len(legacy["seeds"]) == 10, "이번 등록 설계는 v048 seed 10개 전체를 요구합니다.")
    plan = {"contract":CONTRACT,"software_version":__version__,"created_at":utc_now(),
        "baseline":baseline,"reference":reference,"source_fingerprint":source_fingerprint(),
        "seeds":list(legacy["seeds"]),"cycles":CYCLES,"order_seed":ORDER_SEED,
        "blocks":make_schedule(legacy["seeds"],CYCLES,ORDER_SEED),
        "max_calls":len(legacy["seeds"])*4*CYCLES*6,"analysis_policy":copy.deepcopy(POLICY)}
    plan["plan_sha256"] = digest(plan)
    validate_plan(plan); write_json(out,plan,exclusive=True)
    return plan

def validate_plan(plan: dict, *, check_sources: bool = True) -> None:
    from paired_probe_v048.plan import validate_plan as validate_v048
    keys={"contract","software_version","created_at","baseline","reference","source_fingerprint",
          "seeds","cycles","order_seed","blocks","max_calls","analysis_policy","plan_sha256"}
    require(isinstance(plan,dict) and set(plan)==keys and plan["contract"]==CONTRACT,"v049 계획 필드/계약 불일치")
    require(plan["plan_sha256"]==digest({k:v for k,v in plan.items() if k!="plan_sha256"}),"계획 해시 불일치")
    require(plan["software_version"]==__version__ and canonical(plan["analysis_policy"])==canonical(POLICY),"등록 정책 변경")
    r=plan["reference"]
    require(r["contract"]=="audited-v048-bundle-reference-r1" and r["anchor"]=="bundled_external_plan","기준선 계약 오류")
    require(r["receipt_sha256"]==digest({k:v for k,v in r.items() if k!="receipt_sha256"}),"기준선 영수증 해시 불일치")
    raw=unb64(r["plan_b64"]); require(sha(raw)==r["plan_bytes_sha256"],"v048 원문 계획 해시 불일치")
    legacy=strict_json(raw); validate_v048(legacy,check_sources=check_sources)
    require(r["plan_sha256"]==legacy["plan_sha256"] and canonical(plan["baseline"])==canonical(legacy["baseline"]),"기준선 설정 변경")
    seeds=plan["seeds"]
    require(isinstance(seeds,list) and len(seeds)==10 and all(type(s) is int for s in seeds)
            and seeds==legacy["seeds"],"v048의 전체 seed와 순서를 유지해야 합니다.")
    require(type(plan["cycles"]) is int and plan["cycles"]==CYCLES and type(plan["order_seed"]) is int
            and plan["order_seed"]==ORDER_SEED,"반복/순서 정책 변경")
    require(type(plan["max_calls"]) is int and plan["max_calls"]==480,"호출 한도 불일치")
    require(canonical(plan["blocks"])==canonical(make_schedule(seeds,CYCLES,ORDER_SEED)),"동결 순서·입력·조건 불일치")
    if check_sources: require(plan["source_fingerprint"]==source_fingerprint(),"계획 동결 후 실행/감사 소스 변경")
