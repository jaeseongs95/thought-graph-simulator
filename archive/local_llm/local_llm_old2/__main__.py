"""Windows: py -3 -m local_llm. 모델 호출 명령과 오프라인 명령을 구분한다."""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

from .calibration import build_calibration_plan
from .client import APIError, OllamaClient, local_endpoint
from .common import REPO, ContractError, load_core, read_json, require, write_json
from .design import build_plan
from .diagnostics import reanalyze
from .protocol_v2 import PROTOCOL
from .report import write_report
from .runner import environment, run
from .selfcheck import selfcheck


def design_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", choices=("smoke", "pilot", "full"), default="smoke")
    parser.add_argument("--problems", type=Path, default=REPO / "examples" / "problems.json")
    parser.add_argument("--problem", action="append", help="사용할 문제 id. 여러 번 지정 가능")
    parser.add_argument("--repeats", type=int, help="기본 smoke/pilot 1회, full 3회")
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--allow-core-change", action="store_true")


def network_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=float, default=300)


def generation_arguments(parser: argparse.ArgumentParser) -> None:
    network_arguments(parser)
    parser.add_argument("--out", type=Path, help="새 결과 폴더")
    parser.add_argument("--resume", action="store_true", help="동일 설정에서 미시작 조건만 이어서 실행")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--num-ctx", type=int, default=8192)
    parser.add_argument("--num-predict", type=int, default=4096)
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--think", action="store_true", help="별도 조건으로 thinking 사용. 기본 비활성")


def prepare_design(args: argparse.Namespace):
    core, info = load_core(args.allow_core_change)
    problems = read_json(args.problems)
    require(isinstance(problems, list), "문제 파일은 JSON 배열이어야 합니다.")
    for problem in problems:
        core.check_problem(problem)
    require(len({p["id"] for p in problems}) == len(problems), "중복 문제 id")
    if args.problem:
        require(len(args.problem) == len(set(args.problem)), "중복 --problem")
        lookup = {p["id"]: p for p in problems}
        require(set(args.problem) <= set(lookup), "존재하지 않는 --problem id")
        problems = [lookup[pid] for pid in args.problem]
    return core, info, build_plan(core, problems, args.profile, args.repeats, args.seed)


def generation_config(args: argparse.Namespace) -> dict:
    require(math.isfinite(args.temperature) and 0 <= args.temperature <= 2, "temperature 범위: 0~2")
    require(math.isfinite(args.timeout) and 0 < args.timeout <= 3600, "timeout 범위 오류")
    require(4096 <= args.num_ctx <= 65536, "num-ctx 범위: 4096~65536")
    require(256 <= args.num_predict < args.num_ctx, "출력 한도는 256 이상, context보다 작아야 합니다.")
    require(1 <= args.threads <= 64 and 1 <= args.batch_size <= 2048, "스레드/배치 범위 오류")
    require(not args.resume or args.out is not None, "--resume에는 기존 --out을 명시하세요.")
    return {"protocol": PROTOCOL, "model": args.model, "endpoint": local_endpoint(args.endpoint),
            "timeout_seconds": args.timeout, "think": args.think,
            "options": {"temperature": args.temperature, "top_p": 0.9, "top_k": 20,
                        "repeat_penalty": 1.0, "num_ctx": args.num_ctx,
                        "num_predict": args.num_predict, "num_thread": args.threads,
                        "num_batch": args.batch_size}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="고정 목표 A/D/M 로컬 LLM 검증 v0.2")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="설치·메타데이터 조회만 수행. 추론 없음")
    network_arguments(doctor)
    doctor.add_argument("--allow-core-change", action="store_true")
    planner = sub.add_parser("plan", help="조건표만 작성. 네트워크 없음")
    design_arguments(planner)
    planner.add_argument("--save", type=Path)
    execute = sub.add_parser("run", help="통합 A/D/M 조건을 로컬 모델로 실행")
    design_arguments(execute)
    generation_arguments(execute)
    gate = execute.add_mutually_exclusive_group()
    gate.add_argument("--gate", type=Path, help="pilot/full 전에 재검사할 v0.2 smoke 결과 폴더")
    gate.add_argument("--ungated", action="store_true", help="실패 양상 탐색 목적으로 smoke 게이트를 명시적으로 생략")
    calibration = sub.add_parser("calibrate", help="분리 교정 8회. 통합 ADM 결과와 별도 집계")
    generation_arguments(calibration)
    calibration.add_argument("--seed", type=int, default=1729)
    calibration.add_argument("--allow-core-change", action="store_true")
    summarize = sub.add_parser("summarize", help="저장된 record를 재집계. 네트워크 없음")
    summarize.add_argument("--out", type=Path, required=True)
    inspect = sub.add_parser("inspect-results", help="보존 응답을 재검사해 새 폴더에 진단 저장. 네트워크 없음")
    inspect.add_argument("--input", type=Path, required=True)
    inspect.add_argument("--out", type=Path, required=True)
    inspect.add_argument("--allow-core-change", action="store_true")
    check = sub.add_parser("selfcheck", help="오프라인 하네스 자체 검사. 네트워크 없음")
    check.add_argument("--allow-core-change", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            _, info = load_core(args.allow_core_change)
            details = OllamaClient(args.endpoint, args.timeout).inspect(args.model)
            output = {"core": info, "environment": environment(), "model": details["tag"],
                      "server": details["server"], "capabilities": details["show"].get("capabilities"),
                      "running_models": details["running_models"], "note": "추론·다운로드하지 않음"}
        elif args.command == "summarize":
            output = write_report(args.out.resolve())
        elif args.command == "selfcheck":
            core, _ = load_core(args.allow_core_change)
            output = selfcheck(core)
        elif args.command == "inspect-results":
            core, _ = load_core(args.allow_core_change)
            result = reanalyze(core, args.input, args.out)
            output = {"counts": result["counts"], "out": str(args.out), "model_called": False}
        else:
            if args.command == "calibrate":
                core, info = load_core(args.allow_core_change)
                plan = build_calibration_plan(core, args.seed)
            else:
                core, info, plan = prepare_design(args)
            if args.command == "plan":
                output = {"profile": plan["profile"], "problem_ids": [p["id"] for p in plan["problems"]],
                          "conditions_per_problem": len(plan["roles"]), "repeats": plan["repeats"],
                          "assigned_calls": plan["assigned_calls"], "warnings": plan["warnings"],
                          "reference_depths": plan["reference_depths"], "note": "계획이며 실행 결과가 아님"}
                if args.save:
                    require(not args.save.exists(), "조건표 저장 대상이 이미 존재합니다.")
                    write_json(args.save, plan)
            else:
                config = generation_config(args)
                gate_path = getattr(args, "gate", None)
                if args.command == "run" and args.profile in {"pilot", "full"}:
                    require(gate_path is not None or args.ungated,
                            "pilot/full에는 --gate <v0.2 smoke 폴더>를 지정하세요. "
                            "실패 포함 탐색 실행은 --ungated로 명시할 수 있습니다.")
                out = args.out or (REPO / "results_llm" / f"v02_{plan['profile']}_{datetime.now():%Y%m%d_%H%M%S}")
                print(f"배정: {plan['assigned_calls']}회 / 모델: {args.model} / 결과: {out}", flush=True)
                for warning in plan["warnings"]:
                    print("문제 구성 경고: " + warning, flush=True)
                return run(core, info, plan, config, out, args.resume, gate_path)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (ContractError, APIError, OSError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
