"""v088 실제 증거와 초기 facts anchor만 사용한다. 대상/향후 답으로 선정하지 않는다."""
from pathlib import Path
import os
import subprocess
import sys
import zipfile
import core089 as core
import bridge089
from baseline087 import validated_prefix

CONTRACT_KEYS = (
    'identity', 'model', 'problems', 'reference_plans', 'depth_ranges', 'seeds',
    'conditions', 'reference_conditions', 'candidate_orders', 'candidate_ids',
    'headers', 'selector_schema', 'api_defaults', 'generation_schema', 'num_predict',
    'request_utf8_byte_limit', 'timeout_seconds', 'id_assignments', 'frozen_profiles',
    'numeric_compare_schema', 'lookup_schema', 'numeric_compare_header', 'lookup_header',
    'allocated_id_header', 'allocated_id_prefix', 'units',
)
_CACHE = {}

def select_initial_anchors(archive, protocol):
    """baseline trial ID 오름차순의 첫 유효 facts 요청. 응답/summary는 읽지 않는다."""
    plan = core.load(archive.read('plan.json'))
    names = set(archive.namelist())
    trials = sorted((t for t in plan['trials'] if t['phase'] == 'end_to_end'
                     and t['generator_arm'] == 'baseline'), key=lambda t: t['id'])
    anchors, provenance = [], []
    for problem in protocol['problems']:
        for kind in ('shallow', 'deep'):
            path = protocol['reference_plans'][problem['id']][
                protocol['reference_conditions'][int(kind == 'deep')]]
            candidates = []
            for trial in trials:
                if trial['problem_id'] != problem['id']:
                    continue
                sid = trial['id'] + '_rule_00'
                name = 'wire/' + sid + '/request.wire.json'
                if name not in names:
                    continue
                raw = archive.read(name)
                body = core.load(raw)
                data = core.load(body['messages'][0]['content'].split('\n\ninput: ', 1)[1])
                if (data['provided_route_plan']['rule_ids'] != path
                        or len(data['history']) != 1 or validated_prefix(body) is None):
                    continue
                candidates.append((trial, sid, raw, body))
            if not candidates:
                raise ValueError('유효 초기 facts 없음: ' + problem['id'] + '/' + kind)
            trial, sid, raw, body = candidates[0]
            aid = problem['id'] + '_' + kind + '_r00'
            anchors.append(dict(id=aid, problem_id=problem['id'], route_kind=kind,
                rule_position=0, rule_id=path[0], source_trial_id=trial['id'],
                source_slot_id=sid, source_request_sha256=core.sha(raw), request_body=body))
            provenance.append(dict(anchor_id=aid, source_trial_id=trial['id'],
                valid_prefix_candidates=len(candidates), prefix_valid=True,
                target_response_used_for_selection=False, future_responses_used_for_selection=False,
                summary_used_for_selection=False))
    return anchors, provenance

def validate_inputs(path, run_verifier=True):
    path = Path(path)
    raw = path.read_bytes()
    s = core.spec()
    digest = core.sha(raw)
    if digest != s['baseline_sha256']:
        raise ValueError('v088 baseline ZIP SHA-256 불일치')
    if (digest, run_verifier) in _CACHE:
        return _CACHE[digest, run_verifier]
    with zipfile.ZipFile(path) as z:
        old = core.load(z.read('plan.json'))
        if old['plan_sha256'] != s['baseline_plan_sha256']:
            raise ValueError('v088 기준선 plan 불일치')
        for key in CONTRACT_KEYS:
            if not core.exact(old['protocol'][key], s[key]):
                raise ValueError('유지할 기존 계약 변경: ' + key)
        source_files = {n[7:]: z.read(n) for n in z.namelist() if n.startswith('source/')}
        local = {p.relative_to(core.ROOT/'frozen088').as_posix(): p.read_bytes()
                 for p in (core.ROOT/'frozen088').rglob('*')
                 if p.is_file() and '__pycache__' not in p.parts}
        if source_files != local:
            raise ValueError('v088 동결 소스가 원본과 다름')
        a, pv = select_initial_anchors(z, s)
        if not core.exact(a, core.load((core.ROOT/'data/anchors.json').read_bytes())):
            raise ValueError('초기 facts anchor 불일치')
        if not core.exact(pv, core.load((core.ROOT/'data/anchor_provenance.json').read_bytes())):
            raise ValueError('anchor 선정 provenance 불일치')
    result = dict(baseline_sha256=digest, anchors=len(a), retained_source_files=len(local),
                  new_model_calls=0)
    if run_verifier:
        script = core.ROOT/'frozen088/verify088.py'
        completed = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(script), str(path)],
            cwd=script.parent, env=dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1'),
            capture_output=True, timeout=900)
        if completed.returncode:
            raise ValueError('v088 독립 검산 실패: ' + completed.stderr.decode('utf-8', errors='replace'))
        receipt = core.load(completed.stdout)
        if (receipt.get('verified') is not True or receipt.get('state') != 'complete'
                or receipt.get('observed_calls') != 3136):
            raise ValueError('v088 기준선 미완료/검산 불일치')
        result['prior_receipt'] = receipt
    _CACHE[digest, run_verifier] = result
    return result
