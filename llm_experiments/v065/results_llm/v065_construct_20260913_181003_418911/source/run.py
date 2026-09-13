"""준비와 실행을 분리한 v065 실행기. 다운로드·서버 시작·재시도 없음."""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from common import ROOT, exact, load, save, sha, sources, source_hashes, spec, wire, write, zip_bytes


def endpoint_ok(endpoint):
    p = urllib.parse.urlsplit(endpoint)
    if (p.scheme != 'http' or p.hostname not in ('127.0.0.1', 'localhost', '::1')
            or p.username or p.password or p.query or p.fragment or p.path not in ('', '/')):
        raise ValueError('Only an explicit local HTTP Ollama endpoint is allowed')
    return endpoint.rstrip('/')


def exchange(endpoint, path, body, timeout):
    request = urllib.request.Request(endpoint + path, data=body,
                                     headers={'Content-Type': 'application/json'},
                                     method='GET' if body is None else 'POST')
    started = time.perf_counter_ns()
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(1024**2 + 1)
            code = response.status
        if len(raw) > 1024**2:
            return code, raw, 'response_size_limit', time.perf_counter_ns() - started
        return code, raw, None, time.perf_counter_ns() - started
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(1024**2 + 1), None, time.perf_counter_ns() - started
    except (OSError, urllib.error.URLError) as exc:
        return None, b'', type(exc).__name__, time.perf_counter_ns() - started


def identity_matches(items, expected):
    if len(items) != 3 or any(i['http_status'] != 200 or i['error'] is not None for i in items):
        return False
    try:
        server, tags, show = [load(base64.b64decode(i['response_b64'], validate=True)) for i in items]
        candidates = [m for m in tags['models'] if m.get('name') == expected['model']
                      or m.get('model') == expected['model']]
        if len(candidates) != 1:
            return False
        got = {'model': expected['model'], 'digest': candidates[0]['digest'],
               'server': server, 'details': show.get('details', candidates[0].get('details', {})),
               'template': show.get('template'), 'model_info': show.get('model_info', {}),
               'parameters': show.get('parameters')}
        want = {k: expected[k] for k in got}
        for value in (got, want):
            if value['parameters'] is not None:
                if not isinstance(value['parameters'], str):
                    return False
                value['parameters'] = sorted(value['parameters'].split('\n'))
        return exact(got, want)
    except (ValueError, KeyError, TypeError):
        return False


def capture_metadata(plan, action, endpoint, out):
    items = []
    for index, (name, path) in enumerate((('server', '/api/version'), ('tags', '/api/tags'), ('show', '/api/show'))):
        body = wire({'model': plan['identity']['model']}) if name == 'show' else None
        prefix = out / 'metadata' / action['id'] / str(index)
        write(Path(str(prefix) + '.request.json'), body or b'')
        code, raw, error, elapsed = exchange(endpoint, path, body, spec()['timeout_seconds'])
        write(Path(str(prefix) + '.response.raw.json'), raw)
        items.append({'name': name, 'path': path,
                      'request_b64': None if body is None else base64.b64encode(body).decode(),
                      'response_b64': base64.b64encode(raw).decode(), 'http_status': code,
                      'error': error, 'elapsed_ns': elapsed})
        if code != 200 or error is not None:
            break
    return {'id': action['id'], 'kind': 'metadata', 'items': items,
            'identity_ok': identity_matches(items, plan['identity'])}


def capture_call(plan, action, endpoint, out):
    from design import request_for
    slot = next(s for s in plan['slots'] if s['id'] == action['id'])
    request = wire(request_for(plan, slot))
    if len(request) > spec()['request_utf8_byte_limit']:
        raise ValueError('request UTF-8 byte budget exceeded before dispatch')
    prefix = out / 'wire' / slot['id']
    write(prefix / 'request.wire.json', request)
    code, raw, error, elapsed = exchange(endpoint, '/api/chat', request, spec()['timeout_seconds'])
    write(prefix / 'response.raw.json', raw)
    return {'id': slot['id'], 'kind': 'call', 'http_status': code, 'error': error,
            'elapsed_ns': elapsed, 'request_sha256': sha(request), 'response_sha256': sha(raw),
            'response_b64': base64.b64encode(raw).decode()}


def call_stop_reason(record, model):
    if record['error'] is not None:
        return 'transport_error'
    if record['http_status'] != 200:
        return 'http_error'
    try:
        response = load(base64.b64decode(record['response_b64'], validate=True))
    except (ValueError, UnicodeError):
        return None  # Malformed output is observed; it does not trigger a retry.
    if not isinstance(response, dict) or response.get('model') != model:
        return 'identity_error'
    count = response.get('eval_count')
    if type(count) is int and count > spec()['num_predict']:
        return 'generation_budget_exceeded'
    return None


def finalize(out):
    from report import summarize, render
    from verify import verify_bundle
    plan = load((out / 'plan.json').read_bytes())
    if not exact(plan['source_hashes'], source_hashes()):
        raise ValueError('source changed; use the frozen source to finalize')
    event_path = out / 'records/events.jsonl'
    events = [load(line) for line in event_path.read_bytes().splitlines()] if event_path.exists() else []
    records = [load((out / 'records' / (e['action']['id'] + '.json')).read_bytes()) for e in events]
    started = list((out / 'records').glob('*.started.json'))
    if not (out / 'status.json').exists():
        save(out / 'status.json', {'state': 'crashed', 'reason': 'interrupted_action',
             'completed_actions': len(events), 'started_actions': len(started),
             'inference_calls': sum(load(p.read_bytes())['action']['kind'] == 'call' for p in started),
             'plan_sha256': plan['plan_sha256']})
    status = load((out / 'status.json').read_bytes())
    calls = [{k: v for k, v in record.items() if k != 'kind'}
             for record in records if record['kind'] == 'call']
    summary = summarize(plan, calls, status['state'])
    save(out / 'summary.json', summary)
    write(out / 'summary.ko.md', render(summary).encode('utf-8'))
    files = {}
    for path in sorted(out.rglob('*')):
        if path.is_file():
            if path.is_symlink():
                raise ValueError('run symlink refused')
            files[path.relative_to(out).as_posix()] = path.read_bytes()
    files['MANIFEST.json'] = wire({'contract': 'v065-evidence-r1',
                                   'file_hashes': {name: sha(raw) for name, raw in files.items()}})
    bundle = out.parent / (out.name + '_evidence.zip')
    write(bundle, zip_bytes(files))
    receipt = verify_bundle(bundle)
    save(out.parent / (out.name + '_independent.json'), receipt)
    return {'state': status['state'], 'evidence_zip': str(bundle.resolve()),
            'independent_verification': str((out.parent / (out.name + '_independent.json')).resolve()),
            'inference_calls': status['inference_calls']}


def execute(plan_path, baseline_path, out, endpoint):
    from design import build_plan
    endpoint = endpoint_ok(endpoint)
    plan = load(plan_path.read_bytes())
    expected = build_plan(baseline_path, plan['run_name'], plan['provenance'])
    if not exact(plan, expected):
        raise ValueError('plan/source/baseline mismatch')
    if out.exists() or out.name != plan['run_name']:
        raise FileExistsError('existing output or RunName mismatch')
    lock = plan_path.with_name(plan_path.name + '.started')
    write(lock, wire({'plan_sha256': plan['plan_sha256'], 'automatic_resume': False}))
    out.mkdir(parents=True, exist_ok=False)
    save(out / 'plan.json', plan)
    save(out / 'runtime.json', {'endpoint': endpoint, 'provenance': plan['provenance']})
    write(out / 'baseline/v064_evidence.zip', baseline_path.read_bytes())
    for name, raw in sources().items():
        write(out / 'source' / name, raw)
    (out / 'records').mkdir(exist_ok=True)
    write(out / 'records/events.jsonl', b'')
    tip = plan['plan_sha256']
    completed = started = calls = 0
    state, reason = 'complete', None
    try:
        for action in plan['actions']:
            write(out / 'records' / (action['id'] + '.started.json'),
                  wire({'action': action, 'plan_sha256': plan['plan_sha256']}))
            started += 1
            if action['kind'] == 'call':
                if calls >= spec()['max_inference_calls']:
                    raise ValueError('inference budget exhausted')
                calls += 1
                record = capture_call(plan, action, endpoint, out)
                failure = call_stop_reason(record, plan['identity']['model'])
            else:
                record = capture_metadata(plan, action, endpoint, out)
                failure = None if record['identity_ok'] else 'metadata_identity_error'
            raw = wire(record)
            write(out / 'records' / (action['id'] + '.json'), raw)
            event = {'action': action, 'record_sha256': sha(raw), 'previous_hash': tip}
            event['event_hash'] = sha(wire(event))
            with (out / 'records/events.jsonl').open('ab') as stream:
                stream.write(wire(event) + b'\n')
                stream.flush()
            tip = event['event_hash']
            completed += 1
            print(f"{completed}/{len(plan['actions'])}: {action['id']}", flush=True)
            if failure:
                state, reason = 'stopped', failure
                break
    except BaseException as exc:
        state, reason = 'crashed', 'interrupted_action'
        print('Execution interrupted: ' + type(exc).__name__, file=sys.stderr, flush=True)
    save(out / 'status.json', {'state': state, 'reason': reason, 'completed_actions': completed,
         'started_actions': started, 'inference_calls': calls, 'plan_sha256': plan['plan_sha256']})
    return finalize(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare', help='offline only; no HTTP requests')
    prepare.add_argument('--baseline', type=Path, required=True)
    prepare.add_argument('--run-name', required=True)
    prepare.add_argument('--out', type=Path, required=True)
    prepare.add_argument('--synthetic', action='store_true')
    run = commands.add_parser('execute', help='explicit user execution: up to 12 model calls')
    run.add_argument('--plan', type=Path, required=True)
    run.add_argument('--baseline', type=Path, required=True)
    run.add_argument('--out', type=Path, required=True)
    run.add_argument('--endpoint', default='http://127.0.0.1:11434')
    finish = commands.add_parser('finalize', help='offline export of preserved interrupted run')
    finish.add_argument('--run', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            from design import build_plan
            plan = build_plan(args.baseline, args.run_name, 'synthetic' if args.synthetic else 'live')
            save(args.out, plan)
            if not exact(load(args.out.read_bytes()), plan):
                raise ValueError('written plan does not roundtrip')
            result = {'prepared': str(args.out.resolve()), 'new_model_inference': False,
                      'max_inference_calls_when_executed': 12, 'plan_sha256': plan['plan_sha256']}
        elif args.command == 'execute':
            result = execute(args.plan, args.baseline, args.out, args.endpoint)
        else:
            result = finalize(args.run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get('state', 'complete') == 'complete' else 2
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
