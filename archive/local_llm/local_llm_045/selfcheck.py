"""모델 호출 전의 오프라인 하네스 양성/음성 대조. LLM 성과에 포함하지 않는다."""
from __future__ import annotations

import copy
from typing import Any

from .audit import negative_controls
from .common import require, wire_json
from .prompts_v2 import DEMO_INSTANCE, DEMO_PROBLEM, DEMO_SCHEMA
from .protocol_v2 import parse_payload, to_trace


def selfcheck(core: Any) -> dict:
    checks = []
    for name, payload in (("instance_M0", DEMO_INSTANCE), ("schema_M2", DEMO_SCHEMA)):
        original = copy.deepcopy(payload)
        trace = to_trace(core, DEMO_PROBLEM, parse_payload(wire_json(payload)))
        verification = core.verify(DEMO_PROBLEM, trace)
        checks.append({"name": name + "_positive", "passed": verification["valid"]})
        checks.append({"name": name + "_input_unchanged", "passed": original == payload})
        for control in negative_controls(core, DEMO_PROBLEM, trace):
            if control["applicable"]:
                checks.append({"name": name + "_" + control["name"], "passed": control["rejected"]})
    passed = all(check["passed"] for check in checks)
    require(passed, "오프라인 하네스 자체 검사 실패. 모델을 호출하지 않습니다.")
    return {"passed": passed, "checks": checks, "model_called": False,
            "note": "명시된 픽스처를 이용한 코드 검사이며 LLM 실험 결과가 아님"}
