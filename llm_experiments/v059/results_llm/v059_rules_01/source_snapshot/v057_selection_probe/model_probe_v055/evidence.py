"""성공 점수로 기준선을 고르지 않는다. 동봉 source snapshot은 실행하지 않는다."""
from __future__ import annotations
import copy, tempfile, zipfile
from pathlib import Path
from paired_probe_v049.evidence import safe_unpack, MAX_ARCHIVE_BYTES
from .contracts import *

def import_v054(bundle):
    from order_probe_v054.audit import audit_run
    require(bundle.is_file() and not bundle.is_symlink() and bundle.stat().st_size<=MAX_ARCHIVE_BYTES,'v054 증거 ZIP 없음/크기 초과/링크')
    raw=bundle.read_bytes()
    with tempfile.TemporaryDirectory(prefix='v054_import_') as td:
        root=Path(td);manifest=safe_unpack(raw,root)
        require(manifest.get('contract')=='v054-evidence-bundle-r1','v054 증거 계약 필요')
        pp=root/'external_plan/v054.plan.json';run=root/'run'
        report=audit_run(pp,run,write_report=False)
        require(report['data_integrity'] and report['data_complete'] and report['comparative_analysis_ready'],'완료된 무결한 기준선 필요. 모델 성공 여부는 수입 조건 아님')
        require(report==read_json(run/'summary.json'),'저장 summary/원문 재계산 불일치')
        require(manifest['plan_sha256']==report['plan_sha256'] and manifest['data_complete'] is True,'bundle 상태/계획 불일치')
        plan_raw=pp.read_bytes();previous=strict_json(plan_raw)
        bank={s['id']:b64((run/'calls'/s['id']/'request.wire.json').read_bytes()) for s in previous['slots']}
        reference={'contract':'audited-v054-reference-r1','bundle_sha256':sha(raw),'plan_b64':b64(plan_raw),
            'plan_bytes_sha256':sha(plan_raw),'plan_sha256':previous['plan_sha256'],'event_tip':report['event_tip'],
            'recorded_calls':report['inference_calls'],'evidence_kind':report['evidence_kind'],'request_bank':bank,
            'request_bank_sha256':digest(bank),'note':'완료/무결성 수입. 성공률 필터 없음. 외부 실행 전자서명 아님'}
        reference['receipt_sha256']=digest(reference)
        require(all(sha((root/n).read_bytes())==h for n,h in manifest['file_hashes'].items()),'수입 중 원문 변경')
        require(sha(bundle.read_bytes())==sha(raw),'수입 중 ZIP 변경')
        return copy.deepcopy(previous['baseline']),reference

def bundle_run(plan_path,run,out):
    from .audit import audit_run
    require(not out.exists(),'기존 ZIP 덮어쓰기 금지')
    require(not out.resolve().is_relative_to(run.resolve()),'ZIP은 결과 폴더 밖에 저장')
    audit_run(plan_path,run,write_report=True)
    require(not any(p.is_symlink() for p in run.rglob('*')),'결과에 링크 포함')
    files={'run/'+p.relative_to(run).as_posix():p.read_bytes() for p in sorted(run.rglob('*')) if p.is_file()}
    files['external_plan/v055.plan.json']=plan_path.read_bytes()
    with tempfile.TemporaryDirectory(prefix='v055_bundle_') as td:
        root=Path(td)
        for name,raw in files.items():
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        report=audit_run(root/'external_plan/v055.plan.json',root/'run',write_report=True)
        files={p.relative_to(root).as_posix():p.read_bytes() for p in sorted(root.rglob('*')) if p.is_file()}
        out.parent.mkdir(parents=True,exist_ok=True);created=False
        try:
            with out.open('xb') as handle:
                created=True
                with zipfile.ZipFile(handle,'w',compression=zipfile.ZIP_DEFLATED) as z:
                    for name,raw in files.items():z.writestr(name,raw)
                    z.writestr('BUNDLE_MANIFEST.json',wire({'contract':'v055-evidence-bundle-r1',
                        'plan_sha256':report['plan_sha256'],'data_complete':report['data_complete'],
                        'file_hashes':{name:sha(raw) for name,raw in files.items()},'note':'동봉 증거 일관성 검사. 전자서명 아님'}))
        except BaseException:
            if created:out.unlink(missing_ok=True)
            raise
    return report
