"""v055-r2: 공용 응답 한도와 큰 로컬 계획 파일 한도를 분리한다."""
import tempfile, unittest
from pathlib import Path
from model_probe_v055.contracts import (ContractError, PLAN_JSON_MAX_BYTES, read_json, read_plan_json, strict_plan_json)

class LargePlanIO(unittest.TestCase):
    def test_plan_over_legacy_8mib_is_readable(self):
        payload = b'{"blob":"' + (b'x' * (8*1024*1024 + 128)) + b'"}'
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'plan.json';p.write_bytes(payload)
            with self.assertRaisesRegex(ContractError,'JSON 크기 한도'):
                read_json(p)
            self.assertEqual(len(read_plan_json(p)['blob']),8*1024*1024+128)

    def test_plan_duplicate_key_still_rejected(self):
        with self.assertRaisesRegex(ContractError,'중복 JSON 키'):
            strict_plan_json(b'{"a":1,"a":2}')

    def test_plan_non_finite_still_rejected(self):
        with self.assertRaises(ContractError):
            strict_plan_json(b'{"a":NaN}')

    def test_plan_over_32mib_rejected_before_parse(self):
        raw=b'{' + (b' ' * PLAN_JSON_MAX_BYTES) + b'}'
        with self.assertRaisesRegex(ContractError,'v055 계획 JSON 크기 한도'):
            strict_plan_json(raw)

if __name__=='__main__':unittest.main()
