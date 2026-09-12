"""동결된 이전 코어는 수정하지 않고 v055 소스까지 지문에 포함한다."""
from pathlib import Path
import json, math
from order_probe_v054.contracts import (ContractError, require, strict_json, wire, canonical,
    sha, digest, b64, unb64, read_json, write_json, utc_now, usage, require_external_plan,
    decode_response, validate_payload)
from order_probe_v054.contracts import source_fingerprint as previous_fingerprint

def source_fingerprint():
    values = previous_fingerprint()
    root = Path(__file__).resolve().parent.parent
    for path in sorted((root/'model_probe_v055').glob('*.py')):
        raw = path.read_text(encoding='utf-8-sig').replace('\r\n','\n').replace('\r','\n').encode('utf-8')
        values['model_probe_v055/'+path.name] = sha(raw)
    return values


# v055-r2: 실행 계획은 capture 원문과 두 모델 identity를 함께 보존하므로
# 공용 8 MiB 응답 JSON 한도보다 커질 수 있다. 네트워크/모델 응답의 8 MiB
# 한도는 그대로 유지하고, 동결된 로컬 plan/snapshot 파일에만 별도 상한을 둔다.
PLAN_JSON_MAX_BYTES = 32 * 1024 * 1024

def strict_plan_json(data):
    require(isinstance(data, (str, bytes)), "계획 JSON 문자열/바이트가 필요합니다.")
    require(len(data) <= PLAN_JSON_MAX_BYTES, "v055 계획 JSON 크기 한도를 넘었습니다.")
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "중복 JSON 키: " + key)
            result[key] = value
        return result
    def invalid(value):
        raise ContractError("비유한 JSON 숫자: " + value)
    try:
        def finite_float(text):
            number = float(text)
            require(math.isfinite(number), "비유한 JSON 실수")
            return number
        return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid, parse_float=finite_float)
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise ContractError("엄격한 계획 JSON 해석 실패: " + str(exc)) from exc

def read_plan_json(path: Path):
    return strict_plan_json(path.read_bytes())
