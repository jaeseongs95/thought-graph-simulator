from __future__ import annotations
import copy,itertools,unittest
from criterion_probe_v050.dataset import cases
from criterion_probe_v050.scoring import expected,score_row,path_stages,ARMS

def sample(case):
    block={'id':'b','seed':1,'cycle':0};w=expected(case);e=copy.deepcopy(w);e.pop('finding')
    a=w['primitives']['same_as_goal'];b=w['primitives']['in_facts']
    payloads={'b__oneshot_original':copy.deepcopy(w),'b__oneshot_commuted':copy.deepcopy(w),'b__extract':e,
        'b__proof':{'value':a and b},'b__gap_direct':{'value':a and not b},'b__not':{'value':not b},'b__gap_and':{'value':a and not b}}
    observations={k:{'status':'valid_payload'} for k in payloads};return block,payloads,observations

class Scoring(unittest.TestCase):
    def test_all_perfect_cases(self):
        for c in cases():
            b,p,o=sample(c)
            for a in ARMS:self.assertTrue(score_row(c,b,a,p,o)['strict_trace_correct'])
    def test_all_256_boolean_assignments(self):
        # 네 입력 × 추출 a/b, proof, direct gap, NOT, final gap의 64조합.
        total=0;full=0;masked=0
        for case in cases():
            accepted=0
            for aa,bb,proof,gd,nn,ga in itertools.product((False,True),repeat=6):
                b,p,o=sample(case);p['b__extract']['primitives']={'same_as_goal':aa,'in_facts':bb}
                for k,v in [('proof',proof),('gap_direct',gd),('not',nn),('gap_and',ga)]:p['b__'+k]['value']=v
                d=score_row(case,b,'staged_commuted',p,o);s=score_row(case,b,'staged_pipeline',p,o)
                accepted+=d['strict_trace_correct'] and s['strict_trace_correct'];total+=1
                masked+=s['finding_correct'] and not s['strict_trace_correct']
            self.assertEqual(accepted,1);full+=accepted
        self.assertEqual(total,256);self.assertEqual(full,4);self.assertGreater(masked,0)
    def test_each_oneshot_boolean_bit_is_checked(self):
        for case in cases():
            for part,field in [('primitives','same_as_goal'),('primitives','in_facts'),('finding','answer_only_accepts'),('finding','proof_and_goal_accepts'),('finding','gap_detected')]:
                b,p,o=sample(case);p['b__oneshot_original'][part][field]=not p['b__oneshot_original'][part][field]
                self.assertFalse(score_row(case,b,'oneshot_original',p,o)['strict_trace_correct'])
    def test_missing_observation_does_not_default_to_wrong(self):
        c=cases()[0];b,p,o=sample(c);o.pop('b__oneshot_original');p.pop('b__oneshot_original')
        r=score_row(c,b,'oneshot_original',p,o);self.assertIsNone(r['finding_correct']);self.assertIsNone(r['strict_trace_correct'])
    def test_goal_derivable_but_not_fact_is_positive_gap(self):
        # Ca→Cc 규칙이 있어도 부모·규칙 없는 단독 Cc 주장에는 지지가 없다.
        c=cases()[2];e=expected(c);self.assertTrue(e['finding']['gap_detected']);self.assertFalse(e['finding']['proof_and_goal_accepts'])
    def test_host_routes_model_answer_only_without_repair(self):
        c=cases()[2];b,p,o=sample(c);p['b__extract']['primitives']['same_as_goal']=False
        r=score_row(c,b,'staged_commuted',p,o);self.assertIs(r['actual']['finding']['answer_only_accepts'],False)
