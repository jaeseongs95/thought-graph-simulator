"""표준 라이브러리만 쓰는 로컬 Ollama 클라이언트. 재시도·다운로드·도구 실행 없음."""
from __future__ import annotations

import ipaddress
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .common import MAX_JSON_BYTES, ContractError, wire_json, require, strict_json


class APIError(RuntimeError):
    def __init__(self, message: str, *, response_text: str | None = None,
                 elapsed_seconds: float | None = None):
        super().__init__(message)
        self.response_text = response_text
        self.elapsed_seconds = elapsed_seconds


@dataclass
class Reply:
    value: dict
    text: str
    elapsed_seconds: float


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        raise APIError(f"HTTP 리다이렉트 금지: {code}")


def local_endpoint(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    require(parsed.scheme == "http", "로컬 API 주소는 http만 허용합니다.")
    require(not parsed.username and not parsed.password and not parsed.query
            and not parsed.fragment and parsed.path in {"", "/"},
            "API 주소에 인증정보·경로·쿼리·fragment를 넣을 수 없습니다.")
    host = parsed.hostname or ""
    if host == "localhost":
        host = "127.0.0.1"  # DNS/hosts 설정에 의존하지 않는다.
    try:
        address = ipaddress.ip_address(host)
        port = parsed.port or 11434
    except ValueError as exc:
        raise ContractError("숫자로 된 루프백 주소 또는 localhost만 허용합니다.") from exc
    require(address.is_loopback and 1 <= port <= 65535, "루프백 API 주소만 허용합니다.")
    host_text = f"[{address}]" if address.version == 6 else str(address)
    return f"http://{host_text}:{port}"


def reject_remote_metadata(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in {"remote_host", "remote_model", "remote_url", "cloud_model"}:
                require(not item, "클라우드/원격 모델 메타데이터를 발견했습니다.")
            reject_remote_metadata(item)
    elif isinstance(value, list):
        for item in value:
            reject_remote_metadata(item)


class OllamaClient:
    def __init__(self, endpoint: str = "http://127.0.0.1:11434", timeout: float = 300):
        require(0 < timeout <= 3600, "타임아웃은 0초 초과 3600초 이하이어야 합니다.")
        self.endpoint = local_endpoint(endpoint)
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, path: str, body: dict | None = None) -> Reply:
        allowed = {"/api/version", "/api/tags", "/api/show", "/api/ps", "/api/chat"}
        require(path in allowed, "허용하지 않은 API 경로")
        request = urllib.request.Request(
            self.endpoint + path,
            data=wire_json(body).encode("utf-8") if body is not None else None,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST" if body is not None else "GET",
        )
        start = time.perf_counter()
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(MAX_JSON_BYTES + 1)
            require(len(raw) <= MAX_JSON_BYTES, "Ollama 응답 크기 제한 초과")
            text = raw.decode("utf-8")
            value = strict_json(text)
            require(isinstance(value, dict), "Ollama 응답 객체 필요")
            if value.get("error"):
                raise APIError(str(value["error"]), response_text=text)
            return Reply(value, text, time.perf_counter() - start)
        except urllib.error.HTTPError as exc:
            text = exc.read(MAX_JSON_BYTES).decode("utf-8", errors="replace")
            raise APIError(f"Ollama HTTP {exc.code}: {text[:2000]}", response_text=text,
                           elapsed_seconds=time.perf_counter() - start) from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError,
                UnicodeError, ContractError) as exc:
            raise APIError(f"Ollama 통신/응답 오류: {exc}",
                           elapsed_seconds=time.perf_counter() - start) from exc
        except APIError as exc:
            exc.elapsed_seconds = time.perf_counter() - start
            raise

    def tag(self, model: str) -> dict:
        require(isinstance(model, str) and bool(model) and "cloud" not in model.lower(),
                "로컬 모델 이름만 허용합니다.")
        tags = self.request("/api/tags").value
        entries = [item for item in tags.get("models", [])
                   if item.get("name") == model or item.get("model") == model]
        require(len(entries) == 1,
                f"로컬에 {model} 모델이 없거나 이름이 모호합니다. 먼저 사용자가 직접 "
                f"`ollama pull {model}`을 실행하고 정확한 태그를 사용하세요. 자동 다운로드는 하지 않습니다.")
        entry = entries[0]
        reject_remote_metadata(entry)
        require(bool(entry.get("digest")), "모델 digest 누락")
        require(entry.get("details", {}).get("format") == "gguf", "로컬 GGUF 모델만 지원합니다.")
        return entry

    def inspect(self, model: str) -> dict:
        version = self.request("/api/version").value
        entry = self.tag(model)
        show = self.request("/api/show", {"model": model, "verbose": False}).value
        reject_remote_metadata(show)
        require(show.get("details", {}).get("format") == "gguf", "로컬 GGUF 모델 정보가 아닙니다.")
        require("completion" in show.get("capabilities", []), "텍스트 생성 capability가 없습니다.")
        return {"server": version, "tag": entry, "show": show,
                "running_models": self.request("/api/ps").value}

    def running_model(self, model: str) -> dict | None:
        entries = self.request("/api/ps").value.get("models", [])
        return next((item for item in entries if item.get("name") == model
                     or item.get("model") == model), None)

    def chat(self, body: dict) -> Reply:
        return self.request("/api/chat", body)
