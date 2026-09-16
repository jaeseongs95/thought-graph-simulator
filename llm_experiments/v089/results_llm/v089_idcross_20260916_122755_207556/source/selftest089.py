"""시험 결과를 JSON과 원문 로그로 남긴다. 테스트는 실제 Ollama 대신 합성 응답만 사용한다."""
from __future__ import annotations
from pathlib import Path
import argparse,json,time,unittest,sys
import core089

class Result(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.success_ids=[]
    def addSuccess(self,test):
        super().addSuccess(test);self.success_ids.append(test.id())

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    suite=unittest.defaultTestLoader.discover(str(core089.ROOT/'tests'),pattern='test_*.py')
    started=time.perf_counter();runner=unittest.TextTestRunner(verbosity=2,resultclass=Result);r=runner.run(suite)
    output={'contract':'v089-development-selftest-r1','provenance':'synthetic_and_offline_only',
        'actual_qwen_inference_calls':0,'tests_run':r.testsRun,'passed':len(r.success_ids),
        'failures':len(r.failures),'errors':len(r.errors),'skipped':len(r.skipped),
        'elapsed_seconds':time.perf_counter()-started,'passed_ids':r.success_ids,
        'failure_details':[{'test':t.id(),'traceback':s} for t,s in r.failures+r.errors],
        'skip_details':[{'test':t.id(),'reason':reason} for t,reason in r.skipped],
        'source_hashes':core089.source_hashes(),'python_version':sys.version,
        'research_hypothesis_tested':False}
    core089.save(a.out,output)
    print(json.dumps({k:output[k] for k in ('tests_run','passed','failures','errors','skipped','actual_qwen_inference_calls')},ensure_ascii=False))
    return 0 if r.wasSuccessful() else 2

if __name__=='__main__':raise SystemExit(main())
