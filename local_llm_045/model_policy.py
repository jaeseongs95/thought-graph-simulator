"""모델 이름 대신 GGUF 메타데이터로 실행 모드를 검사한다. 추론·다운로드 없음.

지원 여부는 체크포인트 식별과 Ollama capability를 분리해 판단한다.
메타데이터 검사는 추론 품질이나 서버의 실제 thinking 동작을 보증하지 않는다.
"""
from __future__ import annotations

import copy
import re
from typing import Any

from .common import ContractError, digest, require

POLICY_VERSION = "qwen3-mode-v4"
DEFAULT_MODEL = "qwen3:4b-instruct"
SOURCES = {
    "instruct": "https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507",
    "thinking": "https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507",
    "channels": "https://docs.ollama.com/capabilities/thinking",
}


class ModeError(ContractError):
    """메타데이터/실제 응답 채널과 요청 모드의 불일치. 모델 과제 오답과 구분한다."""


def identify_model(metadata: dict) -> dict:
    show = metadata.get("show", {})
    info = show.get("model_info", {})
    require(isinstance(info, dict), "모델 model_info 객체가 없습니다.")
    fields = {key: info.get(key) for key in (
        "general.architecture", "general.basename", "general.name", "general.version",
        "general.finetune", "general.license.link", "general.size_label")}
    arch = str(fields["general.architecture"] or "").lower()
    require(arch in {"qwen3", "qwen3moe"},
            "v0.4 자동 정책은 Qwen3 GGUF에 한정됩니다. 다른 계열은 문서화된 모드 정책을 추가해야 합니다.")
    # 라이선스 본문 전체의 'thinking' 단어를 검색하지 않는다. 공식 저장소 URI만 식별 근거로 사용.
    uri = str(fields["general.license.link"] or "")
    match = re.search(r"huggingface\.co/Qwen/Qwen3-[^/\s]+-(Instruct|Thinking)-2507(?:/|$)", uri,
                      flags=re.IGNORECASE)
    evidence = []
    candidates = set()
    ft = str(fields["general.finetune"] or "").strip().lower()
    version = str(fields["general.version"] or "").strip()
    if ft in {"instruct", "thinking"} and version == "2507":
        candidates.add(ft)
        evidence.append({"source": "GGUF finetune + version", "kind": ft})
    if match:
        candidate = match.group(1).lower()
        candidates.add(candidate)
        evidence.append({"source": "GGUF official model repository URI", "kind": candidate})
    require(len(candidates) <= 1, "GGUF 모델 계열 메타데이터가 서로 모순됩니다. 모델을 확인하세요.")
    if candidates:
        kind = next(iter(candidates))
        if ft in {"instruct", "thinking"}:
            require(ft == kind, "finetune 필드와 공식 저장소 URI의 모델 계열이 다릅니다.")
    else:
        # 태그나 capability만으로 '하이브리드'라고 추정하지 않는다.
        raise ModeError("체크포인트의 모드 유형을 확인하지 못했습니다. qwen3:4b 같은 별칭만으로 "
                        "판단하지 않습니다. qwen3:4b-instruct 또는 Thinking-2507의 GGUF 메타데이터를 확인하세요.")
    capabilities = show.get("capabilities", [])
    require(isinstance(capabilities, list) and "completion" in capabilities,
            "텍스트 생성 capability가 없습니다.")
    return {"policy_version": POLICY_VERSION, "checkpoint_kind": kind,
            "checkpoint_version": "2507", "evidence": evidence, "identity_fields": fields,
            "capabilities": capabilities, "metadata_sha256": digest(show),
            "source": SOURCES[kind],
            "note": "태그 이름은 분류 근거가 아님. 별도 체크포인트 사이의 비교이며 동일 가중치의 on/off 비교가 아님."}


def resolve_config(config: dict, metadata: dict) -> dict:
    """불일치는 추론 전에 차단한다. Instruct에는 불필요한 think 필드를 보내지 않는다."""
    result = copy.deepcopy(config)
    identity = identify_model(metadata)
    kind = identity["checkpoint_kind"]
    requested = result.get("requested_mode", "auto")
    require(requested in {"auto", "non-thinking", "thinking"}, "알 수 없는 실행 모드")
    expected = "thinking" if kind == "thinking" else "non-thinking"
    if requested not in {"auto", expected}:
        raise ModeError(f"모델/모드 불일치: {kind}-2507은 {expected} 전용인데 {requested}를 요청했습니다. "
                        "실행 모드를 맞추거나 다른 체크포인트를 별도 결과 폴더에서 사용하세요.")
    if kind == "thinking":
        require("thinking" in identity["capabilities"],
                "Thinking 체크포인트지만 Ollama가 thinking capability를 제공하지 않습니다. 서버/템플릿을 확인하세요.")
    options = result["options"]
    defaults = ({"temperature": 0.6, "top_p": 0.95, "num_ctx": 16384, "num_predict": 8192}
                if kind == "thinking" else
                {"temperature": 0.7, "top_p": 0.8, "num_ctx": 8192, "num_predict": 4096})
    for key, value in defaults.items():
        if options.get(key) is None:
            options[key] = value
    require(4096 <= options["num_ctx"] <= 65536, "num-ctx 범위: 4096~65536")
    require(256 <= options["num_predict"] < options["num_ctx"],
            "출력 한도는 256 이상이고 context보다 작아야 합니다.")
    if kind == "thinking":
        require(options["temperature"] > 0, "Thinking 실행에는 temperature>0를 지정하세요.")
    model_limit = metadata["show"].get("model_info", {}).get("qwen3.context_length")
    if isinstance(model_limit, int):
        require(options["num_ctx"] <= model_limit, "요청 context가 GGUF에 기재된 context를 초과합니다.")
    result["think"] = True if kind == "thinking" else None
    result["mode_policy"] = {**identity, "resolved_mode": expected,
                             "request_think_field": "true" if kind == "thinking" else "omitted",
                             "require_separate_thinking": kind == "thinking",
                             "resource_budget": "local_bounded_not_vendor_benchmark_budget"}
    result["config_stage"] = "resolved"
    return result


def response_channels(body: dict, response: dict, policy: dict | None) -> dict:
    """최종 content만 판정한다. thinking에서 JSON을 추출하거나 응답을 복구하지 않는다."""
    message = response.get("message")
    if not isinstance(message, dict):
        raise ModeError("assistant message가 없어 응답 채널을 검사할 수 없습니다.")
    content = message.get("content")
    thinking = message.get("thinking")
    if not isinstance(content, str) or (thinking is not None and not isinstance(thinking, str)):
        raise ModeError("content/thinking 채널의 자료형이 올바르지 않습니다.")
    observed_thinking = isinstance(thinking, str) and bool(thinking.strip())
    result = {"thinking_field_present": "thinking" in message,
              "thinking_nonempty": observed_thinking,
              "thinking_characters": len(thinking or ""),
              "final_characters": len(content), "final_nonempty": bool(content.strip()),
              "eval_count_scope": "API total generated tokens; no separate final/thinking token counts inferred"}
    if policy:
        required = policy["require_separate_thinking"]
        if required and not observed_thinking:
            raise ModeError("Thinking 모드로 요청했으나 별도 message.thinking이 비어 있습니다. "
                            "JSON/템플릿/서버 호환성을 확인하세요. 최종 JSON만으로 정상 모드를 가정하지 않습니다.")
        if not required and observed_thinking:
            raise ModeError("non-thinking 체크포인트 요청에서 thinking 채널이 반환됐습니다.")
        if not content.strip():
            raise ModeError("최종 content가 비어 있습니다. thinking을 정답으로 대신 사용하지 않습니다.")
    return result
