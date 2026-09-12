"""명시적인 합성 서버로 전체 96회 경로를 재현한다. 실제 LLM 성과가 아니다."""
from __future__ import annotations
import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from paired_probe_v047.plan import prepare
from paired_probe_v047.runner import execute
from paired_probe_v047.audit import audit_run
from paired_probe_v047.contracts import write_json
from tests_v047.fixtures import baseline, fake_server

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "validation" / "demo_pattern_rerun")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("기존 합성 결과를 덮어쓰지 않습니다. 새 --out 경로를 지정하세요.")
    args.out.mkdir(parents=True)
    with fake_server("original_false") as (state, endpoint):
        baseline(args.out / "source_fixture", endpoint)
        plan_path = args.out / "frozen.plan.json"
        prepare(args.out / "source_fixture", plan_path)
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            report = execute(plan_path, args.out / "run")
        (args.out / "execution.log").write_text(capture.getvalue(), encoding="utf-8")
        n = len(state.requests)
    # 가짜 서버 종료 후 네트워크 없이 다시 감사한다.
    replay = audit_run(plan_path, args.out / "run", write_report=True)
    assert replay == report
    result = {"evidence_kind": "synthetic_fixture", "live_llm_calls": 0,
        "synthetic_http_inference_requests": n, "offline_replay_equal": replay == report,
        "original_correct": report["arms"]["original"]["final_correct"],
        "commuted_correct": report["arms"]["commuted"]["final_correct"],
        "pipeline_strict_correct": report["arms"]["pipeline"]["strict_trace_correct"],
        "assigned_per_arm": report["arms"]["original"]["assigned"]}
    write_json(args.out / "DEMO_STATUS.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
