import copy,itertools,unittest
from adm_diagnostic_v052.design import PROBLEMS,ROLES
from adm_diagnostic_v052.measure import measure,project,depth_bounds,role_match
from adm_diagnostic_v052.schema import schema_for
from adm_diagnostic_v052.contracts import validate_payload,decode_response,wire,ContractError
from adm_diagnostic_v052.calibration import reference_record
from .fixtures import generic_trace,to_explicit,envelope,MODEL

def slot(role='instance_shallow_M0',task='factorial',pid='K01',arm='explicit'):
    return {'task':task,'arm':arm,'role_id':role,'problem_id':pid}

class Measurement(unittest.TestCase):
    def test_all_24_valid_combinations(self):
        for pid,p in PROBLEMS.items():
            for r in ROLES:
                with self.subTest(pid=pid,role=r['id']):
                    payload=to_explicit(generic_trace(p,r['A'],r['D'],r['M']))
                    validate_payload(payload,schema_for(slot(r['id'])))
                    m=measure(p,payload,slot(r['id']));self.assertTrue(role_match(m,r,p),m)
    def test_format_reference_copy(self):
        for pid,p in PROBLEMS.items():
            m=measure(p,reference_record(pid),slot(None,'copy_control',pid));self.assertTrue(m['strict_valid']);self.assertTrue(m['copy_exact'])
    def test_depth_is_actual_dependency(self):
        self.assertEqual(depth_bounds(PROBLEMS['K01']),(1,2));self.assertEqual(depth_bounds(PROBLEMS['T02']),(1,4))
    def test_requested_role_not_measurement_input(self):
        p=PROBLEMS['K01'];v=to_explicit(generic_trace(p));a=measure(p,v,slot());b=measure(p,v,slot('schema_deep_M2'));self.assertEqual(a,b)
    def test_goal_atom_not_node_id(self):
        p=PROBLEMS['K01'];v=to_explicit(generic_trace(p));v['final_node_id']='Cc';m=measure(p,v,slot());self.assertFalse(m['strict_valid']);self.assertFalse(m['final_ref_valid']);self.assertTrue(m['all_local_nodes_valid'])
    def test_no_path_pruning(self):
        p=PROBLEMS['K01'];v=to_explicit(generic_trace(p,'instance','deep',0));v['nodes'].append({'id':'alternative','atom':'Cc','rule':'k03','parents':['n0']});v['node_views'].append({'node_id':'alternative','representation':{'kind':'instance','atom':'Cc'}})
        m=measure(p,v,slot());self.assertFalse(m['strict_valid']);self.assertTrue(m['all_local_nodes_valid'])
    def test_false_fact_rejected(self):
        p=PROBLEMS['K01'];v=to_explicit(generic_trace(p));v['nodes']=[{'id':'n0','atom':'Cc','rule':None,'parents':[]}];v['final_node_id']='n0';self.assertFalse(measure(p,v,slot())['proof_valid'])
    def test_missing_premise_rejected(self):
        p=PROBLEMS['T02'];v=to_explicit(generic_trace(p));v['nodes'][-1]['parents']=v['nodes'][-1]['parents'][:1];self.assertFalse(measure(p,v,slot(pid='T02'))['proof_valid'])
    def test_invalid_rule_rejected(self):
        p=PROBLEMS['K01'];v=to_explicit(generic_trace(p));v['nodes'][-1]['rule']='not_allowed';self.assertFalse(measure(p,v,slot())['strict_valid'])
    def test_duplicate_node_view_not_last_wins(self):
        p=PROBLEMS['K01'];v=to_explicit(generic_trace(p));v['node_views'].append(copy.deepcopy(v['node_views'][0]));m=measure(p,v,slot());self.assertFalse(m['strict_valid']);self.assertTrue(m['proof_valid'])
    def test_duplicate_binding_not_last_wins(self):
        p=PROBLEMS['K01'];v=to_explicit(generic_trace(p,'schema'));binding=v['node_views'][-1]['representation']['bindings'];binding.append(copy.deepcopy(binding[0]));m=measure(p,v,slot());self.assertFalse(m['strict_valid']);self.assertTrue(m['proof_valid'])
    def test_schema_premise_injection_rejected(self):
        p=PROBLEMS['K01'];v=to_explicit(generic_trace(p,'schema'));view=v['node_views'][-1]['representation'];view['assumptions'].append({'if':[],'then':view['conclusion']});self.assertFalse(measure(p,v,slot())['strict_valid'])
    def test_schema_wrong_binding_rejected(self):
        p=PROBLEMS['K01'];v=to_explicit(generic_trace(p,'schema'));v['node_views'][-1]['representation']['bindings'][0]['atom']='X';self.assertFalse(measure(p,v,slot())['strict_valid'])
    def test_M2_false_keeps_AD(self):
        p=PROBLEMS['K01'];v=to_explicit(generic_trace(p,'schema','deep',2));v['reviews'][0]['finding']['gap_detected']=False;m=measure(p,v,slot());self.assertTrue(m['proof_valid']);self.assertTrue(m['representation_valid']);self.assertEqual((m['A'],m['D'],m['M']),('schema',2,2));self.assertFalse(m['strict_valid'])
    def test_M2_all_eight_values_only_one_succeeds(self):
        p=PROBLEMS['K01'];passed=0
        for bits in itertools.product((False,True),repeat=3):
            v=to_explicit(generic_trace(p,m=2));v['reviews'][0]['finding']=dict(zip(('answer_only_accepts','proof_and_goal_accepts','gap_detected'),bits));passed+=measure(p,v,slot())['strict_valid']
        self.assertEqual(passed,1)
    def test_M1_target_atom_rejected(self):
        p=PROBLEMS['K01'];v=to_explicit(generic_trace(p,m=1));v['reviews'][0]['target']='Cc';self.assertFalse(measure(p,v,slot())['review_target_valid'])
    def test_graph_only_has_no_A_M_claim(self):
        p=PROBLEMS['K01'];v=to_explicit(generic_trace(p));v={k:v[k] for k in ('nodes','final_node_id')};m=measure(p,v,slot(task='graph_only'));self.assertTrue(m['strict_valid']);self.assertIsNone(m['A']);self.assertIsNone(m['M'])
    def test_roundtrip_preserves_every_semantic_value(self):
        p=PROBLEMS['T02'];v=generic_trace(p,'schema','deep',2);q,errs=project(to_explicit(v),'explicit','factorial');self.assertEqual(q,v);self.assertFalse(errs)
    def test_output_bad_final_not_repaired_in_projection(self):
        v=to_explicit(generic_trace(PROBLEMS['K01']));v['final_node_id']='Cc';q,_=project(v,'explicit','factorial');self.assertEqual(q['final'],'Cc')
    def test_strict_json_rejects_duplicate(self):
        raw=wire(envelope(content='{"nodes":[],"nodes":[]}'))
        with self.assertRaises(ContractError):decode_response(raw,MODEL)
    def test_non_boolean_review_rejected(self):
        p=PROBLEMS['K01'];v=to_explicit(generic_trace(p,m=2));v['reviews'][0]['finding']['gap_detected']=1;self.assertFalse(measure(p,v,slot())['strict_valid'])
    def test_selective_D_not_read_from_role(self):
        p=PROBLEMS['K01'];v=to_explicit(generic_trace(p,'instance','shallow',0));m=measure(p,v,slot('instance_deep_M0'));self.assertEqual(m['D'],1);self.assertFalse(role_match(m,next(r for r in ROLES if r['id']=='instance_deep_M0'),p))
    def test_wrong_goal_rejected(self):
        p=PROBLEMS['K01'];v=to_explicit(generic_trace(p));v['final_node_id']='n0';self.assertFalse(measure(p,v,slot())['strict_valid'])
