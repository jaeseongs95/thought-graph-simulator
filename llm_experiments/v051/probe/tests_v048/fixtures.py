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
              "options": {"temperature": 0.7, "num_ctx": 8192, "num_predict": 4096, "top_k": 20, "top_p": 0.8},
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
        self.mode = mode; self.requests = []; self.show_calls = 0; self.counts = {}; self.metadata_boundary = 0


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
                self.send({"models": [{"name": MODEL, "model": MODEL, "digest": ("x" * 64 if state.mode == "before_identity_error" else MODEL_DIGEST),
                                      "details": SHOW["details"]}]})
            else:
                self.send({"error": "missing"}, 404)
        def do_POST(self):
            body = strict_json(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/api/show":
                state.show_calls += 1
                show = copy.deepcopy(SHOW)
                if state.mode == "runtime_drift" and state.show_calls > state.metadata_boundary + 1:
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
            if state.mode in ("original_false", "missing_usage", "seed_sensitive", "repeat_unstable") and expr == EXPRS["original"]:
                value = False
            if state.mode == "wrong_not" and expr == EXPRS["not"]:
                value = b
            if state.mode == "seed_sensitive" and body["options"]["seed"] % 2 and expr == EXPRS["original"]:
                value = TRUTH[a, b]
            if state.mode == "repeat_unstable" and expr == EXPRS["original"]:
                key = wire(body)
                state.counts[key] = state.counts.get(key, 0) + 1
                if state.counts[key] % 2 == 0:
                    value = TRUTH[a, b]
            content = None
            if state.mode == "invalid_not" and expr == EXPRS["not"]:
                content = '{"value":"false"}'
            result = envelope(value, content=content)
            if state.mode == "wrong_model":
                result["model"] = "another-model"
            if state.mode == "missing_usage":
                result.pop("prompt_eval_count", None)
                result.pop("prompt_eval_cached_count", None)
            if state.mode == "truncated":
                result["done_reason"] = "length"
            self.send(result)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    worker.start()
    try:
        yield state, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown(); server.server_close(); worker.join(timeout=2)


def build_v047(root: Path, endpoint: str):
    """고정 v047 실행기로 합성 기준선을 만든다. 새로운 모델 증거로 쓰지 않는다."""
    import contextlib
    import io
    from paired_probe_v047.plan import prepare
    from paired_probe_v047.runner import execute
    source = baseline(root, endpoint)
    path = root / "v047.external.plan.json"
    prepare(root, path, source_run=source, cycles=1)
    out = root / "v047.run"
    with contextlib.redirect_stdout(io.StringIO()):
        execute(path, out)
    return path, out


@contextmanager
def experiment(mode="perfect", *, seeds=None, cycles=6):
    import contextlib
    import io
    import tempfile
    from paired_probe_v048.plan import prepare
    from paired_probe_v048.runner import execute
    with tempfile.TemporaryDirectory() as temp, fake_server() as (state, endpoint):
        root = Path(temp)
        old_plan, old_run = build_v047(root, endpoint)
        state.requests.clear(); state.mode = mode; state.metadata_boundary = state.show_calls
        path = root / "v048.external.plan.json"
        plan = prepare(old_run, path, baseline_plan=old_plan, seeds=[101] if seeds is None else seeds, cycles=cycles)
        out = root / "v048.run"
        with contextlib.redirect_stdout(io.StringIO()):
            report = execute(path, out)
        yield root, state, path, plan, out, report
