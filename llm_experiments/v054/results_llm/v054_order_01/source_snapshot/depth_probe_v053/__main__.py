"""selftest → prepare → run → audit → bundle. 이전 원문을 덮어쓰지 않는다."""
from __future__ import annotations
import argparse
import json
import sys
import unittest
from pathlib import Path
from .contracts import ContractError, read_json, require

def main(argv=None):
    parser = argparse.ArgumentParser(description='D 정의 명시 대조. 동일 모델·문제·seed에서 120회 실행한다.')
    sub = parser.add_subparsers(dest='command', required=True)
    part = sub.add_parser('selftest'); part.add_argument('--all', action='store_true', help='기존 v047~v052 시험까지 포함')
    part = sub.add_parser('prepare'); part.add_argument('--baseline-bundle', type=Path, required=True); part.add_argument('--out',type=Path,required=True)
    part = sub.add_parser('show'); part.add_argument('--plan',type=Path,required=True)
    part = sub.add_parser('run'); part.add_argument('--plan',type=Path,required=True); part.add_argument('--out',type=Path,required=True)
    for command in ('audit','bundle'):
        part = sub.add_parser(command); part.add_argument('--plan',type=Path,required=True); part.add_argument('--run',type=Path,required=True)
        if command=='bundle':
            part.add_argument('--out',type=Path,required=True)
    args = parser.parse_args(argv)
    try:
        if args.command=='selftest':
            root = Path(__file__).resolve().parent.parent
            names = [f'tests_v0{i}' for i in range(47,54)] if args.all else ['tests_v053']
            suite=unittest.TestSuite()
            for name in names:
                tests=unittest.TestLoader().discover(str(root/name),pattern='test_*.py',top_level_dir=str(root))
                require(tests.countTestCases()>0,'빈 시험 모음 금지: '+name); suite.addTests(tests)
            return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
        if args.command in ('prepare','show'):
            from .plan import prepare, validate_plan
            plan=prepare(args.baseline_bundle,args.out) if args.command=='prepare' else read_json(args.plan)
            validate_plan(plan)
            print(json.dumps({k:plan[k] for k in ('contract','plan_sha256','seeds','arms','directions','max_calls')},ensure_ascii=False,indent=2))
            print('오프라인 계획 확인 완료. 모델 추론은 실행하지 않았습니다.')
            return 0
        if args.command=='run':
            from .runner import execute
            report=execute(args.plan,args.out)
        elif args.command=='audit':
            from .audit import audit_run
            report=audit_run(args.plan,args.run,write_report=True)
        else:
            from .evidence import bundle_run
            report=bundle_run(args.plan,args.run,args.out)
            print('증거 ZIP:',args.out)
        keys=('data_integrity','data_complete','inference_calls','max_inference_calls','evidence_kind','run_state',
              'failure_stage','failure_kind','failure_slot_id','run_error')
        print(json.dumps({key:report[key] for key in keys},ensure_ascii=False,indent=2))
        if not report['data_complete'] and report.get('run_error'):
            print('실행 중단 원인: '+report['run_error'],file=sys.stderr)
        return 0 if args.command=='bundle' or report['data_complete'] else 3
    except (ContractError,OSError,KeyError,TypeError,ValueError) as exc:
        print(type(exc).__name__+': '+str(exc),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
