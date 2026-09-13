"""Ollama 실행기. 정답 계산·재시도·오답 보정은 하지 않는다."""
from __future__ import annotations
import json
import os
import platform
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from .contracts import (MAX_BYTES, ContractError, b64, decode_response, digest,
                        read_json, require, sha, source_fingerprint, strict_json,
                        utc_now, wire, write_json)
from .plan import make_request, slots, validate_plan

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def endpoint_base(endpoint: str) -> str:
    require(isinstance(endpoint, str), "endpoint 문자열 필요")
    parsed = urllib.parse.urlsplit(endpoint)
    require(parsed.scheme in ("http", "https") and parsed.hostname in ("localhost", "127.0.0.1", "::1"),
            "이 모듈은 로컬 loopback Ollama만 호출합니다.")
    require(not parsed.username and not parsed.password and not parsed.query and not parsed.fragment,
            "endpoint 인증정보/쿼리/fragment 금지")
    require(parsed.path.rstrip("/") in ("", "/api/chat"), "Ollama base URL 또는 /api/chat만 허용")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))

class OllamaHTTP:
    def __init__(self, endpoint: str, timeout: float):
        self.base = endpoint_base(endpoint)
        require(type(timeout) in (int, float) and 0 < timeout <= 3600, "timeout 범위 오류")
        self.timeout = timeout
        # 사용자 프록시나 HTTP redirect로 외부 주소로 전송되지 않도록 한다.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, path: str, body: bytes | None = None) -> dict:
        started = time.perf_counter_ns()
        request = urllib.request.Request(self.base + path, data=body,
                                          headers={"Content-Type": "application/json"},
                                          method="POST" if body is not None else "GET")
        code = 0; raw = b""; error = None
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                code = response.status
                raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raw = raw[:MAX_BYTES]
                error = "response_size_limit_exceeded"
        except urllib.error.HTTPError as exc:
            code = exc.code
            raw = exc.read(MAX_BYTES)
            error = f"HTTP {exc.code}"
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            error = type(exc).__name__ + ": " + str(exc)
        return {"http_status": code, "raw": raw, "error": error,
                "elapsed_ns": time.perf_counter_ns() - started}

    def metadata(self, model: str) -> dict:
        raw_data = {}; data = {}
        for name, path, body in (("server", "/api/version", None), ("tags", "/api/tags", None),
                                 ("show", "/api/show", wire({"model": model}))):
            result = self.request(path, body)
            require(result["http_status"] == 200 and result["error"] is None,
                    "추론 전/후 Ollama 메타데이터 확인 실패: " + name + ": " + str(result["error"]))
            raw_data[name] = b64(result["raw"])
            data[name] = strict_json(result["raw"])
        return {"at": utc_now(), "raw_b64": raw_data, "data": data}


def check_identity(metadata: dict, baseline: dict) -> dict:
    from .contracts import unb64
    for key in ("server", "tags", "show"):
        require(strict_json(unb64(metadata["raw_b64"][key])) == metadata["data"][key],
                "메타데이터 원문과 해석값 불일치")
    data = metadata["data"]; model = baseline["config"]["model"]
    tags = data["tags"]["models"]
    matches = [t for t in tags if t.get("name") == model or t.get("model") == model]
    require(len(matches) == 1, "원래 모델 태그가 없거나 중복입니다: " + model)
    require(matches[0]["digest"] == baseline["model"]["digest"], "기준선과 모델 digest가 다릅니다.")
    require(digest(data["show"]) == baseline["model"]["show_sha256"], "기준선과 모델 템플릿/정보가 다릅니다.")
    server = data["server"]
    expected = baseline["server"]
    require((server.get("version") if isinstance(expected, str) else server) == expected,
            "기준선과 Ollama 서버 버전이 다릅니다.")
    return {"model": model, "digest": matches[0]["digest"], "show_sha256": digest(data["show"]),
            "server": server, "details": matches[0].get("details")}


def execute(plan_path: Path, out: Path) -> dict:
    plan = read_json(plan_path); validate_plan(plan)
    require(not out.exists(), "기존 결과 폴더는 덮어쓰지 않습니다: " + str(out))
    baseline = plan["baseline"]; config = baseline["config"]
    http = OllamaHTTP(config["endpoint"], config.get("timeout_seconds", 180))
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "plan.snapshot.json", plan, exclusive=True)
    snapshot = out / "source_snapshot"; snapshot.mkdir()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        (snapshot / path.name).write_bytes(path.read_bytes())
    write_json(out / "run_manifest.json", {"plan_sha256": plan["plan_sha256"], "started_at": utc_now(),
        "source_fingerprint": source_fingerprint(), "python": sys.version,
        "platform": platform.platform(), "executable": sys.executable,
        "endpoint": http.base, "evidence_kind": baseline["evidence_kind"],
        "new_model_inference": baseline["evidence_kind"] != "synthetic_fixture",
        "retry_policy": "none", "warmup_calls": 0,
        "source_plan_path": str(plan_path.resolve()), "max_inference_calls": plan["max_calls"]}, exclusive=True)
    status = {"state": "running", "complete": False, "recorded_slots": 0, "inference_calls": 0,
              "event_tip": plan["plan_sha256"], "runtime_identity_verified": False, "error": None}
    write_json(out / "status.json", status)
    parent_cache = {}
    event_path = out / "events.jsonl"
    with event_path.open("xb") as event_stream:
        def append(event):
            event["previous_hash"] = status["event_tip"]
            event["event_hash"] = digest(event)
            event_stream.write(wire(event) + b"\n"); event_stream.flush(); os.fsync(event_stream.fileno())
            status["event_tip"] = event["event_hash"]
            status["recorded_slots"] += 1
            write_json(out / "status.json", status)
        try:
            before = http.metadata(config["model"])
            write_json(out / "runtime.before.json", before, exclusive=True)
            check_identity(before, baseline)
            all_slots = slots(plan)
            for index, slot in enumerate(all_slots):
                event = {"slot": slot, "at": utc_now(), "parent": None}
                parent_value = None
                if slot["stage"] == "and":
                    parent = parent_cache[slot["block_id"]]
                    event["parent"] = {"id": parent["id"], "response_sha256": parent["response_sha256"]}
                    if parent["value"] is None:
                        event.update(kind="blocked", reason="parent_has_no_valid_boolean")
                        append(event)
                        continue
                    parent_value = parent["value"]  # 오답 bool도 그대로 전달한다.
                request_raw = make_request(plan, slot, parent_value)
                folder = out / "calls" / slot["id"]; folder.mkdir(parents=True)
                (folder / "request.wire.json").write_bytes(request_raw)
                print(f'[{index + 1}/{len(all_slots)}] {slot["id"]}', flush=True)
                status["inference_calls"] += 1
                result = http.request("/api/chat", request_raw)
                (folder / "response.raw.json").write_bytes(result["raw"])
                event.update(kind="call", request_sha256=sha(request_raw), response_sha256=sha(result["raw"]),
                             http_status=result["http_status"], transport_error=result["error"],
                             elapsed_ns=result["elapsed_ns"])
                append(event)
                if slot["stage"] == "not":
                    value = None
                    if result["http_status"] == 200 and result["error"] is None:
                        try:
                            value = decode_response(result["raw"], config["model"])["value"]
                        except ContractError:
                            pass
                    parent_cache[slot["block_id"]] = {"id": slot["id"], "value": value,
                                                     "response_sha256": event["response_sha256"]}
                # 형식 실패/모델 오답은 계속 수집한다. 인프라 실패는 재시도 없이 중단한다.
                if result["http_status"] != 200 or result["error"] is not None:
                    raise ContractError("인프라 오류로 미완료 종료. 자동 재시도하지 않음: " + str(result["error"]))
            after = http.metadata(config["model"])
            write_json(out / "runtime.after.json", after, exclusive=True)
            check_identity(after, baseline)
            status.update(state="complete", complete=True, runtime_identity_verified=True)
        except KeyboardInterrupt:
            status.update(state="interrupted", error="사용자가 실행을 중단했습니다.")
        except (ContractError, KeyError, TypeError, OSError, ValueError) as exc:
            status.update(state="incomplete", error=type(exc).__name__ + ": " + str(exc))
        finally:
            status["finished_at"] = utc_now()
            write_json(out / "status.json", status)
    # 모든 요청이 끝난 뒤에만 오프라인 채점기를 불러온다.
    from .audit import audit_run
    return audit_run(plan_path, out, write_report=True)
