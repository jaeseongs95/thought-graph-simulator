"""다운로드 이후의 설치/오프라인 검사/명시적 실행. 모델 갱신·서버 시작·자동 재시도 없음."""
from __future__ import annotations
import argparse,contextlib,hashlib,json,os,re,shutil,subprocess,sys,uuid
from datetime import datetime
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parent
PREFIX='llm_experiments/v072/probe/'
EXPECTED='7a995a40d9db35cf06472b421ace231083e2d0b705d9bc6a336f3d35d0eae535'
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
            if m.get('contract')!='v072-source-release-r1':raise LaunchError('잘못된 배포 manifest')
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
        if p.name=='thought-graph-simulator' or (p/'llm_experiments/v071').is_dir():candidates.append(p)
    candidates += [Path(r'D:\codex\AI논문\thought-graph-simulator'),Path.home()/'Desktop/thought-graph-simulator']
    for p in candidates:
        if p.is_dir():return p.resolve()
    raise LaunchError('저장소를 찾지 못했습니다. -RepoRoot로 기존 thought-graph-simulator 폴더를 지정하세요.')

def choose_baseline(repo,given=None):
    if given:
        p=given.expanduser().resolve()
        if not p.is_file() or digest(p)!=EXPECTED:raise LaunchError('지정한 v071 evidence의 파일/해시가 다릅니다.')
        return p
    folders=[repo/'llm_experiments/v071/results_llm',repo/'results_llm',Path.home()/'Downloads']
    for folder in folders:
        if not folder.is_dir():continue
        for p in sorted(folder.glob('v071*_evidence*.zip'),key=lambda f:f.stat().st_mtime,reverse=True):
            if p.is_file() and not p.is_symlink() and p.stat().st_size<=100*1024**2 and digest(p)==EXPECTED:return p.resolve()
    raise LaunchError('이번 v071 evidence ZIP을 찾지 못했습니다. 원본을 Downloads 또는 v071/results_llm에 두거나 -Baseline으로 지정하세요.')

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
        except OSError as e:raise LaunchError('이미 v072 자동화가 실행 중입니다. 중복 시작하지 않습니다.') from e
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':
                import msvcrt;msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl;fcntl.flock(f,fcntl.LOCK_UN)

def install(source,repo):
    m,hs=manifest_at(source);version=repo/'llm_experiments/v072';target=version/'probe';version.mkdir(parents=True,exist_ok=True)
    if target.exists():
        try:verify_tree(target,hs);return target
        except LaunchError:
            backup=version/('probe.backup_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]);target.rename(backup);print('이전 v072 소스를 보존했습니다:',backup,flush=True)
    target.mkdir()
    for n in hs:
        dest=target/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/n,dest)
    verify_tree(target,hs)
    manifest=version/'RELEASE_MANIFEST.json'
    if manifest.exists():manifest.rename(version/('RELEASE_MANIFEST.previous_'+uuid.uuid4().hex[:8]+'.json'))
    manifest.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
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
    repo=choose_repo(repo);baseline=choose_baseline(repo,baseline);version=repo/'llm_experiments/v072'
    with lock(version/'results_llm/automation.lock'):
        guard=version/'results_llm/frozen_batch.started.json'
        if not check_only and guard.exists():raise LaunchError('이 v072 배치는 이미 시작했습니다. 새 RunName으로 반복하지 않습니다. 기존 evidence/로그를 확인하세요: '+str(guard))
        target=install(source,repo);name=run_name or 'v072_gemma_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        if not re.fullmatch(r'v072_[A-Za-z0-9_-]{1,70}',name):raise LaunchError('잘못된 실행 이름')
        plan=version/'experiments'/(name+'.plan.json');out=version/'results_llm'/name;logdir=version/'results_llm/automation_logs'/name
        if plan.exists() or out.exists() or logdir.exists():raise LaunchError('기존 계획/결과/로그는 덮어쓰지 않습니다.')
        logdir.mkdir(parents=True,exist_ok=False);log=logdir/'run.log'
        env=dict(os.environ,V072_BASELINE=str(baseline),PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
        python=[sys.executable,'-X','utf8','-B'];step=lambda args:invoke(python+args,target,log,env)
        print('저장소:',repo,'\n기준선:',baseline,'\n실행 이름:',name,'\n로그:',log,flush=True)
        step(['-m','unittest','discover','-s','tests','-p','test_*.py' if all_tests else 'test_logic.py','-v'])
        args=['run.py','prepare','--baseline',str(baseline),'--run-name',name,'--out',str(plan)]
        if synthetic:args+=['--synthetic']
        step(args)
        if check_only:
            print('무추론 검사 완료. 실제 Ollama 조회/시작/다운로드/추론 없음.',flush=True);return {'check_only':True,'plan':str(plan),'log':str(log)}
        print('이제 기존 gemma3:4b로 최대 100회 동일 계약을 검사합니다. 모델 다운로드·갱신·서버 시작은 하지 않습니다.',flush=True)
        with guard.open('x',encoding='utf-8') as f:json.dump({'run_name':name,'plan':str(plan),'automatic_retry':False},f,ensure_ascii=False)
        step(['run.py','execute','--plan',str(plan),'--baseline',str(baseline),'--out',str(out),'--endpoint',endpoint])
        bundle=out.with_name(out.name+'_evidence.zip');receipt=out.with_name(out.name+'_independent.json')
        if not bundle.is_file() or not receipt.is_file():raise LaunchError('완료 증거 또는 독립 검산 파일 없음')
        r=json.loads(receipt.read_text(encoding='utf-8'))
        if r.get('verified') is not True or r.get('state')!='complete' or r.get('inference_calls')!=json.loads(plan.read_text(encoding='utf-8'))['protocol']['max_inference_calls']:raise LaunchError('완료/독립 검산 상태 불일치')
        print((out/'summary.ko.md').read_text(encoding='utf-8'),flush=True)
        print('\n분석용 ZIP:',bundle,'\nSHA-256:',digest(bundle),'\n독립 검산:',receipt,flush=True)
        if os.name=='nt' and not no_open:subprocess.Popen(['explorer.exe','/select,',str(bundle)])
        return {'check_only':False,'bundle':str(bundle),'receipt':str(receipt),'log':str(log)}

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--repo-root',type=Path);p.add_argument('--baseline',type=Path);p.add_argument('--check-only',action='store_true');p.add_argument('--all-tests',action='store_true');p.add_argument('--run-name');p.add_argument('--endpoint',default='http://127.0.0.1:11434');p.add_argument('--synthetic',action='store_true');p.add_argument('--no-open',action='store_true');a=p.parse_args(argv)
    try:workflow(ROOT,a.repo_root,a.baseline,a.check_only,a.all_tests,a.run_name,a.endpoint,a.synthetic,a.no_open);return 0
    except (OSError,ValueError,LaunchError,KeyboardInterrupt) as e:
        print('\n자동화 중단: '+str(e),file=sys.stderr);print('원문·기존 결과를 보존했습니다. 모델 재요청/자동 새 실행/서버 시작/모델 갱신은 하지 않았습니다.',file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
