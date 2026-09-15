"""후보·분모·원문·스키마·기존 요청을 검사한다. 외부 모델을 호출하지 않는다."""
import ast, json, unittest, zipfile
from copy import deepcopy
from pathlib import Path
from collections import Counter
from unittest.mock import patch
import core081 as core
import design081 as design
import audit081 as audit
import report081 as report
from fixtures081 import plan, response_set, decode_request, BASELINE, answer


class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = plan()
        cls.records, cls.raws, cls.requests = response_set(cls.p)
        cls.s = report.summarize(cls.p, cls.records, cls.raws, 'complete')

    def test_independent_schedule(self):
        self.assertEqual(design.schedule(self.p['protocol']), audit.reconstruct_schedule(self.p['protocol']))

    def test_assigned_denominators(self):
        p = self.p
        self.assertEqual((len(p['trials']), len(p['slots']), len(p['actions'])), (208, 1468, 1484))
        for variant in ['candidate_id', 'rule_ids']:
            rows = [t for t in p['trials'] if t['selector_variant'] == variant]
            self.assertEqual((len(rows), sum(t['metric'] == 'D' for t in rows), sum(t['metric'] == 'W' for t in rows)), (96, 64, 32))
        self.assertEqual(sum(t['arm'] == 'reference' for t in p['trials']), 16)
        self.assertEqual(sum(o['stage'] == 'select' for o in p['slots']), 192)

    def test_strategy_order_balanced(self):
        by = {}
        for t in self.p['trials']:
            if t['arm'] == 'model':
                by.setdefault(t['unit_id'], []).append(t['selector_variant'])
        self.assertEqual(Counter(v[0] for v in by.values()), {'candidate_id': 48, 'rule_ids': 48})

    def test_all_requests_independently_reconstructed(self):
        for op in self.p['slots']:
            skip, request = audit.expected_request(self.p, op, self.raws)
            self.assertEqual(skip, design.disposition(self.p, op, self.raws), op['id'])
            if skip is None:
                self.assertEqual(request, self.requests[op['id']], op['id'])

    def test_full_summary_independent(self):
        self.assertEqual(self.s, audit.independent_summary(self.p, self.records, self.raws, 'complete'))

    def test_perfect_synthetic_counts(self):
        self.assertEqual(len(self.requests), 1404)
        for variant in ['candidate_id', 'rule_ids']:
            g = self.s['groups'][variant]
            self.assertEqual(g['totals']['D']['metric_end_to_end']['successes'], 64)
            self.assertEqual(g['totals']['D']['end_to_end_pairs']['successes'], 32)
            self.assertEqual(g['totals']['D']['presentation_robust_end_to_end']['successes'], 8)
            self.assertEqual(g['totals']['W']['metric_end_to_end']['successes'], 32)
            self.assertTrue(all(c['all_four_end_to_end_correct'] for c in g['metric_discrimination']))
        self.assertEqual(self.s['reference']['successes'], 16)

    def test_paired_model_inputs_equal(self):
        for a in self.p['trials']:
            if a['selector_variant'] != 'candidate_id':
                continue
            b = next(t for t in self.p['trials'] if t['unit_id'] == a['unit_id'] and t['selector_variant'] == 'rule_ids')
            ra, rb = [core.load(self.requests[t['selection_slot_id']]) for t in (a, b)]
            self.assertEqual(decode_request(ra), decode_request(rb))
            for k in ra.keys() - {'messages', 'format'}:
                self.assertEqual(ra[k], rb[k])
            ha, hb = [r['messages'][0]['content'].split('\n') for r in (ra, rb)]
            self.assertEqual(ha[:2], hb[:2])

    def test_no_numeric_or_parent_answer_in_selector_input(self):
        for op in self.p['slots']:
            if op['stage'] != 'select':
                continue
            d = decode_request(core.load(self.requests[op['id']]))
            self.assertEqual(set(d['problem']), {'facts', 'rules', 'goal'})
            self.assertTrue(all(set(c) == {'candidate_id', 'rules'} for c in d['candidates']))
            self.assertEqual(len(d), 3)

    def test_schema_not_enumerating_valid_sequences(self):
        schema = self.p['protocol']['route_selector_schema']['properties']['rule_ids']
        self.assertEqual((schema['minItems'], schema['maxItems']), (1, 16))
        self.assertNotIn('enum', schema)
        self.assertNotIn('enum', schema['items'])
        self.assertNotIn('oneOf', schema)
        self.assertNotIn('const', schema)

    def test_fixed_id_enum_order(self):
        for t in self.p['trials']:
            if t['selector_variant'] == 'candidate_id':
                req = core.load(self.requests[t['selection_slot_id']])
                self.assertEqual(req['format']['properties']['candidate_id']['enum'], ['route_0', 'route_1'])

    def test_direction_request_only_demand_changes(self):
        grouped = {}
        for t in self.p['trials']:
            if t['pair_id']:
                grouped.setdefault(t['pair_id'], []).append(t)
        for ts in grouped.values():
            body = []
            for t in ts:
                req = core.load(self.requests[t['selection_slot_id']])
                head, inp = req['messages'][0]['content'].split('\n\ninput: ', 1)
                d = core.load(inp)
                d.pop('requested_depth', None); d.pop('requested_rule_count', None)
                req['messages'][0]['content'] = head + '\n\ninput: ' + core.wire(d).decode()
                body.append(req)
            self.assertEqual(body[0], body[1])

    def test_model_history_is_unmodified_and_neutral(self):
        for op in self.p['slots']:
            if op['stage'] == 'select' or op['id'] not in self.requests:
                continue
            t = design.trial_for(self.p, op)
            d = decode_request(core.load(self.requests[op['id']]))
            if t['arm'] == 'model':
                source = core.load(self.raws[t['selection_slot_id']])['message']['content']
                self.assertEqual(d['selection_original']['content'], source)
                self.assertEqual(d['selection_original']['source_id'], t['unit_id'] + '_select')
            preceding = [x for x in self.p['slots'][:self.p['slots'].index(op)] if x['trial_id'] == t['id'] and x['stage'] != 'select' and x['id'] in self.raws]
            self.assertEqual([h['content'] for h in d['history']], [core.load(self.raws[x['id']])['message']['content'] for x in preceding])
            self.assertEqual([h['source_slot_id'] for h in d['history']], [x['logical_id'] for x in preceding])

    def test_rules_do_not_leak_arm_into_generation_header(self):
        for uid in sorted({t['unit_id'] for t in self.p['trials'] if t['arm'] == 'model'}):
            ts = [t for t in self.p['trials'] if t['unit_id'] == uid]
            reqs = [core.load(self.requests[t['id'] + '_facts']) for t in ts]
            self.assertEqual(reqs[0]['format'], reqs[1]['format'])
            heads = [r['messages'][0]['content'].split('\n\ninput: ')[0] for r in reqs]
            self.assertEqual(heads[0], heads[1])
            data = [decode_request(r) for r in reqs]
            for d in data:
                d.pop('selection_original')
            self.assertEqual(data[0], data[1])

    def test_mapping_ignores_D_W_targets(self):
        for t in self.p['trials']:
            if t['arm'] != 'model':
                continue
            altered = deepcopy(t); altered['condition'] = 'deep' if t['condition'] == 'shallow' else 'shallow'
            altered['metric'] = 'W' if t['metric'] == 'D' else 'D'
            self.assertEqual(design.selected_route(self.p, t, self.raws), design.selected_route(self.p, altered, self.raws))

    def test_shared_reference_not_doubled(self):
        self.assertEqual(self.s['reference']['assigned'], 16)
        self.assertTrue(self.s['reference_shared_not_duplicated'])
        for v in ('candidate_id', 'rule_ids'):
            self.assertEqual(self.s['groups'][v]['usage_by_stage']['select']['calls'], 96)

    def test_independent_modules_do_not_import_production(self):
        for name in ['audit081.py', 'verify081.py', 'legacy/audit_model.py', 'legacy/audit_graph.py']:
            tree = ast.parse((core.ROOT / name).read_text())
            imports = []
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    imports.extend(a.name for a in n.names)
                elif isinstance(n, ast.ImportFrom):
                    imports.append(n.module or '')
            self.assertFalse(set(imports) & {'design081', 'report081', 'measure', 'stages', 'design', 'report'}, name)

    @unittest.skipUnless(BASELINE.is_file(), 'v080 evidence가 없어 과거 요청 회귀 검사를 건너뜀')
    def test_all_739_v080_live_requests_preserved(self):
        with zipfile.ZipFile(BASELINE) as z:
            raw = {n.split('/')[1]: z.read(n) for n in z.namelist() if n.startswith('wire/') and n.endswith('/response.raw.json')}
            tested = 0
            for op in self.p['slots']:
                t = design.trial_for(self.p, op)
                if t['selector_variant'] == 'rule_ids':
                    continue
                name = 'wire/' + op['id'] + '/request.wire.json'
                if name in z.namelist():
                    self.assertEqual(core.wire(design.request_for(self.p, op, raw)), z.read(name), op['id'])
                    tested += 1
            self.assertEqual(tested, 739)

    @unittest.skipUnless(BASELINE.is_file(), 'v080 evidence가 없어 핵심 모듈 비교를 건너뜀')
    def test_legacy_files_byte_preserved(self):
        with zipfile.ZipFile(BASELINE) as z:
            for p in (core.ROOT / 'legacy').glob('*.py'):
                self.assertEqual(p.read_bytes(), z.read('source/legacy/' + p.name), p.name)


if __name__ == '__main__':
    unittest.main()
