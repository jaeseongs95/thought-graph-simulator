"""Windows에서 `py -3 -m local_llm ...`으로 실행하는 진입점."""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

from .client import APIError, OllamaClient, local_endpoint
from .common import REPO, ContractError, load_core, read_json, require, write_json
from .design import build_plan
from .report import write_report
from .runner import environment, run


def design_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", choices=("smoke", "pilot", "full"), default="smoke")
    parser.add_argument("--problems", type=Path, default=REPO / "examples" / "problems.json")
    parser.add_argument("--problem", action="append", help="사용할 문제 id. 여러 번 지정 가능")
    parser.add_argument("--repeats", type=int, help="기본 smoke/pilot 1회, full 3회")
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--allow-core-change", action="store_true", help="검토 후 변경된 기존 검증기를 명시적으로 허용")


def network_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=float, default=300, help="요청별 소켓 대기 제한(초)")


def prepare_design(args: argparse.Namespace):
    core, info = load_core(args.allow_core_change)
    problems = read_json(args.problems)
    require(isinstance(problems, list), "문제 파일은 JSON 배열이어야 합니다.")
    for problem in problems:
        core.check_problem(problem)
    require(len({p["id"] for p in problems}) == len(problems), "중복 문제 id")
    if args.problem:
        require(len(args.problem) == len(set(args.problem)), "같은 --problem을 중복 지정했습니다.")
        lookup = {p["id"]: p for p in problems}
        require(set(args.problem) <= set(lookup), "존재하지 않는 --problem id")
        problems = [lookup[pid] for pid in args.problem]
    plan = build_plan(core, problems, args.profile, args.repeats, args.seed)
    return core, info, plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="고정 목표 A/D/M 로컬 LLM 검증")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="설치·메타데이터만 조회. 추론/다운로드 없음")
    network_arguments(doctor)
    doctor.add_argument("--allow-core-change", action="store_true")
    planner = sub.add_parser("plan", help="조건표만 작성. Ollama 접속/추론 없음")
    design_arguments(planner)
    planner.add_argument("--save", type=Path, help="선택: 전체 조건표를 새 JSON 파일로 저장")
    execute = sub.add_parser("run", help="로컬 모델을 실제 호출")
    design_arguments(execute)
    network_arguments(execute)
    execute.add_argument("--out", type=Path, help="새 결과 디렉터리")
    execute.add_argument("--resume", action="store_true", help="같은 설정에서 미시작 조건만 이어서 실행")
    execute.add_argument("--temperature", type=float, default=0.2)
    execute.add_argument("--num-ctx", type=int, default=8192)
    execute.add_argument("--num-predict", type=int, default=4096)
    execute.add_argument("--threads", type=int, default=6)
    execute.add_argument("--batch-size", type=int, default=256)
    execute.add_argument("--think", action="store_true", help="별도 실험으로 thinking 활성화. 기본은 비활성")
    summarize = sub.add_parser("summarize", help="저장된 결과를 재집계. Ollama 접속/추론 없음")
    summarize.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            _, info = load_core(args.allow_core_change)
            client = OllamaClient(args.endpoint, args.timeout)
            details = client.inspect(args.model)
            output = {"core": info, "environment": environment(),
                      "model": details["tag"], "server": details["server"],
                      "capabilities": details["show"].get("capabilities"),
                      "running_models": details["running_models"],
                      "note": "메타데이터 조회만 완료. JSON 생성·GPU 추론 성공 여부는 smoke에서 확인."}
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 0
        if args.command == "summarize":
            summary = write_report(args.out.resolve())
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
        core, info, plan = prepare_design(args)
        if args.command == "plan":
            output = {"profile": plan["profile"], "problem_ids": [p["id"] for p in plan["problems"]],
                      "conditions_per_problem": len(plan["roles"]), "repeats": plan["repeats"],
                      "assigned_calls": plan["assigned_calls"], "warnings": plan["warnings"],
                      "reference_depths": plan["reference_depths"],
                      "note": "실행 계획이며 LLM 실행 결과가 아님"}
            if args.save:
                require(not args.save.exists(), "조건표 저장 대상이 이미 존재합니다.")
                write_json(args.save, plan)
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 0
        require(math.isfinite(args.temperature) and 0 <= args.temperature <= 2, "temperature 범위: 0~2")
        require(math.isfinite(args.timeout) and 0 < args.timeout <= 3600, "timeout 범위 오류")
        require(4096 <= args.num_ctx <= 65536, "num-ctx 범위: 4096~65536")
        require(256 <= args.num_predict < args.num_ctx, "출력 한도는 256 이상, context보다 작아야 합니다.")
        require(1 <= args.threads <= 64 and 1 <= args.batch_size <= 2048, "스레드/배치 범위 오류")
        require(not args.resume or args.out is not None, "--resume에는 기존 --out을 명시하세요.")
        config = {"model": args.model, "endpoint": local_endpoint(args.endpoint),
                  "timeout_seconds": args.timeout, "think": args.think,
                  "options": {"temperature": args.temperature, "top_p": 0.9, "top_k": 20,
                              "repeat_penalty": 1.0, "num_ctx": args.num_ctx,
                              "num_predict": args.num_predict, "num_thread": args.threads,
                              "num_batch": args.batch_size}}
        out = args.out or (REPO / "results_llm" / f"{args.profile}_{datetime.now():%Y%m%d_%H%M%S}")
        print(f"배정: {plan['assigned_calls']}회 / 모델: {args.model} / 결과: {out}", flush=True)
        for warning in plan["warnings"]:
            print("문제 구성 경고: " + warning, flush=True)
        return run(core, info, plan, config, out, args.resume)
    except (ContractError, APIError, OSError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
