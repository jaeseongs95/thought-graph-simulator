"""python -m paired_probe_v048: prepare/show/run/audit/bundle/selftest."""
from __future__ import annotations
import argparse
import json
import sys
import unittest
import zipfile
from pathlib import Path
from .contracts import ContractError, read_json, require, sha, wire
from .plan import prepare, validate_plan


def print_plan(plan: dict) -> None:
    config = plan["baseline"]["config"]
    print(json.dumps({"contract": plan["contract"], "plan_sha256": plan["plan_sha256"],
        "model": config["model"], "endpoint": config["endpoint"], "options": config["options"],
        "excluded_discovery_seeds": plan["reference"]["discovery_seeds"],
        "new_seeds": plan["seeds"], "cycles_per_seed": plan["cycles"],
        "max_inference_calls": plan["max_calls"], "v047_anchor": plan["reference"]["anchor"],
        "evidence_kind": plan["baseline"]["evidence_kind"]}, ensure_ascii=False, indent=2))
    print("prepare/show는 네트워크·추론을 실행하지 않습니다. run에서만 계획된 로컬 추론을 실행합니다.")


def print_report(report: dict) -> None:
    keys = ("data_integrity", "data_complete", "comparative_analysis_ready", "evidence_kind",
            "inference_calls", "max_inference_calls", "matching_v047_seeds", "seed_count")
    print(json.dumps({key: report[key] for key in keys}, ensure_ascii=False, indent=2))


def bundle(plan_path: Path, run: Path, out: Path) -> dict:
    from .audit import audit_run
    require(not out.exists(), "기존 ZIP은 덮어쓰지 않습니다.")
    require(not out.resolve().is_relative_to(run.resolve()), "ZIP은 실행 원문 폴더 밖에 저장하세요.")
    report = audit_run(plan_path, run, write_report=True)
    paths = sorted(p for p in run.rglob("*") if p.is_file())
    require(all(not p.is_symlink() for p in run.rglob("*")), "심볼릭 링크를 증거 ZIP에 포함하지 않습니다.")
    inventory = {}
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            name = "run/" + path.relative_to(run).as_posix()
            raw = path.read_bytes()
            archive.writestr(name, raw); inventory[name] = sha(raw)
        raw = plan_path.read_bytes()
        archive.writestr("external_plan/v048.plan.json", raw)
        inventory["external_plan/v048.plan.json"] = sha(raw)
        archive.writestr("BUNDLE_MANIFEST.json", wire({"contract": "v048-evidence-bundle-r1",
            "data_complete": report["data_complete"], "plan_sha256": report["plan_sha256"],
            "file_hashes": inventory, "note": "원문·외부 계획 동봉. 외부 전자서명은 아님"}))
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="v047 기준선을 보존하는 사전 고정 다중-seed 대조")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="v047 원문 감사 후 새 seed 계획 동결. 네트워크 없음")
    p.add_argument("--baseline-run", type=Path, required=True)
    anchoring = p.add_mutually_exclusive_group(required=True)
    anchoring.add_argument("--baseline-plan", type=Path)
    anchoring.add_argument("--accept-snapshot", action="store_true", help="외부 동결 계획이 없는 경우를 명시. 약한 기준선으로 기록")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seeds", help="생략하면 결과와 무관한 사전 고정 새 seed 10개")
    p.add_argument("--cycles", type=int, default=6, help="6의 배수. 기본 6")
    p = sub.add_parser("show", help="동결 계획 확인. 네트워크 없음")
    p.add_argument("--plan", type=Path, required=True)
    p = sub.add_parser("run", help="기존 결과를 덮어쓰지 않고 실제 로컬 추론 실행")
    p.add_argument("--plan", type=Path, required=True); p.add_argument("--out", type=Path, required=True)
    for name, description in (("audit", "외부 계획과 원문으로 오프라인 재채점"),
                              ("bundle", "원문·외부 계획·재채점 결과를 ZIP으로 묶기")):
        p = sub.add_parser(name, help=description)
        p.add_argument("--plan", type=Path, required=True); p.add_argument("--run", type=Path, required=True)
        if name == "bundle":
            p.add_argument("--out", type=Path, required=True)
    sub.add_parser("selftest", help="기존 v047 회귀 + v048 단위·합성 HTTP 시험. 실제 Ollama 호출 없음")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            seeds = [int(s.strip()) for s in args.seeds.split(",")] if args.seeds is not None else None
            plan = prepare(args.baseline_run, args.out, baseline_plan=args.baseline_plan,
                accept_snapshot=args.accept_snapshot, seeds=seeds, cycles=args.cycles)
            print_plan(plan)
        elif args.command == "show":
            plan = read_json(args.plan); validate_plan(plan); print_plan(plan)
        elif args.command == "run":
            from .runner import execute
            report = execute(args.plan, args.out); print_report(report)
            print("결과:", args.out / "summary.ko.md")
            return 0 if report["comparative_analysis_ready"] else 3
        elif args.command == "audit":
            from .audit import audit_run
            report = audit_run(args.plan, args.run, write_report=True); print_report(report)
            return 0 if report["comparative_analysis_ready"] else 3
        elif args.command == "bundle":
            report = bundle(args.plan, args.run, args.out); print_report(report)
            print("증거 ZIP:", args.out)
        else:
            root = Path(__file__).resolve().parent.parent
            suite = unittest.TestSuite()
            for folder in ("tests_v047", "tests_v048"):
                require((root / folder).is_dir(), "시험 폴더 누락: " + folder)
                cases = unittest.TestLoader().discover(str(root / folder), pattern="test_*.py", top_level_dir=str(root))
                require(cases.countTestCases() > 0, "빈 시험 모음은 성공으로 처리하지 않습니다.")
                suite.addTests(cases)
            return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    except (ContractError, OSError, KeyError, TypeError, ValueError) as exc:
        print("중단:", str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
