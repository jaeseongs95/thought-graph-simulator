"""기존 합성 HTTP 서버를 재사용하되 사용자 Ollama에는 접근하지 않는다."""
from __future__ import annotations
import atexit
import contextlib
import io
import shutil
import tempfile
from pathlib import Path
from tests_v048.fixtures import fake_server, build_v047

_shared=None

def shared():
    global _shared
    if _shared is not None:return _shared
    from paired_probe_v048.plan import prepare as p48
    from paired_probe_v048.runner import execute as e48
    from paired_probe_v048.__main__ import bundle as b48
    from paired_probe_v049.plan import prepare
    from paired_probe_v049.runner import execute
    temp=tempfile.TemporaryDirectory(prefix='v049_fixture_');root=Path(temp.name)
    ctx=fake_server();state,endpoint=ctx.__enter__()
    with contextlib.redirect_stdout(io.StringIO()):
        pp,rr=build_v047(root,endpoint)
        p=p48(rr,root/'v048.plan.json',baseline_plan=pp)
        e48(root/'v048.plan.json',root/'v048.run')
        archive=root/'v048.zip';b48(root/'v048.plan.json',root/'v048.run',archive)
        plan=prepare(archive,root/'v049.plan.json')
        state.requests.clear();state.mode='perfect'
        report=execute(root/'v049.plan.json',root/'v049.run')
    _shared={'root':root,'state':state,'endpoint':endpoint,'bundle':archive,'plan':plan,'report':report}
    def cleanup():
        ctx.__exit__(None,None,None);temp.cleanup()
    atexit.register(cleanup)
    return _shared

@contextlib.contextmanager
def copied():
    fixture=shared()
    with tempfile.TemporaryDirectory(prefix='v049_test_') as td:
        root=Path(td);p=root/'external.plan.json';out=root/'run'
        shutil.copyfile(fixture['root']/'v049.plan.json',p)
        shutil.copytree(fixture['root']/'v049.run',out)
        yield root,p,out,fixture

@contextlib.contextmanager
def executed(mode='perfect'):
    from paired_probe_v049.plan import prepare
    from paired_probe_v049.runner import execute
    f=shared();s=f['state'];s.mode=mode;s.requests.clear();s.counts.clear();s.metadata_boundary=s.show_calls
    with tempfile.TemporaryDirectory(prefix='v049_exec_') as td:
        root=Path(td);p=root/'external.plan.json';out=root/'run'
        plan=prepare(f['bundle'],p)
        with contextlib.redirect_stdout(io.StringIO()):report=execute(p,out)
        yield root,p,out,plan,report,s
    s.mode='perfect'
