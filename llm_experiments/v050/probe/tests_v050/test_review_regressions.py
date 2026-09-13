"""다각도 검토에서 추가한 오류 위치/부분 관측 반례. 수정 전후 동일 시험."""
from __future__ import annotations
import unittest
from criterion_probe_v050.dataset import cases
from criterion_probe_v050.scoring import score_row
from .test_scoring import sample

class ReviewRegressions(unittest.TestCase):
    def test_invalid_proof_must_not_erase_correct_extraction(self):
        c=cases()[2];b,p,o=sample(c);p['b__proof']=None;o['b__proof']['status']='invalid_response'
        r=score_row(c,b,'staged_commuted',p,o)
        self.assertIs(r['observed_correct'],True)
        self.assertIs(r['primitives_correct'],True)
        self.assertIs(r['strict_trace_correct'],False)
    def test_invalid_proof_must_not_erase_correct_gap(self):
        c=cases()[2];b,p,o=sample(c);p['b__proof']=None;o['b__proof']['status']='invalid_response'
        r=score_row(c,b,'staged_commuted',p,o)
        self.assertIs(r['gap_correct'],True)
        self.assertIs(r['finding_correct'],False)
    def test_missing_later_call_must_preserve_observed_earlier_results(self):
        c=cases()[2];b,p,o=sample(c);p.pop('b__gap_direct');o.pop('b__gap_direct')
        r=score_row(c,b,'staged_commuted',p,o)
        self.assertIs(r['observed_correct'],True)
        self.assertIs(r['primitives_correct'],True)
        self.assertIsNone(r['gap_correct'])
        self.assertIsNone(r['strict_trace_correct'])
    def test_bad_not_not_reported_as_input_reading_error(self):
        c=cases()[2];b,p,o=sample(c);p['b__not']=None;p['b__gap_and']=None
        o['b__not']['status']='invalid_response';o['b__gap_and']['status']='blocked'
        r=score_row(c,b,'staged_pipeline',p,o)
        self.assertIs(r['observed_correct'],True)
        self.assertIs(r['primitives_correct'],True)
        self.assertEqual(r['first_failed_stage'],'NOT_format')
