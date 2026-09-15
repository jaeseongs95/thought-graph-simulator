"""다운로드 이후의 설치/오프라인 검사/명시적 실행. 모델 갱신·서버 시작·자동 재시도 없음."""
from __future__ import annotations
import argparse,contextlib,hashlib,json,os,re,shutil,subprocess,sys,uuid
from datetime import datetime
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parent
PREFIX='llm_experiments/v085/probe/'
EXPECTED='98b6963b27ecfb4c111a543da7d6c23ace37b02303804d64e3e4ddfe0ae63304'
class LaunchError(RuntimeError):pass

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def verify_tree(root,hashes):
    actual=set()
    for p in root.rglob('*'):
        if '__pycache__' in p.parts:continue
        if p.is_symlink():raise LaunchError('소스 symlink 거부: '+str(p))
        if p.is_file():actual.add(p.relative_to(root).as_posix())
    if actual!=set(hashes):raise LaunchError('소스 파일 누락/추가: '+str(sorted(actual^set(hashes))))
    for name,h in hashes.items():
        pp=PurePosixPath(name)
        if pp.is_absolute() or '..' in pp.parts or '\\' in name or pp.as_posix()!=name or not (root/name).resolve().is_relative_to(root.resolve()):raise LaunchError('manifest 경로 오류')
        if digest(root/name)!=h:raise LaunchError('소스 내용 변경: '+name)

def manifest_at(source):
    candidates=[source.parent/'RELEASE_MANIFEST.json',source.parents[2]/'RELEASE_MANIFEST.json']
    for p in candidates:
        if p.is_file():
            m=json.loads(p.read_text(encoding='utf-8'))
            if m.get('contract')!='v085-source-release-r1':raise LaunchError('잘못된 배포 manifest')
            hs=m['file_hashes']
            if any(not n.startswith(PREFIX) for n in hs):raise LaunchError('배포 prefix 오류')
            short={n[len(PREFIX):]:h for n,h in hs.items()};verify_tree(source,short);return m,short
    raise LaunchError('RELEASE_MANIFEST.json을 찾지 못했습니다. 자동화 파일을 다시 저장하거나 정식 ZIP을 전체 추출하세요.')

def choose_repo(given):
    if given:
        p=given.expanduser().resolve()
        if not p.is_dir():raise LaunchError('저장소 폴더 없음: '+str(p))
        return p
    candidates=[]
    for p in [Path.cwd(),*Path.cwd().parents]:
        if p.name=='thought-graph-simulator' or (p/'llm_experiments/v084').is_dir():candidates.append(p)
    candidates += [Path(r'D:\codex\AI논문\thought-graph-simulator'),Path.home()/'Desktop/thought-graph-simulator']
    for p in candidates:
        if p.is_dir():return p.resolve()
    raise LaunchError('저장소를 찾지 못했습니다. -RepoRoot로 기존 thought-graph-simulator 폴더를 지정하세요.')

def choose_baseline(repo,given=None):
    if given:
        p=given.expanduser().resolve()
        if not p.is_file() or digest(p)!=EXPECTED:raise LaunchError('지정한 v084 evidence의 파일/해시가 다릅니다.')
        return p
    folders=[repo/'llm_experiments/v084/results_llm',repo/'results_llm',Path.home()/'Downloads']
    for folder in folders:
        if not folder.is_dir():continue
        for p in sorted(folder.glob('v084*_evidence*.zip'),key=lambda f:f.stat().st_mtime,reverse=True):
            if p.is_file() and not p.is_symlink() and p.stat().st_size<=100*1024**2 and digest(p)==EXPECTED:return p.resolve()
    raise LaunchError('이번 v084 evidence ZIP을 찾지 못했습니다. 원본을 Downloads 또는 v084/results_llm에 두거나 -Baseline으로 지정하세요.')

@contextlib.contextmanager
def lock(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as f:
        if path.stat().st_size==0:f.write(b'0');f.flush()
        f.seek(0)
        try:
            if os.name=='nt':
                import msvcrt;msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl;fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as e:raise LaunchError('이미 v085 자동화가 실행 중입니다. 중복 시작하지 않습니다.') from e
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':
                import msvcrt;msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl;fcntl.flock(f,fcntl.LOCK_UN)

def install(source,repo):
    m,hs=manifest_at(source)
    version=repo/'llm_experiments/v085';target=version/'probe'
    version.mkdir(parents=True,exist_ok=True)
    manifest=version/'RELEASE_MANIFEST.json'
    if target.exists():
        verify_tree(target,hs)
        if not manifest.is_file() or json.loads(manifest.read_text(encoding='utf-8'))!=m:
            raise LaunchError('기존 v085 배포 manifest가 다릅니다. 자동 교체하지 않습니다.')
        return target
    if manifest.exists():raise LaunchError('probe 없는 기존 manifest가 있습니다. 자동 덮어쓰기하지 않습니다.')
    target.mkdir()
    for n in hs:
        dest=target/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/n,dest)
    verify_tree(target,hs)
    with manifest.open('x',encoding='utf-8') as f:
        f.write(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
    return target

def invoke(args,cwd,log,env):
    args=[str(x) for x in args];print('\n실행:',subprocess.list2cmdline(args),flush=True)
    with log.open('ab') as f:
        f.write(('\nCOMMAND '+repr(args)+'\n').encode());f.flush()
        child=subprocess.Popen(args,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        try:
            for line in iter(child.stdout.readline,b''):
                f.write(line);f.flush();print(line.decode('utf-8',errors='replace').rstrip(),flush=True)
            code=child.wait()
        except BaseException:
            if child.poll() is None:child.terminate();child.wait()
            raise
        finally:child.stdout.close()
        f.write(f'\nEXIT {code}\n'.encode());f.flush()
    if code:raise LaunchError(f'하위 단계 종료 {code}. 자동 재시도하지 않습니다. 원문/로그: {log}')

def workflow(source,repo,baseline,check_only=False,all_tests=False,run_name=None,endpoint='http://127.0.0.1:11434',synthetic=False,no_open=False):
    if sys.version_info<(3,10):raise LaunchError('Python 3.10 이상 필요')
    repo=choose_repo(repo);baseline=choose_baseline(repo,baseline);version=repo/'llm_experiments/v085'
    with lock(version/'results_llm/automation.lock'):
        guard=version/'results_llm/frozen_batch.started.json'
        if not check_only and guard.exists():raise LaunchError('이 v085 배치는 이미 시작했습니다. 새 RunName으로 반복하지 않습니다. 기존 evidence/로그를 확인하세요: '+str(guard))
        target=install(source,repo);name=run_name or 'v085_valuelink_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        if not re.fullmatch(r'v085_[A-Za-z0-9_-]{1,70}',name):raise LaunchError('잘못된 실행 이름')
        plan=version/'experiments'/(name+'.plan.json');out=version/'results_llm'/name;logdir=version/'results_llm/automation_logs'/name
        if plan.exists() or out.exists() or logdir.exists():raise LaunchError('기존 계획/결과/로그는 덮어쓰지 않습니다.')
        logdir.mkdir(parents=True,exist_ok=False);log=logdir/'run.log'
        env=dict(os.environ,V085_BASELINE=str(baseline),PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
        python=[sys.executable,'-X','utf8','-B'];step=lambda args:invoke(python+args,target,log,env)
        print('저장소:',repo,'\n기준선:',baseline,'\n실행 이름:',name,'\n로그:',log,flush=True)
        step(['selftest085.py','--out',str(logdir/'selftest.json')])
        step(['cases085.py','--check'])
        step(['calibrate085.py','--out',str(logdir/'calibration.json')])
        args=['run085.py','prepare','--baseline',str(baseline),'--run-name',name,'--out',str(plan)]
        if synthetic:args+=['--synthetic']
        step(args)
        if check_only:
            print('무추론 검사 완료. 실제 Ollama 조회/시작/다운로드/추론 없음.',flush=True);return {'check_only':True,'plan':str(plan),'log':str(log)}
        print('이제 기존 qwen3:4b-instruct로 사전 동결 값 비교·ID 연결 분리 대조를 실행합니다. 실제 경로 길이에 따라 동결 계획의 최대 횟수 내에서 추론합니다. 모델 다운로드·갱신·서버 시작은 하지 않습니다.',flush=True)
        step(['run085.py','execute','--plan',str(plan),'--baseline',str(baseline),'--out',str(out),'--endpoint',endpoint])
        bundle=out.with_name(out.name+'_evidence.zip');receipt=out.with_name(out.name+'_independent.json')
        if not bundle.is_file() or not receipt.is_file():raise LaunchError('완료 증거 또는 독립 검산 파일 없음')
        r=json.loads(receipt.read_text(encoding='utf-8'))
        if r.get('verified') is not True or r.get('state')!='complete' or not (0 < r.get('inference_calls',-1) <= json.loads(plan.read_text(encoding='utf-8'))['protocol']['max_inference_calls']):raise LaunchError('완료/독립 검산 상태 불일치')
        print((out/'summary.ko.md').read_text(encoding='utf-8'),flush=True)
        print('\n분석용 ZIP:',bundle,'\nSHA-256:',digest(bundle),'\n독립 검산:',receipt,flush=True)
        if os.name=='nt' and not no_open:subprocess.Popen(['explorer.exe','/select,',str(bundle)])
        return {'check_only':False,'bundle':str(bundle),'receipt':str(receipt),'log':str(log)}

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--repo-root',type=Path);p.add_argument('--baseline',type=Path);p.add_argument('--check-only',action='store_true');p.add_argument('--inspect-only',action='store_true');p.add_argument('--all-tests',action='store_true');p.add_argument('--run-name');p.add_argument('--endpoint',default='http://127.0.0.1:11434');p.add_argument('--synthetic',action='store_true');p.add_argument('--no-open',action='store_true');a=p.parse_args(argv)
    try:
        if a.inspect_only:
            if a.check_only:raise LaunchError('--check-only와 --inspect-only를 함께 지정하지 마세요.')
            from inspect_state import inspect
            print(json.dumps(inspect(choose_repo(a.repo_root)/'llm_experiments/v085'),ensure_ascii=False,indent=2));return 0
        workflow(ROOT,a.repo_root,a.baseline,a.check_only,a.all_tests,a.run_name,a.endpoint,a.synthetic,a.no_open);return 0
    except (OSError,ValueError,LaunchError,KeyboardInterrupt) as e:
        print('\n자동화 중단: '+str(e),file=sys.stderr);print('원문·기존 결과를 보존했습니다. 모델 재요청/자동 새 실행/서버 시작/모델 갱신은 하지 않았습니다.',file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
