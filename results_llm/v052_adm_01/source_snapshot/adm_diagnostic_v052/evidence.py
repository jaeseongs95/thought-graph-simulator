"""v051 재감사 수입 및 v052 증거 배포. 첨부 소스를 실행하지 않는다. 기준선 모델 성공률을 수입 게이트로 쓰지 않는다."""
from __future__ import annotations
import copy,tempfile,zipfile
from pathlib import Path
from paired_probe_v049.evidence import safe_unpack, MAX_ARCHIVE_BYTES
from .contracts import *

def import_v051(bundle):
    from adm_pilot_v051.audit import audit_run
    require(bundle.is_file() and bundle.stat().st_size<=MAX_ARCHIVE_BYTES,'v051 증거 ZIP 없음/크기 초과')
    raw=bundle.read_bytes()
    with tempfile.TemporaryDirectory(prefix='v051_import_') as td:
        root=Path(td);m=safe_unpack(raw,root)
        require(m.get('contract')=='v051-evidence-bundle-r1','v051 증거 bundle 필요')
        pp=root/'external_plan/v051.plan.json';rr=root/'run'
        report=audit_run(pp,rr,write_report=False)
        require(report['data_integrity'] and report['data_complete'] and report['comparative_analysis_ready'],'완료·비교 가능한 기준선 필요. 모델 점수는 수입 조건 아님')
        require(m.get('data_complete') is True and m.get('plan_sha256')==report['plan_sha256'],'bundle 계약 불일치')
        require(all(sha((root/n).read_bytes())==h for n,h in m['file_hashes'].items()),'감사 중 수입 원문 변경')
        plan_raw=pp.read_bytes();old=strict_json(plan_raw)
        ref={'contract':'audited-v051-bundle-reference-r1','anchor':'bundled_external_plan',
             'bundle_sha256':sha(raw),'source_bundle_name':bundle.name,'audited_at':utc_now(),
             'plan_b64':b64(plan_raw),'plan_bytes_sha256':sha(plan_raw),'plan_sha256':old['plan_sha256'],
             'event_tip':report['event_tip'],'recorded_calls':report['inference_calls'],
             'evidence_kind':report['evidence_kind'],
             'note':'원문·외부계획 재감사 영수증. 외부 전자서명 아님. 점수 선택 금지'}
        ref['receipt_sha256']=digest(ref)
        require(sha(bundle.read_bytes())==sha(raw),'수입 중 원본 ZIP 변경')
        return copy.deepcopy(old['baseline']),ref

def bundle_run(plan_path,run,out):
    from .audit import audit_run
    require(not out.exists(),'기존 ZIP 덮어쓰기 금지')
    require(not out.resolve().is_relative_to(run.resolve()),'ZIP은 결과 폴더 밖에 저장하세요')
    audit_run(plan_path,run,write_report=True)
    require(not any(p.is_symlink() for p in run.rglob('*')),'링크 포함 결과 거부')
    files={'run/'+p.relative_to(run).as_posix():p.read_bytes() for p in sorted(run.rglob('*')) if p.is_file()}
    files['external_plan/v052.plan.json']=plan_path.read_bytes()
    with tempfile.TemporaryDirectory(prefix='v052_bundle_') as td:
        root=Path(td)
        for n,b in files.items():
            p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
        report=audit_run(root/'external_plan/v052.plan.json',root/'run',write_report=True)
        files={p.relative_to(root).as_posix():p.read_bytes() for p in sorted(root.rglob('*')) if p.is_file()}
        out.parent.mkdir(parents=True,exist_ok=True);created=False
        try:
            with out.open('xb') as f:
                created=True
                with zipfile.ZipFile(f,'w',compression=zipfile.ZIP_DEFLATED) as z:
                    for n,b in files.items():z.writestr(n,b)
                    z.writestr('BUNDLE_MANIFEST.json',wire({'contract':'v052-evidence-bundle-r1',
                        'plan_sha256':report['plan_sha256'],'data_complete':report['data_complete'],
                        'file_hashes':{n:sha(b) for n,b in files.items()},'note':'외부 실행 전자서명 아님. 동봉 계획·원문 일관성 검사'}))
        except BaseException:
            if created:out.unlink(missing_ok=True)
            raise
    return report
