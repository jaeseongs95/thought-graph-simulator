"""Windows를 포함한 subprocess 텍스트 캡처를 바이트 경계에서 안전하게 처리한다.

실험 원문/JSON 저장 인코딩은 UTF-8을 유지한다. 이 모듈은 selftest와 검증 스크립트가
자식 프로세스 stdout/stderr를 읽는 경계만 담당한다.
"""
from __future__ import annotations

import locale
import os
import subprocess
from dataclasses import dataclass
from typing import Mapping, Sequence


class SubprocessDecodeError(UnicodeError):
    """텍스트로 기대한 subprocess 출력이 허용 인코딩으로 해석되지 않을 때 발생."""


@dataclass(frozen=True)
class TextProcessResult:
    args: Sequence[str]
    returncode: int
    stdout: str
    stderr: str
    stdout_encoding: str
    stderr_encoding: str


def _candidate_encodings(*, python_child: bool) -> list[str]:
    """손실 변환 없이 시도할 인코딩 순서를 반환한다.

    Python 자식은 아래 run_text_process가 UTF-8 출력을 강제하므로 UTF-8을 우선한다.
    Windows 레거시 출력 회귀를 위해 시스템 선호 인코딩과 cp949도 후순위로 허용한다.
    """
    preferred = locale.getpreferredencoding(False) or "utf-8"
    ordered = ["utf-8", preferred, "cp949"] if python_child else [preferred, "utf-8", "cp949"]
    result: list[str] = []
    for encoding in ordered:
        normalized = encoding.lower().replace("_", "-")
        if normalized not in {item.lower().replace("_", "-") for item in result}:
            result.append(encoding)
    return result


def decode_process_bytes(raw: bytes, *, python_child: bool = True) -> tuple[str, str]:
    """subprocess 바이트를 손실 없이 디코딩한다. errors='replace'는 사용하지 않는다."""
    if not raw:
        return "", "ascii"
    errors: list[str] = []
    for encoding in _candidate_encodings(python_child=python_child):
        try:
            return raw.decode(encoding, errors="strict"), encoding
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")
    preview = raw[:32].hex(" ")
    raise SubprocessDecodeError(
        "subprocess 출력을 텍스트로 해석하지 못했습니다. "
        f"시도 인코딩={_candidate_encodings(python_child=python_child)!r}, "
        f"앞부분(hex)={preview}, 오류={' | '.join(errors)}"
    )


def run_text_process(
    command: Sequence[str],
    *,
    cwd=None,
    timeout: float | None = None,
    python_child: bool = True,
    env: Mapping[str, str] | None = None,
) -> TextProcessResult:
    """reader thread의 암묵적 text decode를 피하고 완료 후 바이트를 명시적으로 해석한다.

    python_child=True이면 자식 Python의 표준 입출력을 UTF-8로 강제한다. 그럼에도 레거시
    CP949 바이트가 나오면 손실 없이 후순위 디코딩을 시도한다.
    """
    child_env = os.environ.copy()
    if env is not None:
        child_env.update(env)
    if python_child:
        child_env["PYTHONUTF8"] = "1"
        child_env["PYTHONIOENCODING"] = "utf-8"

    completed = subprocess.run(
        list(command),
        cwd=cwd,
        capture_output=True,
        text=False,
        timeout=timeout,
        env=child_env,
    )
    stdout, stdout_encoding = decode_process_bytes(completed.stdout, python_child=python_child)
    stderr, stderr_encoding = decode_process_bytes(completed.stderr, python_child=python_child)
    return TextProcessResult(
        args=completed.args,
        returncode=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        stdout_encoding=stdout_encoding,
        stderr_encoding=stderr_encoding,
    )
