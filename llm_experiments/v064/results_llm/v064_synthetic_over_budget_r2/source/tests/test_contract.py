"""반대 결과와 운영 경계. 합성 서버 응답은 실제 모델 성과가 아니다."""
import base64
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import common
import design
import measure
import report
import run
import verify


def baseline_path():
    return Path(os.environ.get('V064_BASELINE', str(ROOT.parents[1] / 'v058/results_llm/v058_order_02_evidence.zip')))


def proof(problem, deep=False):
    """Test-only hand-specified paths, never used by the live request runner."""
    routes = {
        'T02': (['r83'], ['r21', 'r57', 'r04', 'r69']),
        'E01_shared_fork': (['n52'], ['n08', 'n91', 'n37']),
        'E02_two_vs_four': (['m18', 'm76'], ['m33', 'm05', 'm84', 'm41']),
    }
    rules = {r['id']: r for r in problem['rules']}
    route = routes[problem['id']][int(deep)]
    nodes = [{'id': atom, 'atom': atom, 'rule': None, 'parents': []} for atom in problem['facts']]
    for key in route:
        rule = rules[key]
        nodes.append({'id': rule['conclusion'], 'atom': rule['conclusion'], 'rule': key,
                      'parents': rule['premises'][:]})
    return {'nodes': nodes, 'final_node_id': problem['goal']}


def envelope(payload, model='qwen3:4b-instruct'):
    return {'model': model, 'message': {'role': 'assistant', 'content': json.dumps(payload)},
            'done': True, 'done_reason': 'stop', 'prompt_eval_count': 100, 'eval_count': 50,
            'prompt_eval_cached_count': 0, 'total_duration': 1000000}


@contextmanager
def server(plan, mode='good'):
    state = {'chats': 0, 'requests': []}
    identity = plan['identity']
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            if self.path == '/api/version':
                body = identity['server']
            elif self.path == '/api/tags':
                body = {'models': [{'name': identity['model'], 'digest': identity['digest'], 'details': identity['details']}]}
                if mode == 'bad_metadata':
                    body['models'][0]['digest'] = '0' * 64
            else:
                self.send_error(404)
                return
            self.respond(body)
        def do_POST(self):
            request = common.load(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path == '/api/show':
                self.respond({k: identity[k] for k in ('details', 'template', 'parameters', 'model_info')})
                return
            if self.path != '/api/chat':
                self.send_error(404)
                return
            state['chats'] += 1
            state['requests'].append(request)
            if mode == 'http_error' or mode == 'late_http' and state['chats'] == 4:
                self.respond({'error': 'synthetic failure'}, 503)
                return
            text = request['messages'][0]['content']
            problem = json.loads(text.split('\n\nproblem: ')[-1])
            deep = '가장 큰 경로' in text and mode != 'fixed'
            if mode == 'reversed':
                deep = '가장 작은 경로' in text
            payload = proof(problem, deep)
            if mode == 'reverse_nodes':
                payload['nodes'].reverse()
            if mode == 'bad_parent':
                payload['nodes'][-1]['parents'] = []
            response = envelope(payload, identity['model'])
            if mode == 'over_budget':
                response['eval_count'] = 4097
            if mode == 'wrong_model':
                response['model'] = 'different:4b'
            if mode == 'parse_error':
                response['message']['content'] = '{bad json'
            self.respond(response)
        def respond(self, value, code=200):
            raw = common.wire(value)
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=http.serve_forever, daemon=True)
    worker.start()
    try:
        yield 'http://127.0.0.1:' + str(http.server_port), state
    finally:
        http.shutdown()
        http.server_close()
        worker.join()


def resign(files):
    files = dict(files)
    files.pop('MANIFEST.json', None)
    files['MANIFEST.json'] = common.wire({'contract': 'v064-evidence-r1',
        'file_hashes': {k: common.sha(v) for k, v in files.items()}})
    return common.zip_bytes(files)


def rebind_events_and_report(files, plan):
    events = [common.load(line) for line in files['records/events.jsonl'].splitlines()]
    tip = plan['plan_sha256']
    calls = []
    for event in events:
        key = 'records/' + event['action']['id'] + '.json'
        record = common.load(files[key])
        if record['kind'] == 'call':
            calls.append({k: v for k, v in record.items() if k != 'kind'})
        event['record_sha256'] = common.sha(files[key])
        event['previous_hash'] = tip; event.pop('event_hash')
        event['event_hash'] = common.sha(common.wire(event)); tip = event['event_hash']
    files['records/events.jsonl'] = b''.join(common.wire(e) + b'\n' for e in events)
    summary = report.summarize(plan, calls, common.load(files['status.json'])['state'])
    files['summary.json'] = (json.dumps(summary, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    files['summary.ko.md'] = report.render(summary).encode('utf-8')
    return files


class SemanticTests(unittest.TestCase):
    def test_topological_order_and_invalid_usage(self):
        p = common.spec()['problems'][0]
        payload = proof(p, True)
        payload['nodes'].reverse()
        result = measure.assess(p, payload)
        self.assertIs(result['proof_valid'], True)
        self.assertIs(result['strict_valid'], False)
        self.assertIsNone(result['actual_D'])
        self.assertIn('non_topological_order', result['error_codes'])
        for invalid in (-1, True, 1.5, '50', None):
            self.assertIsNone(report._usage({'eval_count': invalid})['eval_count'])
        self.assertEqual(report._usage({'eval_count': 0})['eval_count'], 0)

    def test_manual_paths_and_actual_depths(self):
        for problem in common.spec()['problems']:
            expected = common.spec()['depth_ranges'][problem['id']]
            self.assertEqual(measure.depth_ranges(problem), expected)
            for deep, want in zip((False, True), expected):
                result = measure.assess(problem, proof(problem, deep))
                self.assertIs(result['strict_valid'], True)
                self.assertEqual(result['actual_D'], want)

    def test_rule_labels_parents_cycles_and_unused_nodes(self):
        p = common.spec()['problems'][0]
        valid = proof(p, True)
        bad_cases = []
        bad = copy.deepcopy(valid); bad['nodes'][-1]['parents'] = []; bad_cases.append(bad)
        bad = copy.deepcopy(valid); bad['nodes'][-1]['atom'] = 'invented'; bad_cases.append(bad)
        bad = copy.deepcopy(valid); bad['nodes'][-1]['rule'] = 'unknown'; bad_cases.append(bad)
        bad = copy.deepcopy(valid); bad['nodes'][-1]['parents'] = ['missing']; bad_cases.append(bad)
        bad = copy.deepcopy(valid); bad['nodes'][-1]['parents'] *= 2; bad_cases.append(bad)
        bad = copy.deepcopy(valid); bad['nodes'][0]['parents'] = [bad['nodes'][-1]['id']]; bad_cases.append(bad)
        bad = copy.deepcopy(valid); bad['nodes'].append(copy.deepcopy(bad['nodes'][0])); bad_cases.append(bad)
        bad = copy.deepcopy(valid); bad['nodes'].append({'id': 'extra', 'atom': 'invented', 'rule': None, 'parents': []}); bad_cases.append(bad)
        bad = copy.deepcopy(valid); bad['nodes'].append({'id': 'extra', 'atom': p['facts'][0], 'rule': None, 'parents': []}); bad_cases.append(bad)
        for value in bad_cases:
            with self.subTest(value=value):
                before = copy.deepcopy(value)
                result = measure.assess(p, value)
                self.assertIsNot(result['strict_valid'], True)
                self.assertIsNone(result['actual_D'])
                self.assertEqual(value, before)

    def test_missing_and_parse_failures_do_not_become_logical_errors(self):
        plan = design.build_plan(baseline_path(), 'v064_missing_test', 'synthetic')
        result = report.summarize(plan, [], 'stopped')
        self.assertTrue(all(r['actual_D'] is None and r['strict_valid'] is None for r in result['rows']))
        self.assertTrue(all(p['strict_min_max'] is None for p in result['directed_pairs']))
        self.assertTrue(all(p['strict_min_max_rate'] is None for p in result['problem_summaries']))
        self.assertIsNone(result['overall']['bounded_A_or_M_pilot'])
        self.assertEqual(result['limits']['logical_failures'], 0)

    def test_prepare_offline_budget_and_only_allowed_request_changes(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('offline prepare made HTTP request')):
            plan = design.build_plan(baseline_path(), 'v064_preparation_test', 'synthetic')
        self.assertEqual(len(plan['slots']), 18)
        self.assertEqual(len(plan['actions']), 30)
        for block in range(6):
            requests = [design.request_for(plan, s) for s in plan['slots'] if s['block'] == block]
            for request in requests:
                self.assertEqual(request['options']['num_predict'], 4096)
                self.assertEqual(request['format'], plan['baseline_request']['format'])
                self.assertLessEqual(len(common.wire(request)), 16000)
                self.assertNotIn('expected_min_D', request['messages'][0]['content'])
                self.assertNotIn('depth_ranges', request['messages'][0]['content'])


class RuntimeTests(unittest.TestCase):
    def test_first_stop_cannot_be_hidden_by_rebinding_all_hashes(self):
        for case in ('identity', 'http', 'metadata', 'generation'):
            files = dict(self.files)
            if case == 'metadata':
                action = self.good_plan['actions'][0]
                key = 'records/' + action['id'] + '.json'
                record = common.load(files[key])
                item = record['items'][1]
                response = common.load(base64.b64decode(item['response_b64']))
                response['models'][0]['digest'] = '0' * 64
                raw = common.wire(response)
                item['response_b64'] = base64.b64encode(raw).decode()
                record['identity_ok'] = False
                files['metadata/' + action['id'] + '/1.response.raw.json'] = raw
            else:
                slot = self.good_plan['slots'][0]
                key = 'records/' + slot['id'] + '.json'; record = common.load(files[key])
                if case == 'http':
                    record['http_status'] = 503
                else:
                    response = common.load(base64.b64decode(record['response_b64']))
                    response['model' if case == 'identity' else 'eval_count'] = 'different:4b' if case == 'identity' else 4097
                    raw = common.wire(response)
                    record['response_b64'] = base64.b64encode(raw).decode()
                    record['response_sha256'] = common.sha(raw)
                    files['wire/' + slot['id'] + '/response.raw.json'] = raw
            files[key] = common.wire(record)
            rebind_events_and_report(files, self.good_plan)
            path = self.root / ('early_stop_' + case + '.zip'); common.write(path, resign(files))
            with self.assertRaisesRegex(ValueError, 'action after mandatory stop'):
                verify.verify_bundle(path)

    def test_reported_generation_excess_is_preserved_as_stopped(self):
        summary, result, state = self.run_mode('over_budget')
        self.assertEqual(state['chats'], 1)
        self.assertEqual(result['state'], 'stopped')
        self.assertEqual(summary['rows'][0]['usage']['eval_count'], 4097)
        self.assertIsNone(summary['overall']['bounded_A_or_M_pilot'])
        receipt = common.load(Path(result['independent_verification']).read_bytes())
        self.assertTrue(receipt['verified'])

    def test_uncommitted_wire_preserved_without_scoring_or_future_actions(self):
        for case in ('response', 'request_prefix', 'metadata'):
            name = 'v064_pending_' + case
            plan = design.build_plan(baseline_path(), name, 'synthetic')
            pp = self.root / (name + '.plan.json'); common.save(pp, plan)
            out = self.root / name
            original = run.capture_call
            def interrupted_call(*args):
                if case == 'response':
                    original(*args)
                else:
                    active_plan, action, endpoint, target = args
                    slot = next(s for s in active_plan['slots'] if s['id'] == action['id'])
                    raw = common.wire(design.request_for(active_plan, slot))
                    common.write(target / 'wire' / action['id'] / 'request.wire.json', raw[:40])
                raise KeyboardInterrupt('synthetic pending wire')
            def interrupted_metadata(active_plan, action, endpoint, target):
                common.write(target / 'metadata' / action['id'] / '0.request.json', b'')
                common.write(target / 'metadata' / action['id'] / '0.response.raw.json', b'{partial')
                raise KeyboardInterrupt('synthetic pending metadata')
            function = 'capture_metadata' if case == 'metadata' else 'capture_call'
            replacement = interrupted_metadata if case == 'metadata' else interrupted_call
            with server(plan) as (endpoint, state), patch.object(run, function, side_effect=replacement), redirect_stdout(io.StringIO()):
                result = run.execute(pp, baseline_path(), out, endpoint)
            receipt = common.load(Path(result['independent_verification']).read_bytes())
            self.assertEqual(receipt['state'], 'crashed')
            self.assertEqual(receipt['observed_calls'], 0)
            self.assertIs(receipt['pending_action']['record_committed'], False)
            self.assertTrue(receipt['pending_action']['artifact_names'])
            files = common.unzip(Path(result['evidence_zip']).read_bytes())
            self.assertIsNone(common.load(files['summary.json'])['overall']['bounded_A_or_M_pilot'])
            forged = dict(files); forged['wire/future/request.wire.json'] = b'{}'
            path = self.root / (name + '_future.zip'); common.write(path, resign(forged))
            with self.assertRaises(ValueError): verify.verify_bundle(path)
            if case != 'metadata':
                key = next(k for k in files if k.startswith('wire/') and k.endswith('request.wire.json'))
                files[key] = b'{"model":"wrong"}'
                path = self.root / (name + '_bad_request.zip'); common.write(path, resign(files))
                with self.assertRaises(ValueError): verify.verify_bundle(path)

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='v064 한글 공백 ')
        cls.root = Path(cls.temp.name)
        cls.good_plan_path = cls.root / 'good.plan.json'
        cls.good_plan = design.build_plan(baseline_path(), 'v064_good', 'synthetic')
        common.save(cls.good_plan_path, cls.good_plan)
        cls.good_out = cls.root / 'v064_good'
        with server(cls.good_plan) as (endpoint, state), redirect_stdout(io.StringIO()):
            cls.good_result = run.execute(cls.good_plan_path, baseline_path(), cls.good_out, endpoint)
            assert state['chats'] == 18
        cls.bundle = Path(cls.good_result['evidence_zip'])
        cls.files = common.unzip(cls.bundle.read_bytes())
    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_mode(self, mode):
        plan_path = self.root / (mode + '.plan.json')
        plan = design.build_plan(baseline_path(), 'v064_' + mode, 'synthetic')
        common.save(plan_path, plan)
        out = self.root / plan['run_name']
        with server(plan, mode) as (endpoint, state), redirect_stdout(io.StringIO()):
            result = run.execute(plan_path, baseline_path(), out, endpoint)
        return common.load((out / 'summary.json').read_bytes()), result, state

    def test_positive_selectivity_real_sized_baseline_and_provenance(self):
        result = common.load(self.files['summary.json'])
        self.assertGreater(len(self.files['baseline/v058_evidence.zip']), 12 * 1024**2)
        self.assertIn('run/baseline/v057_evidence.zip', common.unzip(self.files['baseline/v058_evidence.zip']))
        self.assertEqual(result['provenance'], 'synthetic')
        self.assertIs(result['overall']['bounded_A_or_M_pilot'], True)
        self.assertEqual(result['observed_calls'], 18)
        self.assertEqual(len(result['directed_pairs']), 6)
        self.assertEqual(len(result['neutral_diagnostics']), 6)
        self.assertIn('synthetic', self.files['summary.ko.md'].decode('utf-8'))

    def test_fixed_valid_path_is_not_selective_control(self):
        result, receipt, state = self.run_mode('fixed')
        self.assertEqual(state['chats'], 18)
        self.assertTrue(all(r['strict_valid'] is True for r in result['rows']))
        self.assertIs(result['overall']['bounded_A_or_M_pilot'], False)

    def test_reversed_direction_and_non_topological_order_not_approved(self):
        for mode in ('reversed', 'reverse_nodes'):
            result, receipt, state = self.run_mode(mode)
            self.assertEqual(state['chats'], 18)
            self.assertTrue(all(r['proof_valid'] is True for r in result['rows']))
            self.assertIs(result['overall']['bounded_A_or_M_pilot'], False)
            if mode == 'reverse_nodes':
                self.assertTrue(all(r['strict_valid'] is False for r in result['rows']))

    def test_semantic_and_parsing_failures_continue_without_retry(self):
        for mode in ('bad_parent', 'parse_error'):
            result, receipt, state = self.run_mode(mode)
            self.assertEqual(state['chats'], 18)
            self.assertIsNot(result['overall']['bounded_A_or_M_pilot'], True)
            if mode == 'parse_error':
                self.assertEqual(result['limits']['logical_failures'], 0)
                self.assertTrue(all(r['strict_valid'] is None for r in result['rows']))
                self.assertIsNone(result['overall']['bounded_A_or_M_pilot'])

    def test_http_and_identity_stop_and_preserve_partial(self):
        for mode, calls in (('http_error', 1), ('wrong_model', 1), ('bad_metadata', 0)):
            result, receipt, state = self.run_mode(mode)
            self.assertEqual(state['chats'], calls)
            self.assertEqual(result['state'], 'stopped')
            self.assertIsNone(result['overall']['bounded_A_or_M_pilot'])
            self.assertEqual(result['observed_calls'], calls)
            self.assertTrue(all(r['actual_D'] is None for r in result['rows'] if r['status'] == 'not_observed'))

    def test_rehashed_report_plan_request_model_and_source_tampering_rejected(self):
        variants = []
        files = dict(self.files); obj = common.load(files['summary.json']); obj['rows'][0]['actual_D'] = 99
        files['summary.json'] = common.wire(obj); files['summary.ko.md'] = report.render(obj).encode('utf-8'); variants.append(files)
        files = dict(self.files); files['summary.ko.md'] += '\n새로운 성공 주장\n'.encode('utf-8'); variants.append(files)
        files = dict(self.files); obj = common.load(files['summary.json']); obj['full_complete'] = 1; files['summary.json'] = common.wire(obj); variants.append(files)
        files = dict(self.files); obj = common.load(files['plan.json']); obj['protocol']['depth_ranges']['T02'] = [1, 2]; obj.pop('plan_sha256'); obj['plan_sha256'] = common.sha(common.wire(obj)); files['plan.json'] = common.wire(obj); variants.append(files)
        files = dict(self.files); key = next(k for k in files if k.startswith('wire/') and k.endswith('request.wire.json')); obj = common.load(files[key]); obj['model'] = 'other'; files[key] = common.wire(obj); variants.append(files)
        files = dict(self.files); key = next(k for k in files if k.startswith('wire/') and k.endswith('response.raw.json')); obj = common.load(files[key]); obj['model'] = 'other'; files[key] = common.wire(obj); variants.append(files)
        files = dict(self.files); files['source/common.py'] += b'\n# changed\n'; variants.append(files)
        for index, files in enumerate(variants):
            with self.subTest(index=index):
                path = self.root / ('tamper_' + str(index) + '.zip'); common.write(path, resign(files))
                with self.assertRaises((ValueError, KeyError, TypeError, AssertionError)):
                    verify.verify_bundle(path)

    def test_existing_output_and_plan_lock_never_overwritten(self):
        before = self.bundle.read_bytes()
        with self.assertRaises((ValueError, FileExistsError)):
            run.execute(self.good_plan_path, baseline_path(), self.good_out, 'http://127.0.0.1:1')
        self.assertEqual(self.bundle.read_bytes(), before)

    def test_later_failure_preserves_prior_success_and_pending_crash(self):
        result, receipt, state = self.run_mode('late_http')
        self.assertEqual(state['chats'], 4)
        self.assertTrue(all(r['strict_valid'] is True for r in result['rows'][:3]))
        self.assertIsNone(result['overall']['bounded_A_or_M_pilot'])
        name = 'v064_interrupted'
        plan = design.build_plan(baseline_path(), name, 'synthetic')
        plan_path = self.root / 'interrupted.plan.json'; common.save(plan_path, plan)
        original = run.capture_call
        seen = []
        def interrupted(*args):
            if seen: raise KeyboardInterrupt('synthetic interruption')
            seen.append(True)
            return original(*args)
        out = self.root / name
        with server(plan) as (endpoint, state), patch.object(run, 'capture_call', side_effect=interrupted), redirect_stdout(io.StringIO()):
            receipt = run.execute(plan_path, baseline_path(), out, endpoint)
        partial = common.load((out / 'summary.json').read_bytes())
        self.assertEqual(receipt['state'], 'crashed')
        self.assertEqual(state['chats'], 1)
        self.assertIs(partial['rows'][0]['strict_valid'], True)
        self.assertIsNone(partial['rows'][1]['strict_valid'])
        self.assertIsNone(partial['overall']['bounded_A_or_M_pilot'])

    def test_request_content_tamper_with_rebuilt_record_and_event_hashes(self):
        files = dict(self.files)
        first = next(s for s in self.good_plan['slots'])['id']
        key = 'wire/' + first + '/request.wire.json'
        request = common.load(files[key]); request['options']['seed'] += 1
        files[key] = common.wire(request)
        record_key = 'records/' + first + '.json'
        record = common.load(files[record_key]); record['request_sha256'] = common.sha(files[key])
        files[record_key] = common.wire(record)
        events = [common.load(line) for line in files['records/events.jsonl'].splitlines()]
        tip = self.good_plan['plan_sha256']
        for event in events:
            event['record_sha256'] = common.sha(files['records/' + event['action']['id'] + '.json'])
            event['previous_hash'] = tip; event.pop('event_hash')
            event['event_hash'] = common.sha(common.wire(event)); tip = event['event_hash']
        files['records/events.jsonl'] = b''.join(common.wire(e) + b'\n' for e in events)
        path = self.root / 'rehashed_request.zip'; common.write(path, resign(files))
        with self.assertRaises(ValueError): verify.verify_bundle(path)

    def test_strict_json_and_archive_boundaries(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}', b'{"x":-1e999}', b' ' * (common.MAX_JSON + 1)):
            with self.assertRaises(ValueError): common.load(raw)
        for path in ('../x', '/x', 'a\\b', 'CON.txt', 'a/x. ', 'a:b'):
            with self.assertRaises(ValueError): common.safe_name(path)
        with self.assertRaises(ValueError): common.unzip(b'x' * (common.MAX_ZIP + 1))


if __name__ == '__main__':
    unittest.main()
