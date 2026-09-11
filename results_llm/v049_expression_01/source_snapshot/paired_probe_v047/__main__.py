"""python -m paired_probe_v047 명령행 인터페이스."""
from __future__ import annotations
import argparse
import json
import sys
import unittest
from pathlib import Path
from .contracts import ContractError, read_json, require
from .plan import prepare, validate_plan


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="기존 v045/v046을 보존하는 동일 배치 대조 실험")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="기존 원문을 찾아 계획을 동결. 네트워크 호출 없음")
    p.add_argument("--source-root", type=Path, default=Path("results_llm"))
    p.add_argument("--source-run", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--cycles", type=int, default=6)
    p.add_argument("--seeds", help="쉼표 구분. 생략하면 원래 seed 그대로 사용")
    p.add_argument("--order-seed", type=int, default=4701729)
    p = sub.add_parser("show", help="동결 계획을 확인. 네트워크 호출 없음")
    p.add_argument("--plan", type=Path, required=True)
    p = sub.add_parser("run", help="명시적으로 로컬 Ollama 추론 실행")
    p.add_argument("--plan", type=Path, required=True); p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("audit", help="외부 동결 계획과 보존 원문으로 오프라인 재계산")
    p.add_argument("--plan", type=Path, required=True); p.add_argument("--run", type=Path, required=True)
    sub.add_parser("selftest", help="Ollama/모델 없이 단위·가짜 HTTP 통합 시험")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            seeds = [int(s.strip()) for s in args.seeds.split(",")] if args.seeds else None
            plan = prepare(args.source_root, args.out, source_run=args.source_run, seeds=seeds,
                           cycles=args.cycles, order_seed=args.order_seed)
            print_plan(plan)
        elif args.command == "show":
            plan = read_json(args.plan); validate_plan(plan); print_plan(plan)
        elif args.command == "run":
            from .runner import execute
            report = execute(args.plan, args.out)
            print(json.dumps({k: report[k] for k in ("data_integrity", "data_complete", "inference_calls",
                                                     "comparative_analysis_ready", "evidence_kind")}, ensure_ascii=False, indent=2))
            print("상세 결과:", args.out / "summary.ko.md")
            return 0 if report["data_complete"] else 3
        elif args.command == "audit":
            from .audit import audit_run
            report = audit_run(args.plan, args.run, write_report=True)
            print(json.dumps({k: report[k] for k in ("data_integrity", "data_complete", "inference_calls",
                                                     "comparative_analysis_ready", "evidence_kind")}, ensure_ascii=False, indent=2))
            return 0 if report["data_complete"] else 3
        else:
            root = Path(__file__).resolve().parent.parent
            require((root / "tests_v047").is_dir(), "tests_v047 폴더를 모듈과 함께 복사하세요.")
            suite = unittest.defaultTestLoader.discover(str(root / "tests_v047"), pattern="test_*.py")
            require(suite.countTestCases() > 0, "빈 테스트 모음은 성공으로 처리하지 않습니다.")
            return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    except (ContractError, OSError, KeyError, TypeError, ValueError) as exc:
        print("중단:", str(exc), file=sys.stderr)
        return 2
    return 0


def print_plan(plan):
    config = plan["baseline"]["config"]
    print(json.dumps({"contract": plan["contract"], "plan_sha256": plan["plan_sha256"],
        "source": plan["baseline"]["source_dir"], "source_contract": plan["baseline"]["source_contract"],
        "evidence_kind": plan["baseline"]["evidence_kind"], "model": config["model"],
        "endpoint": config["endpoint"], "options": config["options"], "seeds": plan["seeds"],
        "cycles": plan["cycles"], "input_blocks": len(plan["blocks"]),
        "max_inference_calls": plan["max_calls"], "skipped_sources": plan["skipped_sources"]},
        ensure_ascii=False, indent=2))
    print("각 입력에서 original/commuted/pipeline의 여섯 순서를 6회 단위로 균형 배치합니다.")
    if config["options"].get("temperature") == 0:
        print("주의: temperature=0을 보존했습니다. seed 다양화 자체를 독립적인 샘플링 반복으로 해석하지 않습니다.")

if __name__ == "__main__":
    raise SystemExit(main())
