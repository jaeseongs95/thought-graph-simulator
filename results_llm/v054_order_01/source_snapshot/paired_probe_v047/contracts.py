"""직렬화·원문 응답 계약. 정답표나 정답 보정 기능은 없다."""
from __future__ import annotations
import base64
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_BYTES = 8 * 1024 * 1024
SCHEMA = {"type": "object", "properties": {"value": {"type": "boolean"}},
          "required": ["value"], "additionalProperties": False}
EXPRS = {"original": "(a AND (NOT b))", "commuted": "((NOT b) AND a)",
         "not": "(NOT b)", "and": "(a AND b)"}
# v0.4.5 operator_probe.make_request와 같은 문구·키 순서.
SYSTEM = ('입력의 a와 b는 불리언이다. expression의 식 하나만 계산해 value에 기록한다.\n'
          'AND는 두 피연산자가 모두 true일 때 true다. NOT은 true와 false를 뒤집는다. '
          '괄호 안의 연산을 먼저 적용한다.\n'
          'JSON 객체 하나만 출력한다. 다음 스키마는 자료형만 제한하며 정답을 지정하지 않는다.\n'
          + json.dumps(SCHEMA, ensure_ascii=False, separators=(",", ":")))

class ContractError(ValueError):
    """모델 오답과 구분하는 자료·실행 계약 오류."""

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ContractError(message)

def strict_json(data: str | bytes) -> Any:
    require(isinstance(data, (str, bytes)), "JSON 문자열/바이트가 필요합니다.")
    require(len(data) <= MAX_BYTES, "JSON 크기 한도를 넘었습니다.")
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "중복 JSON 키: " + key)
            result[key] = value
        return result
    def invalid(value):
        raise ContractError("비유한 JSON 숫자: " + value)
    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise ContractError("엄격한 JSON 해석 실패: " + str(exc)) from exc

def wire(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")

def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def digest(value: Any) -> str:
    return sha(canonical(value))

def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")

def unb64(text: str) -> bytes:
    try:
        return base64.b64decode(text, validate=True)
    except (ValueError, TypeError) as exc:
        raise ContractError("원문 base64 오류") from exc

def read_json(path: Path) -> Any:
    return strict_json(path.read_bytes())

def write_json(path: Path, value: Any, *, exclusive: bool = False) -> None:
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb" if exclusive else "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

def source_fingerprint() -> dict:
    root = Path(__file__).resolve().parent
    # Windows의 CRLF/LF·BOM만 정규화한다. 공백이나 코드 내용 변경은 허용하지 않는다.
    result = {}
    for path in sorted(root.glob("*.py")):
        data = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        result[path.name] = sha(data.encode("utf-8"))
    return result

def decode_response(raw: bytes, model: str) -> dict:
    """정상 종료·non-thinking·엄격한 bool만 확인한다. 참/거짓 정답은 모른다."""
    obj = strict_json(raw)
    require(isinstance(obj, dict), "응답 봉투가 객체가 아닙니다.")
    require(obj.get("model") == model, "응답 모델 이름 불일치")
    require(obj.get("done") is True and obj.get("done_reason") == "stop", "정상 stop 종료가 아닙니다.")
    message = obj.get("message")
    require(isinstance(message, dict) and message.get("role") == "assistant", "assistant 응답이 아닙니다.")
    require(not message.get("tool_calls") and not message.get("images"), "도구/이미지 응답은 허용하지 않습니다.")
    thinking = message.get("thinking")
    require(thinking is None or (isinstance(thinking, str) and not thinking.strip()),
            "non-thinking 계약과 다른 thinking 응답")
    content = message.get("content")
    require(isinstance(content, str) and "<think>" not in content and "</think>" not in content,
            "content 문자열/생각 채널 계약 위반")
    payload = strict_json(content)
    require(isinstance(payload, dict) and set(payload) == {"value"} and type(payload["value"]) is bool,
            '정확히 {"value": boolean}만 허용합니다.')
    return {"value": payload["value"], "envelope": obj, "content": content}

def usage(raw: bytes) -> dict:
    """서버 측 측정값은 누락·오류를 0으로 위장하지 않는다."""
    keys = ("prompt_eval_count", "prompt_eval_cached_count", "eval_count", "total_duration",
            "load_duration", "prompt_eval_duration", "eval_duration")
    try:
        obj = strict_json(raw)
        if not isinstance(obj, dict):
            return {key: None for key in keys}
        return {key: obj[key] if type(obj.get(key)) is int and obj[key] >= 0 else None for key in keys}
    except ContractError:
        return {key: None for key in keys}
