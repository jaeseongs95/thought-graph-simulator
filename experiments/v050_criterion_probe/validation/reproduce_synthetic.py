"""전체 규모 합성 HTTP 실행. 원래 원식만 양성 조건 오답을 반환하도록 한다."""
from __future__ import annotations
import contextlib,io,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tests_v050.fixtures import shared
from criterion_probe_v050.plan import prepare
from criterion_probe_v050.runner import execute
from criterion_probe_v050.evidence import bundle_run
f=shared();state=f['state'];state.mode='original_false';state.requests.clear();state.metadata_boundary=state.show_calls
pp=f['root']/'negative.plan.json';run=f['root']/'negative.run';prepare(f['bundle'],pp)
r=execute(pp,run)
assert len(state.requests)==560 and r['inference_calls']==560
assert r['arms']['oneshot_original']['strict_trace_correct']==60
for a in ('oneshot_commuted','staged_commuted','staged_pipeline'):assert r['arms'][a]['strict_trace_correct']==80
out=ROOT/'validation/SYNTHETIC_560_EVIDENCE.zip'
bundle_run(pp,run,out)
(ROOT/'validation/SYNTHETIC_560_SUMMARY.ko.md').write_text((run/'summary.ko.md').read_text(encoding='utf-8'),encoding='utf-8')
print(json.dumps({'synthetic_only':True,'calls':560,'strict_trace':{a:v['strict_trace_correct'] for a,v in r['arms'].items()},'bundle':str(out)},ensure_ascii=False,indent=2))
# 프로세스 종료 시 fixture의 HTTP 서버도 종료한다. 재감사는 별도 프로세스에서 수행한다.
