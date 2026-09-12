"""Windows: py -3 -m local_llm. 모델 호출 명령과 오프라인 명령을 구분한다."""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

from .calibration import build_calibration_plan as legacy_calibration_plan
from .calibration_v4 import build_calibration_plan
from .datasets_v4 import transfer_problems
from .model_policy import DEFAULT_MODEL, identify_model, resolve_config
from .client import APIError, OllamaClient, local_endpoint
from .common import REPO, ContractError, load_core, read_json, require, write_json
from .design import build_plan
from .diagnostics import reanalyze
from .protocol_v2 import PROTOCOL
from .report import write_report
from .runner import environment, run
from .selfcheck import selfcheck
from .gate import validate_gate


def design_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", choices=("smoke", "pilot", "full"), default="smoke")
    parser.add_argument("--suite", choices=("transfer-v4", "legacy"), default="transfer-v4",
                        help="기본은 추가 구조 3개. legacy는 기존 examples/problems.json")
    parser.add_argument("--problems", type=Path, help="직접 지정하면 --suite보다 우선")
    parser.add_argument("--problem", action="append", help="사용할 문제 id. 여러 번 지정 가능")
    parser.add_argument("--repeats", type=int, help="기본 smoke/pilot 1회, full 3회")
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--allow-core-change", action="store_true")


def network_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=float, default=300)


def generation_arguments(parser: argparse.ArgumentParser) -> None:
    network_arguments(parser)
    parser.add_argument("--out", type=Path, help="새 결과 폴더")
    parser.add_argument("--resume", action="store_true", help="동일 설정에서 미시작 조건만 이어서 실행")
    parser.add_argument("--temperature", type=float, help="미지정 시 Instruct 0.7, Thinking 0.6")
    parser.add_argument("--top-p", type=float, help="미지정 시 Instruct 0.8, Thinking 0.95")
    parser.add_argument("--num-ctx", type=int, help="미지정 시 Instruct 8192, Thinking 16384")
    parser.add_argument("--num-predict", type=int, help="미지정 시 Instruct 4096, Thinking 8192(사고 포함 출력 예산)")
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--mode", choices=("auto", "non-thinking", "thinking"), default="auto",
                        help="GGUF 메타데이터와 대조. 불일치 시 추론 전에 중단")
    parser.add_argument("--think", action="store_true", help="--mode thinking의 이전 명령 호환 별칭")
    parser.add_argument("--prompt-profile", choices=("legacy-v2", "explicit-v3", "factorized-v4", "definitions-v4"), default="factorized-v4",
                        help="기본은 구성요소별 예시. definitions-v4는 같은 지시에서 예시만 제거한 대조")
    parser.add_argument("--fail-on-model-failure", action="store_true",
                        help="모델 성능 FAIL도 종료 코드 1로 취급. 기본은 실행 완료 시 0")


def prepare_design(args: argparse.Namespace):
    core, info = load_core(args.allow_core_change)
    problems = (read_json(args.problems) if args.problems else
                read_json(REPO / "examples" / "problems.json") if args.suite == "legacy" else
                transfer_problems(args.seed))
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
    require(args.temperature is None or math.isfinite(args.temperature) and 0 <= args.temperature <= 2,
            "temperature 범위: 0~2")
    require(args.top_p is None or math.isfinite(args.top_p) and 0 < args.top_p <= 1,
            "top-p 범위: 0초과 1이하")
    require(math.isfinite(args.timeout) and 0 < args.timeout <= 3600, "timeout 범위 오류")
    require(args.num_ctx is None or 4096 <= args.num_ctx <= 65536, "num-ctx 범위: 4096~65536")
    require(args.num_predict is None or 256 <= args.num_predict <= 65535, "num-predict 범위 오류")
    require(not args.think or args.mode in {"auto", "thinking"}, "--think와 --mode non-thinking은 함께 쓸 수 없습니다.")
    require(1 <= args.threads <= 64 and 1 <= args.batch_size <= 2048, "스레드/배치 범위 오류")
    require(not args.resume or args.out is not None, "--resume에는 기존 --out을 명시하세요.")
    return {"config_stage": "unresolved", "requested_mode": "thinking" if args.think else args.mode,
            "protocol": PROTOCOL, "prompt_profile": args.prompt_profile, "model": args.model, "endpoint": local_endpoint(args.endpoint),
            "timeout_seconds": args.timeout,
            "options": {"temperature": args.temperature, "top_p": args.top_p, "top_k": 20, "min_p": 0.0,
                        "repeat_penalty": 1.0, "num_ctx": args.num_ctx,
                        "num_predict": args.num_predict, "num_thread": args.threads,
                        "num_batch": args.batch_size}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="고정 목표 A/D/M 로컬 LLM 검증 v0.4")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="설치·메타데이터 조회만 수행. 추론 없음")
    network_arguments(doctor)
    doctor.add_argument("--allow-core-change", action="store_true")
    doctor.add_argument("--mode", choices=("auto", "non-thinking", "thinking"), default="auto")
    planner = sub.add_parser("plan", help="조건표만 작성. 네트워크 없음")
    design_arguments(planner)
    planner.add_argument("--save", type=Path)
    execute = sub.add_parser("run", help="통합 A/D/M 조건을 로컬 모델로 실행")
    design_arguments(execute)
    generation_arguments(execute)
    gate = execute.add_mutually_exclusive_group()
    gate.add_argument("--gate", type=Path, help="같은 v0.4 모델·모드·프롬프트·문제의 새 smoke. v0.2/v0.3 실행을 새 기준선에 섞지 않음")
    gate.add_argument("--ungated", action="store_true", help="실패 양상 탐색 목적으로 smoke 게이트를 명시적으로 생략")
    execute.add_argument("--gate-mode", choices=("readiness", "strict"), default="readiness",
                         help="기본은 실행 준비 검사. strict만 전 조건의 성능 성공도 요구")
    gate_check = sub.add_parser("check-gate", help="기존 smoke의 실행 준비만 오프라인 재검사. 네트워크 없음")
    design_arguments(gate_check)
    generation_arguments(gate_check)
    gate_check.set_defaults(profile="pilot")
    gate_check.add_argument("--gate", type=Path, required=True)
    gate_check.add_argument("--gate-mode", choices=("readiness", "strict"), default="readiness")
    calibration = sub.add_parser("calibrate", help="기본 구성요소 진단 24회. 통합 ADM과 별도 집계")
    generation_arguments(calibration)
    calibration.add_argument("--calibration-suite", choices=("v4", "legacy-v2"), default="v4")
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
                      "running_models": details["running_models"],
                      "mode_policy": resolve_config({"requested_mode": args.mode, "options": {}}, details)["mode_policy"],
                      "note": "메타데이터 검사만 수행. 실제 응답 채널 검사는 첫 추론에서 별도 수행. 다운로드/추론하지 않음"}
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
                require(args.calibration_suite != "v4" or args.prompt_profile in {"factorized-v4", "definitions-v4"},
                        "v4 분리 진단에는 factorized-v4 또는 definitions-v4 프롬프트를 사용하세요.")
                builder = build_calibration_plan if args.calibration_suite == "v4" else legacy_calibration_plan
                plan = builder(core, args.seed)
            else:
                core, info, plan = prepare_design(args)
            if args.command == "check-gate":
                saved = read_json(args.gate / "manifest.json")
                # 오프라인 명령이므로 저장된 메타데이터로만 설정을 확정한다.
                config = resolve_config(generation_config(args), saved["ollama_metadata"])
                output = validate_gate(core, args.gate, config, plan, args.gate_mode)
            elif args.command == "plan":
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
                            "pilot/full에는 --gate <smoke 폴더>를 지정하세요. "
                            "실패 포함 탐색 실행은 --ungated로 명시할 수 있습니다.")
                out = args.out or (REPO / "results_llm" / f"v04_{plan['profile']}_{datetime.now():%Y%m%d_%H%M%S}")
                print(f"실행 계획: {plan['assigned_calls']}회 / 모델: {args.model} / "
                      f"프롬프트: {args.prompt_profile} / 결과: {out}", flush=True)
                for warning in plan["warnings"]:
                    print("문제 구성 경고: " + warning, flush=True)
                return run(core, info, plan, config, out, args.resume, gate_path,
                           getattr(args, "gate_mode", "readiness"), args.fail_on_model_failure)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (ContractError, APIError, OSError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
