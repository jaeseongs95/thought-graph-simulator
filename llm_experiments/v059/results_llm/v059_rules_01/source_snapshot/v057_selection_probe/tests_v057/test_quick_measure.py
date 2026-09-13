import copy,unittest
from selection_probe_v057.measure import choice_measure,match,terminal_depths
from selection_probe_v057.contracts import strict_json,ContractError
from order_probe_v054.design import PROBLEMS

class Choice(unittest.TestCase):
    def run_choice(self,rid,pid='K01',direction='shallow'):
        p=PROBLEMS[pid];s={'mode':'choice','direction':direction};m=choice_measure(p,{'final_rule_id':rid},s);return m,match(p,m,s)
    def test_k01_short(self):self.assertTrue(self.run_choice('k03')[1])
    def test_k01_deep(self):self.assertTrue(self.run_choice('k17',direction='deep')[1])
    def test_t02_short(self):self.assertTrue(self.run_choice('r83','T02')[1])
    def test_t02_deep(self):self.assertTrue(self.run_choice('r69','T02','deep')[1])
    def test_wrong_direction_not_success(self):self.assertFalse(self.run_choice('k17')[1])
    def test_neutral_not_direction_success(self):self.assertIsNone(self.run_choice('k17',direction='neutral')[1])
    def test_goal_atom_not_rule(self):
        m,ok=self.run_choice('Cc');self.assertFalse(m['choice_valid']);self.assertIn('unknown_rule',m['errors']);self.assertFalse(ok)
    def test_intermediate_rule_not_valid(self):
        m,_=self.run_choice('k10');self.assertFalse(m['choice_valid']);self.assertEqual(m['errors'],['not_goal_concluding_rule'])
    def test_unknown_not_repaired(self):self.assertFalse(self.run_choice('k1_7')[0]['choice_valid'])
    def test_whitespace_not_trimmed(self):self.assertFalse(self.run_choice(' k03 ')[0]['choice_valid'])
    def test_case_not_repaired(self):self.assertFalse(self.run_choice('K03')[0]['choice_valid'])
    def test_choice_is_never_proof(self):
        m,_=self.run_choice('k03')
        for k in ('proof_valid','strict_valid','D'):self.assertIsNone(m[k])
        self.assertEqual(m['implied_depth'],1)
    def test_unparsed_unmeasured(self):
        m=choice_measure(PROBLEMS['K01'],None,{'mode':'choice'});self.assertIsNone(m['choice_valid']);self.assertIsNone(m['proof_valid'])
    def test_extra_field_not_accepted(self):
        m=choice_measure(PROBLEMS['K01'],{'final_rule_id':'k03','answer':'Cc'},{'mode':'choice'});self.assertFalse(m['format_valid']);self.assertIsNone(m['choice_valid'])
    def test_nonstring_not_accepted(self):
        for x in (1,True,None,[],{}):self.assertFalse(choice_measure(PROBLEMS['K01'],{'final_rule_id':x},{'mode':'choice'})['format_valid'])
    def test_duplicate_key_rejected(self):
        with self.assertRaises(ContractError):strict_json(b'{"final_rule_id":"k03","final_rule_id":"k17"}')
    def test_nonfinite_rejected(self):
        with self.assertRaises(ContractError):strict_json(b'{"x":NaN}')
    def test_depth_maps_not_from_request_direction(self):
        self.assertEqual(terminal_depths(PROBLEMS['K01']),{'k17':[2],'k03':[1]});self.assertEqual(terminal_depths(PROBLEMS['T02']),{'r83':[1],'r69':[4]})
    def test_rule_order_does_not_change_depth_map(self):
        p=copy.deepcopy(PROBLEMS['T02']);p['rules'].reverse();self.assertEqual(terminal_depths(p),terminal_depths(PROBLEMS['T02']))
    def test_ambiguous_terminal_depth_rejected(self):
        p=copy.deepcopy(PROBLEMS['K01']);p['rules'].append({'id':'shortcutB','premises':['Ca'],'conclusion':'Cx'});p['rules'].append({'id':'alsoB','premises':['Cx'],'conclusion':'Cb'})
        with self.assertRaises(ContractError):terminal_depths(p)
    def test_cyclic_problem_rejected(self):
        p=copy.deepcopy(PROBLEMS['K01']);p['rules'].append({'id':'loop','premises':['Cc'],'conclusion':'Ca'})
        with self.assertRaises(ContractError):terminal_depths(p)
