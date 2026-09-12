"""미측정과 실제 오답을 구분하는 추가 심사 기준."""
import unittest
from adm_diagnostic_v052.measure import measure
from adm_diagnostic_v052.design import PROBLEMS
from .test_measure import slot

class ReviewRegression(unittest.TestCase):
    def test_unparsed_response_proof_is_unmeasured_not_incorrect(self):
        m=measure(PROBLEMS['K01'],None,slot())
        self.assertFalse(m['format_valid']);self.assertIsNone(m['proof_valid']);self.assertIsNone(m['review_findings_valid']);self.assertFalse(m['strict_valid'])
    def test_unparsed_graph_only_does_not_claim_proof_error(self):
        m=measure(PROBLEMS['K01'],None,slot(task='graph_only'))
        self.assertFalse(m['format_valid']);self.assertIsNone(m['proof_valid']);self.assertIsNone(m['D'])
