"""실제 Ollama 없이 기본 960회 CLI 경로와 서버 종료 후 감사를 재현한다."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests_v048.fixtures import fake_server, build_v047
from paired_probe_v048.contracts import require, read_json, write_json
from test_support.subprocess_text import run_text_process


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    require(not args.out.exists(),'기존 검증 폴더를 덮어쓰지 않습니다.')
    args.out.mkdir(parents=True)
    log=[]
    def cli(*parts):
        command=[sys.executable,'-m','paired_probe_v048',*map(str,parts)]
        result=run_text_process(command,cwd=ROOT,timeout=45)
        log.extend(['$ '+' '.join(command),result.stdout,result.stderr,'returncode='+str(result.returncode)])
        (args.out/'cli.log').write_text('\n'.join(log),encoding='utf-8')
        require(result.returncode==0,'CLI 검증 실패: '+str(parts))
    with fake_server() as (state,endpoint):
        oldplan,oldrun=build_v047(args.out,endpoint)
        state.requests.clear();state.mode='original_false';state.metadata_boundary=state.show_calls
        plan=args.out/'external_plan'/'v048.plan.json';run=args.out/'run'
        cli('prepare','--baseline-run',oldrun,'--baseline-plan',oldplan,'--out',plan)
        cli('show','--plan',plan)
        require(not state.requests,'계획 단계에서 추론이 발생했습니다.')
        cli('run','--plan',plan,'--out',run)
        require(len(state.requests)==960,'실제 기록된 가짜 HTTP 요청이 960회가 아닙니다.')
        before=read_json(run/'summary.json')
        actual_count=len(state.requests)
    # 이 시점부터 합성 서버도 종료돼 있다. 보존 원문만으로 감사한다.
    cli('audit','--plan',plan,'--run',run)
    after=read_json(run/'summary.json')
    require(before==after,'서버 종료 후 재감사 결과가 달라졌습니다.')
    archive=args.out/'SYNTHETIC_960_EVIDENCE.zip'
    cli('bundle','--plan',plan,'--run',run,'--out',archive)
    checks={'evidence_kind':after['evidence_kind'],'new_model_inference':False,
        'actual_fake_http_calls':actual_count,'server_stopped_before_reaudit':True,
        'offline_reaudit_equal':before==after,'data_complete':after['data_complete'],
        'model_scores_are_fixture_outputs':True,
        'fixture_scores':{a:after['arms'][a]['final_correct'] for a in ('original','commuted','pipeline')},
        'fixture_pipeline_strict':after['arms']['pipeline']['strict_trace_correct'],
        'reference_seed_excluded':after['discovery_seeds_excluded'],
        'plan_sha256':after['plan_sha256'],'bundle':str(archive)}
    write_json(args.out/'RESULT.json',checks)
    print(json.dumps(checks,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
