"""다운로드 이후 설치·실험·독립 검증 자동화. 다운로드, 모델 갱신, 추론 재시도 없음."""
from __future__ import annotations
import argparse,contextlib,hashlib,json,os,re,shutil,subprocess,sys,time,urllib.request,urllib.error,uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from package_check_v056 import verify_package
PACKAGE='v056_layout_probe'

class StepError(RuntimeError):pass

@contextlib.contextmanager
def experiment_lock(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as f:
        if path.stat().st_size==0:f.write(b'0');f.flush()
        f.seek(0)
        try:
            if os.name=='nt':
                import msvcrt;msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl;fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as e:raise StepError('다른 v056 자동화가 실행 중입니다. 중복 추론을 시작하지 않습니다.') from e
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)

def install(stage,repo):
    stage=stage.resolve();repo=repo.resolve();m=verify_package(stage);target=repo/PACKAGE
    if target.exists():
        try:
            existing=verify_package(target)
            if existing==m:return target,False
        except (ValueError,OSError,KeyError):pass
        backup=repo/(PACKAGE+'.backup_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8])
        target.rename(backup);print('기존 소스를 보존 백업했습니다:',backup,flush=True)
    target.mkdir(parents=True,exist_ok=False)
    for name in [*m['file_hashes'],'PACKAGE_MANIFEST.json']:
        dst=target/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(stage/name,dst)
    verify_package(target);return target,True

def free_name(results,requested=None):
    def available(name):return not any(results.glob(name+'*'))
    if requested:
        if not re.fullmatch(r'[A-Za-z0-9_-]+',requested):raise StepError('안전하지 않은 RunName')
        if not available(requested):raise StepError('기존 결과/계획 보존: '+requested)
        return requested
    for n in range(1,10000):
        name=f'v056_layout_{n:02d}'
        if available(name):return name
    raise StepError('빈 실행 이름을 찾지 못했습니다.')

def run_step(args,cwd,log_path):
    print('\n실행:',subprocess.list2cmdline([str(a) for a in args]),flush=True)
    env=dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
    with log_path.open('ab') as log:
        log.write(('\nCOMMAND '+repr([str(a) for a in args])+'\n').encode('utf-8'));log.flush()
        p=subprocess.Popen([str(a) for a in args],cwd=str(cwd),env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        try:
            for raw in iter(p.stdout.readline,b''):
                log.write(raw);log.flush();print(raw.decode('utf-8').rstrip('\r\n'),flush=True)
            code=p.wait()
        except BaseException:
            if p.poll() is None:p.terminate();p.wait()
            raise
        finally:p.stdout.close()
        log.write(f'\nEXIT {code}\n'.encode());log.flush()
    if code:raise StepError(f'하위 단계 실패. Exit={code}. 자동 재시도 없음. 명령: {args}; 로그: {log_path}')

def server_version(base):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(base+'/api/version',timeout=3) as response:
        if response.status!=200:raise StepError('서버 HTTP 상태: '+str(response.status))
        raw=response.read(8*1024*1024+1)
        if len(raw)>8*1024*1024:raise StepError('서버 응답 크기 초과')
        data=json.loads(raw)
    if not isinstance(data,dict) or not isinstance(data.get('version'),str):raise StepError('Ollama 서버 응답 형식')
    return data

def ensure_server(endpoint,logs):
    parsed=urlsplit(endpoint);base=f'{parsed.scheme}://{parsed.netloc}'
    if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost') or parsed.username or parsed.password:raise StepError('로컬 Ollama endpoint만 허용합니다.')
    try:return server_version(base)
    except (OSError,ValueError,urllib.error.URLError,StepError):pass
    if parsed.port not in (None,11434):raise StepError('사용자 정의 포트 서버가 꺼졌습니다. 다른 주소로 자동 변경하지 않습니다.')
    exe=shutil.which('ollama')
    if not exe:
        candidate=Path(os.environ.get('LOCALAPPDATA',''))/'Programs/Ollama/ollama.exe'
        if candidate.is_file():exe=str(candidate)
    if not exe:raise StepError('Ollama 실행 파일을 찾지 못했습니다. 기존 설치/모델은 변경하지 않았습니다.')
    logs.mkdir(parents=True,exist_ok=True)
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0
    with (logs/'ollama_server.log').open('ab') as stream:
        subprocess.Popen([exe,'serve'],stdout=stream,stderr=subprocess.STDOUT,creationflags=flags)
    # 여기서 재확인하는 것은 서버 상태뿐이다. /api/chat은 호출하지 않는다.
    for _ in range(30):
        time.sleep(1)
        try:return server_version(base)
        except (OSError,ValueError,urllib.error.URLError,StepError):pass
    raise StepError('Ollama 시작 확인 실패. 모델 다운로드/추론을 수행하지 않았습니다.')

def automate(stage,repo,baseline=None,all_tests=False,run_name=None,open_result=True):
    if sys.version_info<(3,10):raise StepError('Python 3.10 이상이 필요합니다.')
    repo=repo.resolve()
    if not repo.is_dir():raise StepError('기존 저장소 폴더 없음: '+str(repo))
    results=repo/'results_llm';results.mkdir(exist_ok=True)
    baseline=(baseline or results/'v055_model_02_evidence.zip').resolve()
    if not baseline.is_file():raise StepError('실제 기준선 ZIP 없음: '+str(baseline))
    with experiment_lock(results/'automation_logs/v056.lock'):
        target,changed=install(stage,repo);print('v056 설치:',target,'(신규)' if changed else '(전 파일 확인 후 재사용)',flush=True)
        logs=results/'automation_logs'/('v056_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]);logs.mkdir(parents=True,exist_ok=False)
        log=logs/'automation.log';name=free_name(results,run_name);plan=results/(name+'.plan.json');out=results/name;bundle=results/(name+'_evidence.zip')
        run=lambda args:run_step([sys.executable,*args],target,log)
        print('이번 RunName:',name,'\n자동화 로그:',log,flush=True)
        run(['-m','layout_probe_v056','selftest','--all' if all_tests else '--quick'])
        run(['-m','layout_probe_v056','prepare','--baseline-bundle',baseline,'--out',plan])
        run(['-m','layout_probe_v056','show','--plan',plan])
        data=json.loads(plan.read_text(encoding='utf-8'));server=ensure_server(data['baseline']['config']['endpoint'],logs);print('Ollama:',server,flush=True)
        print('두 기존 모델 식별을 확인합니다. 모델을 새로 받거나 갱신하지 않습니다.',flush=True)
        run(['tools/preflight_v056.py','--plan',plan,'--out',results/(name+'.preflight.json')])
        run(['-m','layout_probe_v056','run','--plan',plan,'--out',out])
        run(['-m','layout_probe_v056','audit','--plan',plan,'--run',out])
        run(['-m','layout_probe_v056','bundle','--plan',plan,'--run',out,'--out',bundle])
        independent=results/(name+'_independent.json')
        run(['tools/independent_verify_v056.py',bundle,'--out',independent])
        print((out/'summary.ko.md').read_text(encoding='utf-8'),flush=True)
        digest=hashlib.sha256(bundle.read_bytes()).hexdigest()
        receipt={'completed':True,'inference_calls':480,'bundle':str(bundle),'sha256':digest,'independent':str(independent),'log':str(log)}
        (logs/'completion.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
        print('\n완료. 분석용 파일:',bundle,'\nSHA-256:',digest,'\n독립 검증:',independent,flush=True)
        if open_result and os.name=='nt':subprocess.Popen(['explorer.exe','/select,',str(bundle)])
        return receipt

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',type=Path,required=True);ap.add_argument('--baseline-bundle',type=Path);ap.add_argument('--all-tests',action='store_true');ap.add_argument('--run-name');ap.add_argument('--no-open',action='store_true');a=ap.parse_args()
    try:automate(Path(__file__).resolve().parents[1],a.repo_root,a.baseline_bundle,a.all_tests,a.run_name,not a.no_open);return 0
    except (StepError,OSError,ValueError,KeyboardInterrupt) as e:
        print('\n자동화 중단: '+type(e).__name__+': '+str(e),file=sys.stderr)
        print('기존 결과·계획·preflight·원문은 보존했습니다. 자동 새 실행/재시도/삭제하지 않습니다.',file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
