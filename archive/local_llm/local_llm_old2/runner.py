"""순차 실행, 원문 보존, 최초 시도만 집계, 중단 후 미시작 조건 이어가기."""
from __future__ import annotations

import copy
import os
import platform
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from . import __version__
from .audit import evaluate_trace
from .client import APIError, OllamaClient
from .common import (PACKAGE, REPO, ContractError, bytes_hash, digest, read_json, require,
                     source_fingerprint, strict_json, utc_now, wire_json, write_json, write_text)
from .prompts import messages
from .protocol import TRANSPORT_SCHEMA, parse_payload, to_trace
from .report import read_records, write_report
from .diagnostics import raw_diagnostics
from . import protocol_v2, prompts_v2, calibration
from .selfcheck import selfcheck


USAGE_FIELDS = ("prompt_eval_count", "prompt_eval_cached_count", "eval_count",
                "total_duration", "load_duration", "prompt_eval_duration", "eval_duration")


def usage(response: dict) -> dict:
    data = {key: response.get(key) if type(response.get(key)) is int and response[key] >= 0 else None
            for key in USAGE_FIELDS}
    for source, target in (("total_duration", "total_seconds"), ("load_duration", "load_seconds"),
                           ("prompt_eval_duration", "prompt_eval_seconds"),
                           ("eval_duration", "generation_seconds")):
        data[target] = data[source] / 1e9 if data[source] is not None else None
    data["tokens_per_second"] = (data["eval_count"] / data["generation_seconds"]
                                 if data["eval_count"] is not None and data["generation_seconds"] else None)
    return data


def request_body(config: dict, case: dict, problem: dict) -> dict:
    options = dict(config["options"], seed=case["seed"])
    if case.get("task"):
        prompt = calibration.messages(problem, case)
        schema = calibration.output_schema(case)
    elif config.get("protocol") == protocol_v2.PROTOCOL:
        prompt = prompts_v2.messages(problem, case["role"])
        schema = protocol_v2.TRANSPORT_SCHEMA
    else:
        # 당시 응답의 오프라인 재검사와 기존 39개 계약시험을 위한 v1 호환 경로.
        prompt = messages(problem, case["role"])
        schema = TRANSPORT_SCHEMA
    return {"model": config["model"], "messages": prompt,
            "stream": False, "think": config["think"], "keep_alive": "10m",
            "format": copy.deepcopy(schema), "options": options}


def assess_response(core: Any, problem: dict, case: dict, reference: dict,
                    body: dict, response: dict) -> tuple[dict, dict | None]:
    """원문 응답을 판정한다. 토큰 종료나 JSON 오류를 고쳐서 통과시키지 않는다."""
    outcome: dict = {"status": "protocol_error", "audit": None, "error": None,
                     "usage": usage(response), "done_reason": response.get("done_reason")}
    trace = None
    is_v2 = "selected_final_node_id" in body.get("format", {}).get("properties", {})
    if not case.get("task"):
        raw_message = response.get("message")
        raw_content = raw_message.get("content") if isinstance(raw_message, dict) else None
        outcome["raw_diagnostics"] = raw_diagnostics(problem, raw_content, v2=is_v2)
    try:
        require(response.get("model") == body["model"], "요청 모델과 응답 모델 불일치")
        require(response.get("done") is True, "완료되지 않은 API 응답")
        if response.get("done_reason") == "length":
            outcome.update(status="truncated", error="출력 토큰 한도에서 종료됨. 완성된 JSON이어도 성공 처리하지 않음")
            return outcome, None
        require(response.get("done_reason") == "stop", "정상 stop 종료가 아닌 응답")
        message = response.get("message")
        require(isinstance(message, dict) and message.get("role") == "assistant", "assistant 응답 누락")
        require(not message.get("tool_calls"), "도구 호출이 포함된 응답은 실행하지 않고 거부함")
        require(body["think"] or not message.get("thinking"), "thinking=false 요청과 다른 응답")
        if case.get("task"):
            payload = strict_json(message.get("content"))
            audit = calibration.assess_payload(core, problem, case, payload)
            outcome["audit"] = audit
            if audit["valid_completion"]:
                outcome["status"] = "accepted"
            else:
                outcome.update(status="invalid_task", error=f"교정 과제 불일치: {audit['task_checks']}")
            return outcome, None
        if is_v2:
            payload = protocol_v2.parse_payload(message.get("content"))
            trace = protocol_v2.to_trace(core, problem, payload)
        else:
            payload = parse_payload(message.get("content"))
            trace = to_trace(core, problem, payload)
        audit = evaluate_trace(core, problem, trace, case["role"], reference)
        outcome["audit"] = audit
        if audit["negative_controls_ok"] is False:
            outcome.update(status="harness_error", error="검증기 반례가 수락됨. 실험을 중단해야 함")
        elif not audit["valid_completion"]:
            outcome.update(status="invalid_trace", error=(audit["audits"]["full"].get("error")
                           or "단순 지지 경로/사실 종단 계약 위반"))
        elif audit["role_adherent"] is False:
            outcome.update(status="role_mismatch", error=f"요청 역할 미준수: {audit['role_matches']}")
        else:
            outcome["status"] = "accepted"
    except ContractError as exc:
        outcome["error"] = str(exc)
    return outcome, trace


def environment() -> dict:
    data = {"python": sys.version, "os": platform.platform(), "machine": platform.machine(),
            "logical_cpu_count": os.cpu_count(), "nvidia_smi": None}
    binary = shutil.which("nvidia-smi")
    if binary:
        try:
            result = subprocess.run(
                [binary, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
                text=True, encoding="utf-8", errors="replace", capture_output=True,
                timeout=10, check=False,
            )
            data["nvidia_smi"] = {"returncode": result.returncode, "stdout": result.stdout.strip(),
                                  "stderr": result.stderr.strip()}
        except (OSError, subprocess.TimeoutExpired) as exc:
            data["nvidia_smi"] = {"error": str(exc)}
    return data


@contextmanager
def run_lock(out: Path) -> Iterator[None]:
    path = out / ".run.lock"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ContractError("이 결과 폴더에 실행 잠금이 있습니다. 실행 중인 프로세스가 없는지 확인하세요. "
                            "강제 종료로 남은 잠금만 수동으로 삭제한 뒤 --resume 하세요.") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()}\nstarted={utc_now()}\n")
        yield
    finally:
        path.unlink(missing_ok=True)


def save_record(folder: Path, record: dict) -> None:
    names = ("request.json", "request.wire.json", "response.raw.json", "trace.json", "timing.json", "gpu.json")
    record["artifacts_sha256"] = {name: bytes_hash((folder / name).read_bytes())
                                  for name in names if (folder / name).is_file()}
    write_json(folder / "record.json", record)


def _blank_record(case: dict, run_sha: str) -> dict:
    return {"case": case, "run_sha256": run_sha, "recorded_at": utc_now(),
            "status": "interrupted_unknown", "api_attempted": None,
            "wall_seconds": None, "usage": {}, "audit": None, "gpu": {}, "error": None}


def recover_case(core: Any, folder: Path, manifest: dict, problem: dict, case: dict) -> dict | None:
    """응답이 보존된 경우만 재판정. 요청만 남았으면 실패로 종결하고 다시 호출하지 않는다."""
    request_path = folder / "request.json"
    if not request_path.is_file():
        return None
    request = read_json(request_path)
    require(request["case_id"] == case["case_id"] and request["run_sha256"] == manifest["run_sha256"],
            "복구할 요청의 실험 결합 불일치")
    expected_body = request_body(manifest["frozen"]["config"], case, problem)
    require(request["body"] == expected_body, "복구할 요청 내용이 동결 설정과 다름")
    if manifest["frozen"]["config"].get("protocol") == protocol_v2.PROTOCOL:
        wire = folder / "request.wire.json"
        require(wire.is_file() and wire.read_bytes() == wire_json(expected_body).encode("utf-8"),
                "복구할 HTTP 요청 원문이 없거나 필드 순서/내용이 다름")
        require(request.get("wire_sha256") == bytes_hash(wire.read_bytes()), "HTTP 요청 원문 해시 불일치")
    record = _blank_record(case, manifest["run_sha256"])
    response_path = folder / "response.raw.json"
    if response_path.is_file():
        response = strict_json(response_path.read_text(encoding="utf-8"))
        require(isinstance(response, dict), "복구할 API 응답 객체 필요")
        outcome, trace = assess_response(core, problem, case,
            manifest["frozen"]["plan"]["reference_depths"][problem["id"]], request["body"], response)
        record.update(outcome, api_attempted=True, recovered_from_saved_response=True)
        if (folder / "timing.json").is_file():
            record["wall_seconds"] = read_json(folder / "timing.json").get("elapsed_seconds")
        if (folder / "gpu.json").is_file():
            record["gpu"] = read_json(folder / "gpu.json").get("model") or {}
            saved_digest = record["gpu"].get("digest")
            if saved_digest and saved_digest != manifest["frozen"]["model"]["digest"]:
                record.update(status="harness_error", error="복구한 실행 모델 digest 불일치")
        if trace is not None:
            write_json(folder / "trace.json", trace)
    else:
        record["error"] = "요청 의도만 보존되고 응답은 없음. 실제 생성·비용은 미확인. 재호출하지 않음."
    save_record(folder, record)
    return record


def _perform_case(core: Any, client: OllamaClient, manifest: dict, case: dict,
                  problem: dict, folder: Path) -> tuple[dict, int | None]:
    frozen = manifest["frozen"]
    expected_digest = frozen["model"]["digest"]
    require(client.tag(frozen["config"]["model"])["digest"] == expected_digest,
            "실행 도중 모델 태그 digest가 바뀌었습니다.")
    body = request_body(frozen["config"], case, problem)
    folder.mkdir(parents=True, exist_ok=True)
    wire = wire_json(body)
    write_json(folder / "request.json", {"case_id": case["case_id"], "run_sha256": manifest["run_sha256"],
                                        "created_at": utc_now(), "body": body,
                                        "wire_sha256": bytes_hash(wire.encode("utf-8"))})
    write_text(folder / "request.wire.json", wire)
    record = _blank_record(case, manifest["run_sha256"])
    record["api_attempted"] = True
    start = time.perf_counter()
    stop_code = None
    try:
        reply = client.chat(body)
        record["wall_seconds"] = reply.elapsed_seconds
        write_text(folder / "response.raw.json", reply.text)
        write_json(folder / "timing.json", {"elapsed_seconds": reply.elapsed_seconds})
        outcome, trace = assess_response(core, problem, case,
                    frozen["plan"]["reference_depths"][problem["id"]], body, reply.value)
        record.update(outcome)
        if trace is not None:
            write_json(folder / "trace.json", trace)
        # /api/ps는 모델 적재 정보다. 실제 GPU 이용률·최고 VRAM 측정이라고 부르지 않는다.
        try:
            running = client.running_model(frozen["config"]["model"])
            record["gpu"] = running or {}
            write_json(folder / "gpu.json", {"model": running, "observed_at": utc_now()})
            if running and running.get("digest") != expected_digest:
                record.update(status="harness_error", error="실행된 모델 digest 불일치")
        except APIError as exc:
            record["gpu_telemetry_error"] = str(exc)
        require(client.tag(frozen["config"]["model"])["digest"] == expected_digest,
                "응답 후 모델 태그 digest가 바뀌었습니다.")
        if record["status"] == "harness_error":
            stop_code = 2
    except APIError as exc:
        # 통신 실패 뒤 즉시 다음 추론을 시작하면 서버에 남은 작업과 겹칠 수 있어 중단한다.
        record.update(status="transport_error", error=str(exc))
        if record["wall_seconds"] is None:
            record["wall_seconds"] = exc.elapsed_seconds
        record["transport_response_text"] = exc.response_text
        stop_code = 2
    except KeyboardInterrupt:
        record.update(status="interrupted", error="사용자가 중단함. 서버 추론 취소까지 보장하지 않음")
        if record["wall_seconds"] is None:
            record["wall_seconds"] = time.perf_counter() - start
        stop_code = 130
    except Exception as exc:
        record.update(status="harness_error", error=f"{type(exc).__name__}: {exc}")
        stop_code = 2
    save_record(folder, record)
    return record, stop_code


def run(core: Any, core_info: dict, plan: dict, config: dict, out: Path,
        resume: bool = False, gate: Path | None = None) -> int:
    check = selfcheck(core)
    if gate is not None:
        validate_gate(core, gate, config, plan)
    client = OllamaClient(config["endpoint"], config["timeout_seconds"])
    # 추론 없이 버전·모델 설치 상태부터 확인한다.
    metadata = client.inspect(config["model"])
    env = environment()
    if gate is not None:
        gate_manifest = read_json(gate / "manifest.json")
        require(gate_manifest["frozen"]["model"]["digest"] == metadata["tag"]["digest"],
                "게이트 통과 후 모델 digest가 달라졌습니다. 같은 모델로 smoke를 다시 실행하세요.")
        require(gate_manifest["frozen"]["ollama_server"] == metadata["server"],
                "게이트 통과 후 Ollama 버전이 달라졌습니다. 같은 환경으로 smoke를 다시 실행하세요.")
    frozen = {"extension_version": __version__, "plan": plan, "config": config,
              "core": core_info, "runtime_sources_sha256": source_fingerprint(),
              "runtime": {"python": platform.python_version(), "os": platform.platform(),
                          "nvidia_smi": env["nvidia_smi"]},
              "model": {"name": config["model"], "digest": metadata["tag"]["digest"],
                        "details": metadata["tag"]["details"], "show_sha256": digest(metadata["show"])},
              "ollama_server": metadata["server"]}
    out = out.resolve()
    if out.exists():
        require(out.is_dir(), "결과 경로가 디렉터리가 아닙니다.")
        require(resume or not any(out.iterdir()), "비어 있지 않은 결과 폴더입니다. "
                "새 폴더를 사용하거나 동일 설정으로 --resume 하세요.")
    else:
        require(not resume, "--resume 할 결과 폴더가 없습니다.")
        out.mkdir(parents=True)
    with run_lock(out):
        if resume:
            require((out / "manifest.json").is_file(), "manifest 없는 결과 폴더는 이어갈 수 없습니다.")
            manifest = read_json(out / "manifest.json")
            require(manifest["run_sha256"] == digest(frozen) and manifest["frozen"] == frozen,
                    "모델·서버·소스·문제·시드·설정 중 하나가 바뀌었습니다. 기존 실험에 섞지 말고 새 폴더를 쓰세요.")
        else:
            manifest = {"format_version": 2, "created_at": utc_now(), "run_sha256": digest(frozen),
                        "frozen": frozen, "environment": env, "ollama_metadata": metadata,
                        "source_status_at_delivery": "OFFLINE_TESTED_LLM_NOT_RUN",
                        "offline_preflight": check,
                        "gate_run_sha256": (read_json(gate / "manifest.json")["run_sha256"] if gate else None)}
            write_json(out / "manifest.json", manifest)
            write_text(out / ".gitignore", "*\n!.gitignore\n")
            snapshot = out / "source_snapshot"
            snapshot.mkdir()
            for source in PACKAGE.glob("*.py"):
                shutil.copyfile(source, snapshot / source.name)
            shutil.copyfile(REPO / "adm_minimal.py", snapshot / "adm_minimal.py")
        existing = {r["case"]["case_id"]: r for r in read_records(out, manifest)}
        if any(r["status"] == "harness_error" for r in existing.values()):
            raise ContractError("기존 실험에 하네스 오류가 있습니다. 원인을 수정한 후 새 결과 폴더에서 시작하세요.")
        problems = {p["id"]: p for p in plan["problems"]}
        try:
            for index, case in enumerate(plan["cases"], 1):
                if case["case_id"] in existing:
                    continue
                folder = out / "cases" / case["case_id"]
                problem = problems[case["problem_id"]]
                recovered = recover_case(core, folder, manifest, problem, case) if resume else None
                if recovered is not None:
                    record = recovered
                    stop_code = 2 if record["status"] == "harness_error" else None
                else:
                    record, stop_code = _perform_case(core, client, manifest, case, problem, folder)
                print(f"[{index}/{len(plan['cases'])}] {case['problem_id']} / {case['role_id']} / "
                      f"seed={case['seed']} -> {record['status']}", flush=True)
                if record.get("error"):
                    print("  " + record["error"], flush=True)
                write_report(out)
                if stop_code is not None:
                    return stop_code
        except KeyboardInterrupt:
            write_report(out)
            return 130
        finally:
            # 미시작 조건도 분모에 남긴다. 파일 손상은 집계 과정에서 오류로 드러난다.
            write_report(out)
    summary = write_report(out)
    print(f"결과: {out / 'summary.md'}")
    return 0 if summary["all_assigned_passed"] else 1


def validate_gate(core: Any, gate: Path, config: dict, next_plan: dict) -> None:
    """summary의 PASS 글자를 믿지 않고 보존 응답 전부를 다시 검사한다. 네트워크 없음."""
    manifest = read_json(gate / "manifest.json")
    frozen = manifest["frozen"]
    previous = frozen["plan"]
    require(previous["profile"] == "smoke" and previous.get("experiment_kind", "joint") == "joint",
            "pilot/full 게이트에는 v0.2 smoke 결과 폴더를 지정하세요.")
    require(frozen["config"] == config, "smoke와 모델·추론·샘플링 설정이 다릅니다.")
    require(frozen["runtime_sources_sha256"] == source_fingerprint(), "smoke 이후 런타임 소스가 변경되었습니다.")
    require(frozen["core"]["sha256"] == bytes_hash(Path(core.__file__).read_bytes()), "smoke와 검증기가 다릅니다.")
    require(previous["seed"] == next_plan["seed"], "smoke와 주 실험의 시작 시드가 다릅니다.")
    require(previous["problems"] == next_plan["problems"][:1], "smoke는 주 실험의 첫 문제와 같아야 합니다.")
    records = read_records(gate, manifest)
    require(len(records) == len(previous["cases"]), "smoke가 완료되지 않았습니다.")
    problems = {p["id"]: p for p in previous["problems"]}
    for record in records:
        case = record["case"]
        folder = gate / "cases" / case["case_id"]
        require((folder / "response.raw.json").is_file(), "smoke 응답 누락")
        problem = problems[case["problem_id"]]
        expected = request_body(config, case, problem)
        saved_request = read_json(folder / "request.json")
        require(saved_request["body"] == expected, "smoke 요청 내용 변경")
        require((folder / "request.wire.json").is_file()
                and (folder / "request.wire.json").read_bytes() == wire_json(expected).encode("utf-8"),
                "smoke HTTP 원문 누락/변경")
        response = read_json(folder / "response.raw.json")
        outcome, _ = assess_response(core, problem, case, previous["reference_depths"][problem["id"]],
                                     expected, response)
        require(outcome["status"] == "accepted", "smoke에 실패 조건이 있습니다. 추가 대량 실행 전에 원인을 확인하세요.")
