"""합성 HTTP 480회→서버 종료→재감사→ZIP→독립 검사. 실제 Ollama를 호출하지 않는다."""
from pathlib import Path
import contextlib
import io
import json
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tests_v048.fixtures import fake_server,build_v047
from paired_probe_v048.plan import prepare as p48
from paired_probe_v048.runner import execute as e48
from paired_probe_v048.__main__ import bundle as b48
from paired_probe_v049.plan import prepare
from paired_probe_v049.runner import execute
from paired_probe_v049.audit import audit_run
from paired_probe_v049.evidence import bundle_run
from independent_raw_check import check

import argparse
parser=argparse.ArgumentParser(description='실제 모델을 호출하지 않는 합성 재현')
parser.add_argument('--out-dir',type=Path,default=Path('synthetic_v049_reproduction'))
args=parser.parse_args()
OUT=args.out_dir
OUT.mkdir(parents=True,exist_ok=False)
with tempfile.TemporaryDirectory(prefix='v049_reproduction_') as td:
    temp=Path(td)
    with fake_server() as (state,endpoint),contextlib.redirect_stdout(io.StringIO()):
        oldp,oldr=build_v047(temp,endpoint)
        midp=temp/'v048.plan.json';midr=temp/'v048.run';midz=temp/'v048.zip'
        p48(oldr,midp,baseline_plan=oldp);e48(midp,midr);b48(midp,midr,midz)
        pp=temp/'v049.plan.json';rr=temp/'v049.run';plan=prepare(midz,pp)
        state.requests.clear();state.mode='original_false'
        before=execute(pp,rr);actual=len(state.requests)
    # 위 context를 나와 HTTP 서버가 종료된 뒤 감사한다.
    after=audit_run(pp,rr,write_report=True);assert before==after
    assert actual==after['inference_calls']==480 and after['evidence_kind']=='synthetic_fixture'
    assert after['arms']['original']['final_correct']==60
    archive=OUT/'SYNTHETIC_480_EVIDENCE.zip'
    bundle_run(pp,rr,archive)
    (OUT/'SYNTHETIC_480_SUMMARY.ko.md').write_bytes((rr/'summary.ko.md').read_bytes())
    independent=check(archive)
    result={'actual_fake_http_calls':actual,'new_real_model_inference':False,'offline_reaudit_equal':before==after,
            'data_integrity':after['data_integrity'],'data_complete':after['data_complete'],
            'arms':{a:{'assigned':x['assigned'],'final_correct':x['final_correct'],'strict_trace_correct':x['strict_trace_correct']} for a,x in after['arms'].items()},
            'interaction':after['factorial_interaction']['mean'],'independent':independent}
    (OUT/'SYNTHETIC_480_RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
