"""엄격한 JSON, 원자적 파일 기록, 기존 검증기 연결."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parent
BASE_COMMIT = "254757486a987475d16541cf84b905d684c1c13d"
BASE_CORE_BLOB = "b7aa0b58b9257fdb80882b48e4ecf1006ac4ff45"
MAX_JSON_BYTES = 4 * 1024 * 1024


class ContractError(ValueError):
    """입력·실험 계약 오류. 모델 실패와 구분한다."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def wire_json(value: Any) -> str:
    """HTTP/프롬프트 직렬화. 해시용 canonical()과 달리 삽입 순서를 보존한다."""
    return json.dumps(value, ensure_ascii=False, sort_keys=False,
                      separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def bytes_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    """Git blob object id for the supplied bytes, without invoking Git."""
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def normalize_python_source_bytes(data: bytes) -> bytes:
    """Normalize only UTF-8 BOM and text line endings for Python-source identity.

    This is intentionally narrow. It does not trim whitespace, reformat code, or
    alter any non-line-ending content. A real source edit therefore remains a
    different identity.
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ContractError("Python 소스를 UTF-8로 해석할 수 없습니다.") from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.encode("utf-8")


def source_text_identity(data: bytes) -> dict:
    """Return raw and line-ending/BOM-normalized identities for source bytes."""
    normalized = normalize_python_source_bytes(data)
    return {
        "sha256": bytes_hash(data),
        "git_blob_sha1": git_blob_sha1(data),
        "normalized_sha256": bytes_hash(normalized),
        "normalized_git_blob_sha1": git_blob_sha1(normalized),
        "normalization_changed_bytes": data != normalized,
    }


def core_identity_compatibility(recorded: dict, current: dict) -> dict:
    """Compare core source identity without treating CRLF/LF/BOM as a code edit.

    Existing manifests (v0.4.4 and earlier) contain raw ``sha256`` and
    ``git_blob_sha1`` fields only. Their recorded source snapshots were LF, so the
    legacy git blob is also the normalized blob. New identities additionally carry
    explicit normalized fields.
    """
    recorded_blob = recorded.get("normalized_git_blob_sha1") or recorded.get("git_blob_sha1")
    current_blob = current.get("normalized_git_blob_sha1") or current.get("git_blob_sha1")
    method = "normalized_git_blob_sha1" if recorded_blob and current_blob else "sha256"
    if recorded_blob and current_blob:
        same = recorded_blob == current_blob
    else:
        same = recorded.get("sha256") == current.get("sha256")
    return {
        "same_source": bool(same),
        "method": method,
        "recorded_identity": recorded_blob if method != "sha256" else recorded.get("sha256"),
        "current_identity": current_blob if method != "sha256" else current.get("sha256"),
        "raw_sha256_equal": recorded.get("sha256") == current.get("sha256"),
        "representation_diff_only": bool(same) and recorded.get("sha256") != current.get("sha256"),
    }


def require_core_compatible(recorded: dict, current: dict, message: str) -> dict:
    result = core_identity_compatibility(recorded, current)
    require(result["same_source"], message)
    return result


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        require(key not in result, f"JSON 중복 키: {key}")
        result[key] = value
    return result


def _bad_constant(value: str) -> None:
    raise ContractError(f"비표준 JSON 숫자 금지: {value}")


def _finite_float(text: str) -> float:
    value = float(text)
    require(math.isfinite(value), "JSON 실수 범위 초과")
    return value


def strict_json(text: str) -> Any:
    require(isinstance(text, str), "JSON 입력은 문자열이어야 합니다.")
    require(len(text.encode("utf-8")) <= MAX_JSON_BYTES, "JSON 크기 제한 초과")
    try:
        return json.loads(text, object_pairs_hook=_unique_object,
                          parse_constant=_bad_constant, parse_float=_finite_float)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ContractError(f"엄격한 JSON 해석 실패: {exc}") from exc


def read_json(path: Path) -> Any:
    require(path.stat().st_size <= MAX_JSON_BYTES, f"파일 크기 제한 초과: {path}")
    return strict_json(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    """같은 디렉터리에서 교체. 이미 있는 실험 결과의 재사용 판단은 호출자가 한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def source_fingerprint() -> dict[str, str]:
    # 실험 결과를 바꿀 수 있는 런타임 소스만 동결한다. 테스트·문서는 별도 배포 해시 대상.
    return {p.name: bytes_hash(p.read_bytes()) for p in sorted(PACKAGE.glob("*.py"))}


def load_core(allow_change: bool = False) -> tuple[ModuleType, dict]:
    path = REPO / "adm_minimal.py"
    require(path.is_file(), "저장소 루트의 adm_minimal.py가 없습니다. local_llm 폴더를 "
            "기존 thought-graph-simulator의 adm_minimal.py 옆에 놓으세요.")
    data = path.read_bytes()
    identity = source_text_identity(data)
    matching = identity["normalized_git_blob_sha1"] == BASE_CORE_BLOB
    require(matching or allow_change,
            "adm_minimal.py가 확인한 기준 파일과 다릅니다. 변경 내용을 검토한 후 "
            "--allow-core-change를 명시해야 실행할 수 있습니다.")
    spec = importlib.util.spec_from_file_location("_adm_local_baseline", path)
    require(spec is not None and spec.loader is not None, "기존 모듈을 불러올 수 없습니다.")
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    for name in ("verify", "check_problem", "digest"):
        require(callable(getattr(core, name, None)), f"기존 모듈 API 누락: {name}")
    return core, {"path": "adm_minimal.py", **identity,
                  "baseline_matches": matching,
                  "baseline_commit": BASE_COMMIT,
                  "allow_core_change": allow_change}


def write_text(path: Path, text: str) -> None:
    """API 원문 등의 UTF-8 텍스트를 원자적으로 저장한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
