"""설치된 소스로 전체 합성 실행·독립 검산. 실제 HTTP exchange를 교체하여 모델 추론을 하지 않는다."""
from pathlib import Path
from unittest.mock import patch
import argparse,contextlib,json
import core089 as c,design089 as d,fixtures089 as f,run089 as run

def main():
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise FileExistsError('새 검증 경로가 필요합니다: '+str(a.out))
    a.out.mkdir(parents=True);plan=d.make_plan(a.baseline,'v089_full_synthetic','synthetic',True);c.save(a.out/'plan.json',plan)
    exchange=f.fake_exchange()
    with (a.out/'execution.log').open('w',encoding='utf-8')as log,contextlib.redirect_stdout(log),patch.object(run,'exchange',exchange):
        result=run.execute(a.out/'plan.json',a.baseline,a.out/plan['run_name'],'http://127.0.0.1:11434')
    receipt=c.load(Path(result['independent_json']).read_bytes())
    if receipt['state']!='complete' or not receipt['verified'] or receipt['inference_calls']!=3824:raise AssertionError('합성 완료 검산 불일치')
    c.save(a.out/'reproduction.json',dict(result=result,actual_qwen_calls=0,dispatch_mock_calls=exchange.count['chat'],source_hashes=c.source_hashes()))
    print(json.dumps(dict(result=result,actual_qwen_calls=0,verified=True),ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
