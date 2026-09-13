"""시험용 합성 모델만 사용한다. 실제 사용자 모델에 연결하지 않는다."""
import contextlib
import io
import shutil
import tempfile
from pathlib import Path
from tests_v052.fixtures import shared as old_shared, generic_trace, to_explicit
from adm_diagnostic_v052.evidence import bundle_run as bundle_old
from depth_probe_v053.plan import prepare
from depth_probe_v053.runner import execute

_cached=None

def shared():
    global _cached
    if _cached is not None:
        return _cached
    old=old_shared(); root=old['root']
    bundle=root/'v052_completed_for_v053.zip'
    with contextlib.redirect_stdout(io.StringIO()):
        bundle_old(root/'v52.plan',root/'v52.run',bundle)
        plan=prepare(bundle,root/'v53.plan')
        old['state'].requests.clear()
        report=execute(root/'v53.plan',root/'v53.run')
    _cached={'root':root,'state':old['state'],'plan':plan,'report':report,'bundle':bundle}
    return _cached

@contextlib.contextmanager
def copied():
    base=shared()
    with tempfile.TemporaryDirectory(prefix='v053_copy_') as td:
        root=Path(td); plan=root/'external.plan'; run=root/'run'
        shutil.copyfile(base['root']/'v53.plan',plan);shutil.copytree(base['root']/'v53.run',run)
        yield root,plan,run,base

@contextlib.contextmanager
def executed(mode):
    base=shared(); state=base['state'];state.mode=mode;state.requests.clear();state.metadata_boundary=state.show_calls
    try:
        with tempfile.TemporaryDirectory(prefix='v053_exec_') as td:
            root=Path(td);plan=root/'external.plan';run=root/'run'
            with contextlib.redirect_stdout(io.StringIO()):
                prepare(base['bundle'],plan);report=execute(plan,run)
            yield root,plan,run,report,state
    finally:
        state.mode='perfect'

def graph_payload(problem,direction='shallow'):
    full=to_explicit(generic_trace(problem,'instance',direction,0))
    return {key:full[key] for key in ('nodes','final_node_id')}
