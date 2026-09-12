"""제3자 관점: 뒤의 메타 판정 오류가 앞의 실제 구조 관측을 지우는가?"""
from __future__ import annotations
import unittest
from adm_pilot_v051.measure import measure
from adm_pilot_v051.design import PROBLEM
from .fixtures import sample_trace,executed

class ReviewRegressions(unittest.TestCase):
    def test_malformed_M2_finding_does_not_erase_valid_proof_A_D(self):
        t=sample_trace('schema','deep',2);t['reviews'][0]['finding']['gap_detected']='false'
        m=measure(PROBLEM,t)
        self.assertFalse(m['format_valid']);self.assertFalse(m['strict_valid'])
        self.assertTrue(m['proof_valid']);self.assertEqual((m['A'],m['D'],m['M']),('schema',2,2))
    def test_malformed_view_does_not_erase_valid_support_depth(self):
        t=sample_trace('schema','deep',0);t['views'][t['final']]['binding']={'X0':123}
        m=measure(PROBLEM,t);self.assertFalse(m['format_valid']);self.assertTrue(m['proof_valid']);self.assertEqual(m['D'],2)
    def test_raw_http_M2_format_failure_keeps_AD_observations(self):
        with executed('invalid_m2_format') as (_,_,_,_,r,_):
            self.assertEqual(sum(x['format_valid'] for x in r['roles'].values()),160)
            self.assertEqual(sum(x['proof_valid'] for x in r['roles'].values()),240)
            self.assertEqual(sum(x['representation_valid'] for x in r['roles'].values()),240)
    def test_component_contrast_not_erased_by_wrong_M2_finding(self):
        with executed('wrong_m2') as (_,_,_,_,r,_):
            a=[x for x in r['paired'] if x['axis']=='A']
            self.assertEqual(sum(x['coordinate_change_observed'] for x in a),120)
            self.assertEqual(sum(x['clean_requested_axis_change'] for x in a),80)
