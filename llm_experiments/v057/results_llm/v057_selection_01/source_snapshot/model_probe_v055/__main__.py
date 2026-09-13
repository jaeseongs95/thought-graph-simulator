"""capture → selftest → prepare → run → audit → bundle."""
from __future__ import annotations
import argparse,json,sys,unittest
from pathlib import Path
from .contracts import ContractError,require,read_json

def main(argv=None):
    parser=argparse.ArgumentParser(description='두 소형 모델 D 제어 비교. 로컬 전용, 총 240회, 자동 다운로드/재시도 없음')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('selftest');p.add_argument('--all',action='store_true',help='기존 v047~v054 시험 포함')
    p=sub.add_parser('capture',help='로컬 모델 metadata만 조회. 추론 0회');p.add_argument('--baseline-bundle',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p=sub.add_parser('prepare',help='오프라인 계획 생성');p.add_argument('--baseline-bundle',type=Path,required=True);p.add_argument('--capture',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p=sub.add_parser('show');p.add_argument('--plan',type=Path,required=True)
    p=sub.add_parser('run');p.add_argument('--plan',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    for command in ('audit','bundle'):
        p=sub.add_parser(command);p.add_argument('--plan',type=Path,required=True);p.add_argument('--run',type=Path,required=True)
        if command=='bundle':p.add_argument('--out',type=Path,required=True)
    a=parser.parse_args(argv)
    try:
        if a.command=='selftest':
            root=Path(__file__).resolve().parent.parent;suite=unittest.TestSuite()
            for name in ([f'tests_v0{i}' for i in range(47,56)] if a.all else ['tests_v055']):
                tests=unittest.TestLoader().discover(str(root/name),pattern='test_*.py',top_level_dir=str(root))
                require(tests.countTestCases()>0,'빈 시험 모음 금지: '+name);suite.addTests(tests)
            return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
        if a.command=='capture':
            from .metadata import capture
            r=capture(a.baseline_bundle,a.out)
            print(json.dumps({'state':r['state'],'inference_calls':0,'models':{k:v['model'] for k,v in r['identities'].items()},'capture':str(a.out/'capture.json')},ensure_ascii=False,indent=2));return 0
        if a.command in ('prepare','show'):
            from .plan import prepare,validate_plan
            p=prepare(a.baseline_bundle,a.capture,a.out) if a.command=='prepare' else read_plan_json(a.plan);validate_plan(p)
            print(json.dumps({k:p[k] for k in ('contract','plan_sha256','max_calls','seeds','model_keys')},ensure_ascii=False,indent=2))
            print('오프라인 계획 확인 완료. 추론 실행 없음.');return 0
        if a.command=='run':
            from .runner import execute
            r=execute(a.plan,a.out)
        elif a.command=='audit':
            from .audit import audit_run
            r=audit_run(a.plan,a.run,write_report=True)
        else:
            from .evidence import bundle_run
            r=bundle_run(a.plan,a.run,a.out);print('증거 ZIP:',a.out)
        print(json.dumps({k:r[k] for k in ('data_integrity','data_complete','inference_calls','max_inference_calls','failure_stage','failure_kind','failure_slot_id','run_error')},ensure_ascii=False,indent=2))
        if not r['data_complete'] and r['run_error']:print('실행 중단: '+r['run_error'],file=sys.stderr)
        return 0 if a.command=='bundle' or r['data_complete'] else 3
    except (ContractError,OSError,ValueError,KeyError,TypeError) as exc:
        print(type(exc).__name__+': '+str(exc),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
