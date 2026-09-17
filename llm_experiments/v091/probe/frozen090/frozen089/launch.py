"""v089 전용 설치/검증/실행. v088 소스·manifest·결과·guard를 수정하지 않는다."""
from __future__ import annotations
import argparse, contextlib, hashlib, json, os, re, shutil, subprocess, sys, uuid
from datetime import datetime
from pathlib import Path, PurePosixPath
ROOT=Path(__file__).resolve().parent
PREFIX='llm_experiments/v089/probe/'
EXPECTED='2d9c2324aa9a9a64d97beb74cc158b24f1e7cf4f59df599a4a154ff110fcfbff'
CONTRACT='v089-source-release-r1'
INSTALLED_MANIFEST='RELEASE_MANIFEST_v089.json'
class LaunchError(RuntimeError):
    pass

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()

def verify_tree(root, hashes):
    if root.is_symlink():
        raise LaunchError('소스 root symlink 거부: '+str(root))
    actual=set()
    for p in root.rglob('*'):
        if '__pycache__' in p.parts:
            continue
        if p.is_symlink():
            raise LaunchError('소스 symlink 거부: '+str(p))
        if p.is_file():
            actual.add(p.relative_to(root).as_posix())
    if actual != set(hashes):
        raise LaunchError('소스 파일 누락/추가: '+str(sorted(actual^set(hashes))))
    for name,h in hashes.items():
        part=PurePosixPath(name)
        if (not name or part.is_absolute() or '..' in part.parts or '\\' in name
                or part.as_posix()!=name or not (root/name).resolve().is_relative_to(root.resolve())):
            raise LaunchError('manifest 경로 오류')
        if digest(root/name)!=h:
            raise LaunchError('소스 내용 변경: '+name)

def manifest_hashes(manifest):
    if set(manifest)!={'contract','file_hashes'} or manifest.get('contract')!=CONTRACT:
        raise LaunchError('배포 contract/manifest 불일치')
    hashes=manifest['file_hashes']
    if not isinstance(hashes,dict) or not hashes:
        raise LaunchError('빈 manifest')
    if any(not isinstance(n,str) or not n.startswith(PREFIX) or not isinstance(h,str)
           or not re.fullmatch(r'[0-9a-f]{64}',h) for n,h in hashes.items()):
        raise LaunchError('manifest hash/prefix 불일치')
    return {name[len(PREFIX):]:value for name,value in hashes.items()}

def manifest_at(source):
    source=Path(source).resolve()
    installed=source.parent/INSTALLED_MANIFEST
    release=source.parents[2]/'RELEASE_MANIFEST.json'
    # 전용 manifest가 있는데 틀리면 다른 상위 manifest로 우회하지 않는다.
    path=installed if installed.is_file() else release
    if not path.is_file():
        raise LaunchError('v089 manifest 없음: 정식 ZIP 전체 또는 내장 PS1을 사용하세요.')
    try:
        from core089 import load
        manifest=load(path.read_bytes())
        hashes=manifest_hashes(manifest)
        verify_tree(source,hashes)
        return manifest,hashes
    except (OSError,ValueError,TypeError,KeyError) as exc:
        raise LaunchError('v089 manifest 검증 거부: '+str(path)+': '+str(exc)) from exc

def migration_blockers(version):
    candidates=[version/'results_llm/frozen_batch.started.json']
    candidates.extend((version/'experiments').glob('v089_*.plan.json.started'))
    results=version/'results_llm'
    if results.is_dir():
        for child in results.iterdir():
            if child.is_dir() and child.name.startswith('v089_'):
                candidates.extend(child/name for name in ('plan.json','runtime.json','status.json'))
    return [p for p in candidates if p.exists()]

def install(source, repo):
    manifest,hashes=manifest_at(source)
    version=repo/'llm_experiments/v089'
    target=version/'probe'
    marker=version/INSTALLED_MANIFEST
    version.mkdir(parents=True,exist_ok=True)
    if target.exists():
        verify_tree(target,hashes)
        if not marker.is_file() or json.loads(marker.read_text(encoding='utf-8'))!=manifest:
            raise LaunchError('기존 v089 설치 manifest가 없거나 다릅니다. 덮어쓰지 않습니다.')
        return target
    if marker.exists() or migration_blockers(version):
        raise LaunchError('v089 설치/실행 흔적이 있어 새 소스를 덮어쓸 수 없습니다.')
    staging=version/('.probe_staging_'+uuid.uuid4().hex)
    staging.mkdir()
    created_target=False
    created_marker=False
    try:
        for name in hashes:
            dest=staging/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source/name,dest)
        verify_tree(staging,hashes)
        staging.rename(target)
        created_target=True
        with marker.open('x',encoding='utf-8') as f:
            created_marker=True
            f.write(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        verify_tree(target,hashes)
        return target
    except BaseException:
        if created_marker:
            marker.unlink(missing_ok=True)
        if created_target:
            shutil.rmtree(target)
        if staging.exists():
            shutil.rmtree(staging)
        raise

def write_installation_receipt(source,target,logdir):
    manifest,hashes=manifest_at(target)
    protocol=json.loads((target/'data/protocol.json').read_text(encoding='utf-8'))
    receipt=dict(contract='v089-installation-receipt-r1',source_path=str(source),installed_path=str(target),
        release_contract=manifest['contract'],source_files=len(hashes),source_hashes=hashes,
        protocol_sha256=digest(target/'data/protocol.json'),
        planned_trials=protocol['trial_count'],max_inference_calls=protocol['max_inference_calls'],
        installed_manifest=str(target.parent/INSTALLED_MANIFEST),actual_model_calls=0)
    with (logdir/'installation.json').open('x',encoding='utf-8') as f:
        json.dump(receipt,f,ensure_ascii=False,indent=2)
    print('실제 설치 contract:',manifest['contract'],'/ protocol:',receipt['protocol_sha256'],flush=True)
    print('실제 설치 launch.py SHA-256:',hashes['launch.py'],flush=True)

def choose_repo(given):
    if given:
        p=given.expanduser().resolve()
        if not p.is_dir():raise LaunchError('저장소 폴더 없음: '+str(p))
        return p
    candidates=[]
    for p in [Path.cwd(),*Path.cwd().parents]:
        if p.name=='thought-graph-simulator' or (p/'llm_experiments/v088').is_dir():candidates.append(p)
    candidates += [Path(r'D:\codex\AI논문\thought-graph-simulator'),Path.home()/'Desktop/thought-graph-simulator']
    for p in candidates:
        if p.is_dir():return p.resolve()
    raise LaunchError('저장소를 찾지 못했습니다. -RepoRoot로 기존 thought-graph-simulator 폴더를 지정하세요.')

def choose_baseline(repo,given=None):
    if given:
        p=given.expanduser().resolve()
        if not p.is_file() or digest(p)!=EXPECTED:raise LaunchError('지정한 v088 evidence의 파일/해시가 다릅니다.')
        return p
    folders=[repo/'llm_experiments/v088/results_llm',repo/'results_llm',Path.home()/'Downloads']
    for folder in folders:
        if not folder.is_dir():continue
        for p in sorted(folder.glob('v088*_evidence*.zip'),key=lambda f:f.stat().st_mtime,reverse=True):
            if p.is_file() and not p.is_symlink() and p.stat().st_size<=320*1024**2 and digest(p)==EXPECTED:return p.resolve()
    raise LaunchError('이번 v088 evidence ZIP을 찾지 못했습니다. 원본을 Downloads 또는 v088/results_llm에 두거나 -Baseline으로 지정하세요.')

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
        except OSError as e:raise LaunchError('이미 v089 자동화가 실행 중입니다. 중복 시작하지 않습니다.') from e
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':
                import msvcrt;msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl;fcntl.flock(f,fcntl.LOCK_UN)


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
    if synthetic and not check_only:raise LaunchError('합성 계획은 라이브 실행할 수 없습니다.')
    if sys.version_info<(3,10):raise LaunchError('Python 3.10 이상 필요')
    repo=choose_repo(repo);baseline=choose_baseline(repo,baseline);version=repo/'llm_experiments/v089'
    with lock(version/'results_llm/automation.lock'):
        guard=version/'results_llm/frozen_batch.started.json'
        if not check_only and guard.exists():raise LaunchError('이 v089 배치는 이미 시작했습니다. 새 RunName으로 반복하지 않습니다. 기존 evidence/로그를 확인하세요: '+str(guard))
        target=install(source,repo);name=run_name or 'v089_idcross_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        if not re.fullmatch(r'v089_[A-Za-z0-9_-]{1,70}',name):raise LaunchError('잘못된 실행 이름')
        plan=version/'experiments'/(name+'.plan.json');out=version/'results_llm'/name;logdir=version/'results_llm/automation_logs'/name
        if plan.exists() or out.exists() or logdir.exists():raise LaunchError('기존 계획/결과/로그는 덮어쓰지 않습니다.')
        logdir.mkdir(parents=True,exist_ok=False);log=logdir/'run.log'
        env=dict(os.environ,V089_BASELINE=str(baseline),PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
        python=[sys.executable,'-X','utf8','-B'];step=lambda args:invoke(python+args,target,log,env)
        print('저장소:',repo,'\n기준선:',baseline,'\n실행 이름:',name,'\n로그:',log,flush=True)
        write_installation_receipt(source,target,logdir)
        step(['selftest089.py','--out',str(logdir/'selftest.json')])
        step(['calibrate089.py','--out',str(logdir/'calibration.json')])
        args=['run089.py','prepare','--baseline',str(baseline),'--run-name',name,'--out',str(plan)]
        if synthetic:args+=['--synthetic']
        step(args)
        if check_only:
            print('무추론 검사 완료. 실제 Ollama 조회/시작/다운로드/추론 없음.',flush=True);return {'check_only':True,'plan':str(plan),'log':str(log)}
        print('이제 기존 qwen3:4b-instruct로 사전 동결된 초기 ID × 후속 ID 4×4 연속 참조 진단과 기존 D 종단 대조를 실행합니다. 실제 경로 길이에 따라 동결 계획의 최대 횟수 내에서 추론합니다. 모델 다운로드·갱신·서버 시작은 하지 않습니다.',flush=True)
        step(['run089.py','execute','--plan',str(plan),'--baseline',str(baseline),'--out',str(out),'--endpoint',endpoint])
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
            print(json.dumps(inspect(choose_repo(a.repo_root)/'llm_experiments/v089'),ensure_ascii=False,indent=2));return 0
        workflow(ROOT,a.repo_root,a.baseline,a.check_only,a.all_tests,a.run_name,a.endpoint,a.synthetic,a.no_open);return 0
    except (OSError,ValueError,LaunchError,KeyboardInterrupt) as e:
        print('\n자동화 중단: '+str(e),file=sys.stderr);print('원문·기존 결과를 보존했습니다. 모델 재요청/자동 새 실행/서버 시작/모델 갱신은 하지 않았습니다.',file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
