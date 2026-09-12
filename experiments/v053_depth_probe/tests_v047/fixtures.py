"""합성 자료임을 manifest에 명시하는 로컬 HTTP 시험 서버."""
from __future__ import annotations
import copy
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from paired_probe_v047.contracts import EXPRS, SCHEMA, SYSTEM, digest, strict_json, wire, write_json

MODEL = "test-only:4b-instruct"
MODEL_DIGEST = "d" * 64
SHOW = {"details": {"family": "fixture", "parameter_size": "4.0B", "quantization_level": "Q4_K_M"},
        "template": "SYNTHETIC NON-THINKING FIXTURE", "parameters": "temperature 0", "model_info": {}}
SERVER = {"version": "test-fixture-0.0"}
TRUTH = {(False, False): False, (False, True): False, (True, False): True, (True, True): False}
AND = {(False, False): False, (False, True): False, (True, False): False, (True, True): True}


def envelope(value=False, *, content=None, model=MODEL):
    return {"model": model, "created_at": "2026-09-11T00:00:00Z",
            "message": {"role": "assistant", "content": wire({"value": value}).decode() if content is None else content},
            "done": True, "done_reason": "stop", "total_duration": 1000000, "load_duration": 0,
            "prompt_eval_count": 120, "prompt_eval_cached_count": 20, "prompt_eval_duration": 500000,
            "eval_count": 5, "eval_duration": 500000}


def baseline(root: Path, endpoint="http://127.0.0.1:11434", *, contract="composition-v046") -> Path:
    path = root / ("v046_fixture" if contract == "composition-v046" else "v045_fixture")
    path.mkdir(parents=True)
    config = {"endpoint": endpoint, "model": MODEL, "timeout_seconds": 5,
              "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 4096, "top_k": 20, "top_p": 0.8},
              "think": None, "mode_policy": {"resolved_mode": "non-thinking"}}
    cases = []
    for a, b in TRUTH:
        key = str(int(a)) + str(int(b)); case_id = "fixture_" + key
        case = {"case_id": case_id, "seed": 1729}
        if contract == "composition-v046":
            case.update(arm="commuted", original_input={"a": a, "b": b})
            expression = EXPRS["commuted"]
        else:
            case.update(operation="and_not_b", input_literals={"a": a, "b": b}, format_mode="schema")
            expression = EXPRS["original"]
        body = {"model": MODEL, "messages": [{"role": "system", "content": SYSTEM},
                   {"role": "user", "content": "input: " + wire({"a": a, "b": b, "expression": expression}).decode("utf-8")}],
                "stream": False, "keep_alive": "10m", "options": dict(config["options"], seed=1729),
                "format": copy.deepcopy(SCHEMA)}
        folder = path / "cases" / case_id; folder.mkdir(parents=True)
        (folder / "request.wire.json").write_bytes(wire(body)); cases.append(case)
    frozen = {"config": config, "model": {"digest": MODEL_DIGEST, "show_sha256": digest(SHOW)},
              "ollama_server": SERVER, "plan": {"probe_contract": contract, "cases": cases},
              "evidence_kind": "synthetic_fixture"}
    write_json(path / "manifest.json", {"frozen": frozen, "run_sha256": digest(frozen)})
    return path


class State:
    def __init__(self, mode="perfect"):
        self.mode = mode; self.requests = []; self.show_calls = 0


@contextmanager
def fake_server(mode="perfect"):
    state = State(mode)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def send(self, data, status=200):
            raw = wire(data)
            self.send_response(status); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
        def do_GET(self):
            if self.path == "/api/version":
                self.send(SERVER)
            elif self.path == "/api/tags":
                self.send({"models": [{"name": MODEL, "model": MODEL, "digest": MODEL_DIGEST,
                                      "details": SHOW["details"]}]})
            else:
                self.send({"error": "missing"}, 404)
        def do_POST(self):
            body = strict_json(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/api/show":
                state.show_calls += 1
                show = copy.deepcopy(SHOW)
                if state.mode == "runtime_drift" and state.show_calls > 1:
                    show["template"] = "CHANGED"
                self.send(show); return
            if self.path != "/api/chat":
                self.send({"error": "missing"}, 404); return
            state.requests.append(body)
            if state.mode == "http_error":
                self.send({"error": "synthetic transport failure"}, 503); return
            values = strict_json(body["messages"][1]["content"][7:])
            a, b, expr = values["a"], values["b"], values["expression"]
            value = (not b if expr == EXPRS["not"] else AND[a, b] if expr == EXPRS["and"] else TRUTH[a, b])
            if state.mode == "original_false" and expr == EXPRS["original"]:
                value = False
            if state.mode == "wrong_not" and expr == EXPRS["not"]:
                value = b
            content = None
            if state.mode == "invalid_not" and expr == EXPRS["not"]:
                content = '{"value":"false"}'
            result = envelope(value, content=content)
            if state.mode == "wrong_model":
                result["model"] = "another-model"
            self.send(result)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    worker.start()
    try:
        yield state, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown(); server.server_close(); worker.join(timeout=2)
