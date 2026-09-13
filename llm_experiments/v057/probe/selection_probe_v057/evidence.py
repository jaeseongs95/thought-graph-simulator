"""기준선 ZIP은 중첩 JSON으로 증식시키지 않고 독립 바이트 파일로 보존한다."""
from __future__ import annotations
import copy,io,tempfile,zipfile
from pathlib import Path,PurePosixPath
from .contracts import *
MAX_ARCHIVE_BYTES=100*1024*1024
MAX_TOTAL_BYTES=256*1024*1024


def safe_unpack(raw,root):
    require(len(raw)<=MAX_ARCHIVE_BYTES,'ZIP 파일 100 MiB 한도 초과')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos=z.infolist();require(0<len(infos)<=12000 and sum(i.file_size for i in infos)<=MAX_TOTAL_BYTES,'ZIP 파일수/해제 크기 초과')
        seen=set();reserved={'CON','PRN','AUX','NUL','CLOCK$','CONIN$','CONOUT$'}|{p+str(i) for p in ('COM','LPT') for i in range(1,10)}
        for i in infos:
            n=i.filename;p=PurePosixPath(n)
            require(not i.is_dir() and '\\' not in n and ':' not in n and not p.is_absolute() and p.as_posix()==n and all(x not in ('.','..') for x in p.parts),'비정규 ZIP 경로')
            require(n.casefold() not in seen,'ZIP 중복/대소문자 충돌');seen.add(n.casefold())
            require(all(x and not x.endswith((' ','.')) and not any(ord(c)<32 or c in '<>"|?*' for c in x) and x.split('.')[0].upper() not in reserved for x in p.parts),'Windows 비안전 파일명')
            require(((i.external_attr>>16)&0o170000)!=0o120000 and not(i.flag_bits&1),'링크/암호화 ZIP 거부')
            limit=8*1024*1024
            if n in ('external_plan/v056.plan.json','external_plan/v057.plan.json','run/plan.snapshot.json'):limit=32*1024*1024
            if n in ('run/baseline/v055_evidence.zip','run/baseline/v056_evidence.zip'):limit=MAX_ARCHIVE_BYTES
            require(i.file_size<=limit,'개별 파일 크기 한도 초과: '+n)
        require('BUNDLE_MANIFEST.json' in z.namelist(),'증거 manifest 없음')
        m=strict_json(z.read('BUNDLE_MANIFEST.json'));hs=m.get('file_hashes')
        require(isinstance(hs,dict) and set(hs)==set(z.namelist())-{'BUNDLE_MANIFEST.json'},'manifest 파일 목록 불일치')
        for i in infos:
            b=z.read(i.filename)
            if i.filename!='BUNDLE_MANIFEST.json':require(sha(b)==hs[i.filename],'manifest 해시: '+i.filename)
            dest=root/i.filename;require(dest.resolve().is_relative_to(root.resolve()),'압축 경로 이탈')
            dest.parent.mkdir(parents=True,exist_ok=True)
            with dest.open('xb') as f:f.write(b)
    return m


def import_v056(bundle):
    """동결 배포 코드로 이전 증거를 감사한다. 첨부 snapshot은 실행하지 않는다."""
    from layout_probe_v056.audit import audit_run
    require(bundle.is_file() and not bundle.is_symlink() and bundle.stat().st_size<=MAX_ARCHIVE_BYTES,'v056 기준선 ZIP 없음/링크/크기 초과')
    raw=bundle.read_bytes()
    with tempfile.TemporaryDirectory(prefix='v057_import_') as td:
        root=Path(td);m=safe_unpack(raw,root);require(m.get('contract')=='v056-evidence-bundle-r1','v056 증거 계약 필요')
        pp=root/'external_plan/v056.plan.json';run=root/'run';report=audit_run(pp,run,write_report=False)
        require(report['data_integrity'] and report['data_complete'] and report['comparative_analysis_ready'],'무결한 완료 기준선 필요. 성공률 필터 없음')
        require(report==read_json(run/'summary.json'),'기준선 summary와 원문 재계산 불일치')
        p=read_plan_json(pp);require(m['plan_sha256']==p['plan_sha256'] and m['data_complete'] is True,'기준선 manifest 상태')
        ref={'contract':'audited-v056-compact-r1','bundle_sha256':sha(raw),'plan_sha256':p['plan_sha256'],
            'event_tip':report['event_tip'],'recorded_calls':480,'selected_calls':240,'selected_layout':'merged','evidence_kind':report['evidence_kind'],
            'config':copy.deepcopy(p['baseline']['config']),'identities':copy.deepcopy(p['identities']),
            'seeds':p['seeds'],'slots':[s for s in p['slots'] if s['layout']=='merged'],
            'request_bank':{s['id']:b64((run/'calls'/s['id']/'request.wire.json').read_bytes()) for s in p['slots'] if s['layout']=='merged'}}
        ref['receipt_sha256']=digest(ref)
        require(all(sha((root/n).read_bytes())==h for n,h in m['file_hashes'].items()),'기준선 수입 중 바이트 변경')
    require(sha(bundle.read_bytes())==sha(raw),'기준선 ZIP 수입 중 변경')
    return ref


def validate_reference_file(bundle,plan):
    require(bundle.is_file() and not bundle.is_symlink(),'동결 기준선 ZIP 없음/링크 거부')
    require(bundle.stat().st_size<=MAX_ARCHIVE_BYTES,'기준선 ZIP 크기 초과')
    require(sha(bundle.read_bytes())==plan['reference']['bundle_sha256'],'동결 기준선 ZIP 해시 불일치')
    ref=import_v056(bundle)
    require(canonical(ref)==canonical(plan['reference']),'원 기준선과 계획의 요청/모델/seed 영수증 불일치')
    return ref


def bundle_run(plan_path,run,out):
    from .audit import audit_run
    require(not out.exists(),'기존 ZIP 보존');require(not out.resolve().is_relative_to(run.resolve()),'ZIP은 결과 폴더 밖에 저장')
    audit_run(plan_path,run,write_report=True)
    require(not any(p.is_symlink() for p in run.rglob('*')),'결과에 링크 포함')
    files={'run/'+p.relative_to(run).as_posix():p.read_bytes() for p in sorted(run.rglob('*')) if p.is_file()}
    files['external_plan/v057.plan.json']=plan_path.read_bytes()
    with tempfile.TemporaryDirectory(prefix='v057_bundle_') as td:
        root=Path(td)
        for n,b in files.items():
            dest=root/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b)
        report=audit_run(root/'external_plan/v057.plan.json',root/'run',write_report=True)
        files={p.relative_to(root).as_posix():p.read_bytes() for p in sorted(root.rglob('*')) if p.is_file()}
        out.parent.mkdir(parents=True,exist_ok=True);created=False
        try:
            with out.open('xb') as handle:
                created=True
                with zipfile.ZipFile(handle,'w',compression=zipfile.ZIP_DEFLATED) as z:
                    for n,b in files.items():z.writestr(n,b)
                    z.writestr('BUNDLE_MANIFEST.json',wire({'contract':'v057-evidence-bundle-r1','plan_sha256':report['plan_sha256'],
                        'data_complete':report['data_complete'],'file_hashes':{n:sha(b) for n,b in files.items()},'note':'동봉 증거의 일관성 검사. 외부 실행 전자서명 아님'}))
        except BaseException:
            if created:out.unlink(missing_ok=True)
            raise
    return report
