from __future__ import annotations
import copy,itertools,unittest
from adm_pilot_v051.contracts import ContractError,validate_payload
from adm_pilot_v051.design import PROBLEM,ROLES
from adm_pilot_v051.measure import measure,role_match
from .fixtures import sample_trace,bare_goal_trace

class Measurement(unittest.TestCase):
    def test_all_12_roles(self):
        for r in ROLES:
            with self.subTest(role=r['id']):
                x=measure(PROBLEM,sample_trace(r['A'],r['D'],r['M']))
                self.assertTrue(x['strict_valid']);self.assertTrue(role_match(x,r))
    def test_goal_string_without_proof_fails(self):
        m=measure(PROBLEM,bare_goal_trace());self.assertTrue(m['goal_string_correct']);self.assertFalse(m['strict_valid'])
    def test_nonexistent_rule(self):
        t=sample_trace();t['nodes'][-1]['rule']='fake';self.assertFalse(measure(PROBLEM,t)['proof_valid'])
    def test_missing_parent(self):
        t=sample_trace();t['nodes'][-1]['parents']=[];self.assertFalse(measure(PROBLEM,t)['proof_valid'])
    def test_duplicate_parent(self):
        t=sample_trace();t['nodes'][-1]['parents']=['n0','n0'];self.assertFalse(measure(PROBLEM,t)['proof_valid'])
    def test_cycle(self):
        t=sample_trace();t['nodes'][-1]['parents']=['n1'];self.assertFalse(measure(PROBLEM,t)['proof_valid'])
    def test_forward_reference(self):
        t=sample_trace();t['nodes'].reverse();self.assertFalse(measure(PROBLEM,t)['proof_valid'])
    def test_duplicate_node_id(self):
        t=sample_trace();t['nodes'][1]['id']='n0';self.assertFalse(measure(PROBLEM,t)['proof_valid'])
    def test_unrelated_nodes_do_not_inflate_depth(self):
        t=sample_trace();t['nodes'].append({'id':'extra','atom':'Ca','rule':None,'parents':[]});t['views']['extra']={'kind':'instance','atom':'Ca'}
        self.assertFalse(measure(PROBLEM,t)['proof_valid'])
    def test_changed_goal(self):
        p=copy.deepcopy(PROBLEM);p['goal']='Ca';self.assertFalse(measure(p,sample_trace())['proof_valid'])
    def test_renamed_variables_preserve_A(self):
        t=sample_trace('schema','deep',0)
        for v in t['views'].values():
            v['binding']={'V'+k[1:]:value for k,value in v['binding'].items()};v['conclusion']='V'+v['conclusion'][1:]
            for c in v['assumptions']:c['if']=['V'+x[1:] for x in c['if']];c['then']='V'+c['then'][1:]
        self.assertEqual(measure(PROBLEM,t)['A'],'schema')
    def test_target_added_as_assumption_rejected(self):
        t=sample_trace('schema');v=t['views'][t['final']];v['assumptions'].append({'if':[],'then':v['conclusion']})
        m=measure(PROBLEM,t);self.assertTrue(m['proof_valid']);self.assertFalse(m['representation_valid'])
    def test_missing_schema_assumption(self):
        t=sample_trace('schema');t['views'][t['final']]['assumptions'].pop();self.assertFalse(measure(PROBLEM,t)['representation_valid'])
    def test_duplicate_schema_assumption(self):
        t=sample_trace('schema');v=t['views'][t['final']];v['assumptions'].append(copy.deepcopy(v['assumptions'][0]));self.assertFalse(measure(PROBLEM,t)['representation_valid'])
    def test_non_bijective_binding(self):
        t=sample_trace('schema');v=t['views'][t['final']];v['binding']['X1']='Ca';self.assertFalse(measure(PROBLEM,t)['representation_valid'])
    def test_unused_binding(self):
        t=sample_trace('schema');t['views'][t['final']]['binding']['ZZ']='Unused';self.assertFalse(measure(PROBLEM,t)['representation_valid'])
    def test_wrong_view_atom(self):
        t=sample_trace();t['views']['n0']['atom']='Cc';self.assertFalse(measure(PROBLEM,t)['representation_valid'])
    def test_mixed_A_not_claimed_uniform(self):
        t=sample_trace('schema');t['views']['n0']={'kind':'instance','atom':'Ca'};m=measure(PROBLEM,t)
        self.assertTrue(m['strict_valid']);self.assertEqual(m['A'],'mixed');self.assertFalse(role_match(m,ROLES[0]))
    def test_M2_false_finding_preserves_target_and_AD(self):
        t=sample_trace('schema','deep',2);t['reviews'][0]['finding']['gap_detected']=False;m=measure(PROBLEM,t)
        self.assertEqual((m['A'],m['D'],m['M']),('schema',2,2));self.assertFalse(m['strict_valid']);self.assertFalse(m['review_findings_valid'])
    def test_M2_alone_no_required_M1(self):
        m=measure(PROBLEM,sample_trace('instance','shallow',2));self.assertTrue(m['strict_valid']);self.assertEqual(m['review_count'],1)
    def test_review_does_not_add_support_depth(self):
        self.assertEqual({measure(PROBLEM,sample_trace('instance','deep',m))['D'] for m in range(3)},{2})
    def test_wrong_M2_target(self):
        t=sample_trace(m=2);t['reviews'][0]['target']='arbitrary';m=measure(PROBLEM,t);self.assertIsNone(m['M']);self.assertFalse(m['strict_valid'])
    def test_M2_wrong_probe(self):
        t=sample_trace(m=2);t['reviews'][0]['probe']['atom']='Ca';self.assertFalse(measure(PROBLEM,t)['review_findings_valid'])
    def test_M1_missing_evidence(self):
        t=sample_trace(m=1);t['reviews'][0]['evidence']=['n0'];self.assertFalse(measure(PROBLEM,t)['strict_valid'])
    def test_M1_wrong_used_rules(self):
        t=sample_trace(m=1);t['reviews'][0]['finding']['used_rules']=[];self.assertFalse(measure(PROBLEM,t)['strict_valid'])
    def test_M1_false_verdict(self):
        t=sample_trace(m=1);t['reviews'][0]['finding']['grounded']=False;self.assertFalse(measure(PROBLEM,t)['strict_valid'])
    def test_M1_accurately_rejects_invalid_proof_not_full_success(self):
        t=sample_trace(m=1);t['nodes'][-1]['rule']='bad';r=t['reviews'][0];r['finding'].update(grounded=False,used_rules=['bad'])
        m=measure(PROBLEM,t);self.assertTrue(m['review_findings_valid']);self.assertFalse(m['strict_valid'])
    def test_missing_requested_review_not_role_match(self):
        m=measure(PROBLEM,sample_trace());self.assertTrue(m['strict_valid']);self.assertFalse(role_match(m,{'A':'instance','D':'shallow','M':2}))
    def test_extra_review_not_clean_M_role(self):
        t=sample_trace(m=2);t['reviews'].append(sample_trace(m=1)['reviews'][0]);m=measure(PROBLEM,t)
        self.assertTrue(m['strict_valid']);self.assertFalse(role_match(m,{'A':'instance','D':'shallow','M':2}))
    def test_requested_role_does_not_create_measurement(self):
        m=measure(PROBLEM,sample_trace());self.assertFalse(role_match(m,{'A':'schema','D':'deep','M':2}));self.assertEqual((m['A'],m['D'],m['M']),('instance',1,0))
    def test_extra_ADM_selflabels_rejected(self):
        t=sample_trace();t['A']='schema';self.assertFalse(measure(PROBLEM,t)['format_valid'])
    def test_all_eight_M2_bool_combinations(self):
        valid=0
        for vals in itertools.product((False,True),repeat=3):
            t=sample_trace(m=2);t['reviews'][0]['finding']=dict(zip(('answer_only_accepts','proof_and_goal_accepts','gap_detected'),vals));valid+=measure(PROBLEM,t)['strict_valid']
        self.assertEqual(valid,1)
    def test_no_integer_boolean(self):
        t=sample_trace(m=2);t['reviews'][0]['finding']['gap_detected']=1
        with self.assertRaises(ContractError):validate_payload(t)
