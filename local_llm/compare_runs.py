"""대응 조건의 변경 범위를 검증하는 오프라인 비교. 원인을 다수결로 고르지 않는다."""
from __future__ import annotations
import argparse
import copy
import json
import sys
from pathlib import Path
from .common import ContractError, digest, read_json, require, write_json, write_text
from .report import read_records

FACTORS = ("format", "temperature", "seed", "model", "server")


def normalized_request(body: dict, vary: str) -> tuple[dict, object]:
    result = copy.deepcopy(body)
    if vary == "format": value = result.pop("format", "<omitted>")
    elif vary == "model": value = result.pop("model")
    elif vary in {"temperature", "seed"}: value = result["options"].pop(vary, "<omitted>")
    else: value = None
    return result, value


def compare(left: Path, right: Path, vary: str) -> dict:
    require(vary in FACTORS, "알 수 없는 비교 요인")
    left, right = left.resolve(), right.resolve()
    require(left != right, "서로 다른 실행을 지정하세요.")
    ma, mb = (read_json(p / "manifest.json") for p in (left, right))
    fa, fb = ma["frozen"], mb["frozen"]
    require(fa["core"]["sha256"] == fb["core"]["sha256"], "core가 달라 비교 불가")
    require(fa["runtime_sources_sha256"] == fb["runtime_sources_sha256"], "하네스 소스가 달라 단일 요인 비교 불가")
    require(fa["plan"].get("probe_contract") == fb["plan"].get("probe_contract") == "micro-v042", "같은 micro-v042 계약 실행만 비교")
    require(fa["plan"]["problems"] == fb["plan"]["problems"], "입력 문제가 다름")
    if vary != "server":
        require(fa["ollama_server"] == fb["ollama_server"], "서버 버전도 달라 단일 요인 비교 불가")
        require(fa["config"]["endpoint"] == fb["config"]["endpoint"], "서버 주소도 달라 단일 요인 비교 불가")
    if vary != "model":
        require(fa["model"]["digest"] == fb["model"]["digest"], "모델 digest도 달라 단일 요인 비교 불가")
        require(fa["model"]["show_sha256"] == fb["model"]["show_sha256"], "모델 템플릿/메타데이터도 달라 비교 불가")
    def records_at(path: Path, m: dict) -> dict:
        records = read_records(path, m)
        key = lambda c: (c["problem_id"], c["role_id"], c["repeat"])
        result = {key(r["case"]): r for r in records}
        require(len(result) == len(records) == len(m["frozen"]["plan"]["cases"]), "모든 배정 조건의 기록이 있어야 비교")
        return result
    ra, rb = records_at(left, ma), records_at(right, mb)
    require(ra.keys() == rb.keys(), "대응 과제 집합이 다름")
    rows = []; changed = False
    for key in sorted(ra):
        a, b = ra[key], rb[key]
        ca, cb = copy.deepcopy(a["case"]), copy.deepcopy(b["case"])
        for c in (ca, cb):
            c.pop("case_id")
            if vary == "format": c.pop("format_mode")
            if vary == "seed": c.pop("seed")
        require(ca == cb, f"과제 계약도 변경됨: {key}")
        pa = left / "cases" / a["case"]["case_id"]
        pb = right / "cases" / b["case"]["case_id"]
        aa, av = normalized_request(read_json(pa / "request.json")["body"], vary)
        bb, bv = normalized_request(read_json(pb / "request.json")["body"], vary)
        require(aa == bb, f"허용 요인 외 실제 HTTP 필드도 변경됨: {key}")
        changed |= av != bv
        rows.append({"problem_id": key[0], "condition": key[1], "repeat": key[2],
            "group": a["case"]["diagnostic_group"], "left_status": a["status"], "right_status": b["status"],
            "left_factor": av, "right_factor": bv, "fixed_request_sha256": digest(aa),
            "left_evidence": a.get("task_diagnostics"), "right_evidence": b.get("task_diagnostics"),
            "left_audit": a.get("audit"), "right_audit": b.get("audit")})
    if vary == "server":
        changed = (fa["ollama_server"] != fb["ollama_server"] or fa["config"]["endpoint"] != fb["config"]["endpoint"])
    if vary == "model": changed |= fa["model"]["digest"] != fb["model"]["digest"]
    require(changed, "지정 요인이 실제로 달라지지 않았습니다. 반복과 요인 대조를 혼동하지 마세요.")
    return {"model_called": False, "source_modified": False, "allowed_factor": vary,
        "left_run": ma["run_sha256"], "right_run": mb["run_sha256"], "paired_cases": len(rows),
        "request_control_verified": True, "comparisons": rows,
        "left_model": fa["model"], "right_model": fb["model"],
        "left_server": fa["ollama_server"], "right_server": fb["ollama_server"],
        "interpretation": "대응 조건의 기록된 요청 차이를 제한했다. 서버 내부 캐시/하드웨어 상태까지 통제한 인과 증명은 아니다. "
            "모델 교체에는 가중치·양자화·템플릿 등이 함께 달라질 수 있어 순수 양자화 효과로 단정하지 않는다. "
            "통제 과제와 추론 과제를 하나의 성능 평균으로 합치지 않는다."}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--left", type=Path, required=True); p.add_argument("--right", type=Path, required=True)
    p.add_argument("--vary", choices=FACTORS, required=True); p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    try:
        out = a.out.resolve()
        require(all(out != source.resolve() and not out.is_relative_to(source.resolve()) for source in (a.left, a.right)), "원본 밖에 저장")
        require(not out.exists() or not any(out.iterdir()), "출력 폴더가 비어 있지 않음")
        result = compare(a.left, a.right, a.vary)
        write_json(out / "comparison.json", result)
        lines = ["# 대응 조건 비교", "", f"변경 요인: {a.vary}; 대응 {result['paired_cases']}건", "",
            "| 과제 | 왼쪽 | 오른쪽 |", "| --- | --- | --- |"]
        lines += [f"| {r['condition']} | {r['left_status']} | {r['right_status']} |" for r in result["comparisons"]]
        write_text(out / "comparison.md", "\n".join(lines) + "\n\n" + result["interpretation"] + "\n")
        print(json.dumps({k:result[k] for k in ("model_called","allowed_factor","paired_cases","request_control_verified")}, ensure_ascii=False, indent=2))
        return 0
    except (ContractError, OSError, ValueError, KeyError, TypeError) as e:
        print(f"오류: {e}", file=sys.stderr); return 2

if __name__ == "__main__": raise SystemExit(main())
