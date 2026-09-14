"""기존 배치의 가드·로그·진행 파일을 읽기만 한다. 실행/복구/삭제/모델 조회 없음."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
import common


def inspect(version: Path) -> dict:
    results=version/'results_llm';guard=results/'frozen_batch.started.json'
    answer={'version_directory':str(version.resolve()),'guard_exists':guard.is_file(),
            'classification':'not_started_by_this_launcher','inference_restarted':False,'modified_files':False}
    if not guard.exists():
        answer['existing_runs']=[str(p) for p in sorted(results.glob('v079_*'))] if results.is_dir() else []
        if answer['existing_runs']:answer['classification']='results_without_guard_requires_review'
        return answer
    g=common.load(guard.read_bytes());name=g.get('run_name')
    if not isinstance(name,str) or not re.fullmatch(r'v079_[A-Za-z0-9_-]{1,70}',name):raise ValueError('가드의 RunName 오류')
    run=results/name;status=run/'status.json';evidence=results/(name+'_evidence.zip');receipt=results/(name+'_independent.json')
    answer.update(guard=g,run_directory=str(run),log=str(results/'automation_logs'/name/'run.log'),
                  evidence=str(evidence) if evidence.is_file() else None,independent_json=str(receipt) if receipt.is_file() else None)
    dispatched=len(list((run/'wire').glob('*/dispatch.started.json')))
    observed=len(list((run/'wire').glob('*/response.raw.json')))
    starts=len(list((run/'records').glob('*.started.json')))
    answer.update(dispatch_markers=dispatched,preserved_responses=observed,action_start_markers=starts)
    if status.is_file():
        st=common.load(status.read_bytes());answer['status']=st
        if st.get('state')=='complete':answer['classification']='complete_recorded'
        elif dispatched==0:answer['classification']='stopped_before_inference_dispatch'
        else:answer['classification']='partial_or_stopped_after_dispatch'
    else:
        answer['classification']='guard_before_observed_dispatch' if dispatched==0 else 'interrupted_status_missing'
    answer['note']='가드는 추론 전에도 생긴다. dispatch 표지는 요청 시도 수이며 모델 완료 증거가 아니다. complete_recorded는 상태 파일 판독이며 별도 verify 결과를 대신하지 않는다.'
    return answer

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--version-dir',type=Path,required=True);a=p.parse_args()
    try:print(json.dumps(inspect(a.version_dir),ensure_ascii=False,indent=2))
    except (OSError,ValueError,TypeError) as e:p.exit(2,str(e)+'\n')
