"""로컬 합성 HTTP 서버. 평가용 정답 생성은 이 시험 모듈 안에서만 수행한다."""
from __future__ import annotations
import contextlib, copy, io, shutil, tempfile
from pathlib import Path
from unittest.mock import patch
from tests_v053.fixtures import shared as previous_shared, graph_payload
from tests_v052.fixtures import explicit_answer as original_answer
from depth_probe_v053.evidence import bundle_run as previous_bundle
from order_probe_v054.contracts import strict_json
from order_probe_v054.design import PROBLEMS
from order_probe_v054.plan import prepare
from order_probe_v054.runner import execute

_cached = None

def shared():
    global _cached
    if _cached is None:
        old = previous_shared(); root = old['root']; bundle = root/'v053_for_v054.zip'
        with contextlib.redirect_stdout(io.StringIO()):
            previous_bundle(root/'v53.plan', root/'v53.run', bundle)
            plan = prepare(bundle, root/'v54.plan'); old['state'].requests.clear()
            report = execute(root/'v54.plan', root/'v54.run')
        _cached = {'root':root, 'state':old['state'], 'plan':plan, 'report':report, 'bundle':bundle}
    return _cached

def first_path(problem):
    """순서만 따르는 음성 대조. 선택된 경로 정리는 합성 서버의 출력 생성에만 사용한다."""
    ns = []; lookup = {}
    for atom in problem['facts']:
        ident = 'f'+str(len(ns)); lookup[atom] = ident
        ns.append({'id':ident, 'atom':atom, 'rule':None, 'parents':[]})
    while problem['goal'] not in lookup:
        progressed = False
        for rule in problem['rules']:
            if rule['conclusion'] not in lookup and all(a in lookup for a in rule['premises']):
                ident = 'n'+str(len(ns))
                ns.append({'id':ident, 'atom':rule['conclusion'], 'rule':rule['id'], 'parents':[lookup[a] for a in rule['premises']]})
                lookup[rule['conclusion']] = ident; progressed = True
                if problem['goal'] in lookup: break
        if not progressed: raise ValueError('시험 문제의 목표가 도달 불가')
    final = lookup[problem['goal']]; byid = {n['id']:n for n in ns}; used = set()
    def visit(ident):
        if ident in used: return
        used.add(ident)
        for parent in byid[ident]['parents']: visit(parent)
    visit(final)
    return {'nodes':[n for n in ns if n['id'] in used], 'final_node_id':final}

def answer(body, mode):
    if mode not in ('first_branch', 'inverse_direction', 'only_original_control', 'misspelled_rule'):
        return original_answer(body, mode)
    problem = strict_json(body['messages'][1]['content'][len('problem: '):])
    if mode == 'first_branch': return first_path(problem)
    if mode == 'inverse_direction':
        direction = 'shallow' if '최종 지지 깊이가 가장 큰 경로' in body['messages'][0]['content'] else 'deep'
        return graph_payload(problem, direction)
    if mode == 'only_original_control':
        unchanged = problem['rules'] == PROBLEMS[problem['id']]['rules']
        return original_answer(body, 'perfect' if unchanged else 'ignore_roles')
    result = original_answer(body, 'perfect')
    result['nodes'][-1]['rule'] = 'unknown_rule_id'
    return result

@contextlib.contextmanager
def copied():
    base = shared()
    with tempfile.TemporaryDirectory(prefix='v054_copy_') as td:
        root = Path(td); plan = root/'external.plan'; run = root/'run'
        shutil.copyfile(base['root']/'v54.plan',plan); shutil.copytree(base['root']/'v54.run',run)
        yield root, plan, run, base

@contextlib.contextmanager
def executed(mode='perfect'):
    base = shared(); state = base['state']; state.mode = mode; state.requests.clear(); state.metadata_boundary = state.show_calls
    try:
        with tempfile.TemporaryDirectory(prefix='v054_exec_') as td, patch('tests_v052.fixtures.explicit_answer', side_effect=answer):
            root = Path(td); plan = root/'external.plan'; run = root/'run'
            with contextlib.redirect_stdout(io.StringIO()):
                prepare(base['bundle'],plan); report = execute(plan,run)
            yield root, plan, run, report, state
    finally:
        state.mode = 'perfect'
