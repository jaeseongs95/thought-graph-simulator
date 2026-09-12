"""ZIP 원문 검사/수입. 첨부된 소스는 실행하지 않으며 배포한 고정 감사기를 사용한다."""
from __future__ import annotations
import copy
import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from .contracts import b64, digest, read_json, require, sha, strict_json, utc_now, wire

MAX_ARCHIVE_BYTES = 100*1024*1024
MAX_TOTAL_BYTES = 150*1024*1024
MAX_FILES = 12000

def safe_unpack(raw: bytes, root: Path) -> dict:
    import io
    require(len(raw)<=MAX_ARCHIVE_BYTES,"ZIP 파일 크기 한도 초과")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos=z.infolist()
        require(0<len(infos)<=MAX_FILES and sum(x.file_size for x in infos)<=MAX_TOTAL_BYTES,"ZIP 파일 수/해제 크기 한도 초과")
        seen=set()
        for x in infos:
            n=x.filename; p=PurePosixPath(n)
            require(not x.is_dir() and '\\' not in n and ':' not in n and not p.is_absolute()
                    and all(part not in ('..','.') for part in p.parts) and p.as_posix()==n,"비정규 ZIP 경로")
            require(n.casefold() not in seen,"중복/대소문자 충돌 ZIP 경로")
            seen.add(n.casefold())
            reserved = {"CON","PRN","AUX","NUL","CLOCK$","CONIN$","CONOUT$"} | {f"{prefix}{i}" for prefix in ("COM","LPT") for i in range(1,10)}
            require(all(part and not part.endswith((" ",".")) and
                        not any(ord(c)<32 or c in '<>"|?*' for c in part) and
                        part.split(".")[0].upper() not in reserved for part in p.parts),
                    "Windows에서 안전하지 않은 ZIP 파일명")
            require(((x.external_attr>>16)&0o170000)!=0o120000 and not(x.flag_bits&1),"링크/암호화 ZIP 금지")
            require(x.file_size<=8*1024*1024,"개별 파일 크기 한도 초과")
        require('BUNDLE_MANIFEST.json' in z.namelist(),"BUNDLE_MANIFEST.json 없음")
        manifest=strict_json(z.read('BUNDLE_MANIFEST.json'))
        hashes=manifest.get('file_hashes')
        require(isinstance(hashes,dict) and set(hashes)==set(z.namelist())-{'BUNDLE_MANIFEST.json'},"ZIP manifest의 파일 목록 불일치")
        for x in infos:
            content=z.read(x.filename)
            if x.filename!='BUNDLE_MANIFEST.json':require(sha(content)==hashes[x.filename],"ZIP manifest 해시 불일치: "+x.filename)
            dest=root/x.filename
            require(dest.resolve().is_relative_to(root.resolve()),"ZIP 경로 이탈")
            dest.parent.mkdir(parents=True,exist_ok=True)
            with dest.open('xb') as f:f.write(content)
        return manifest

def import_v048(bundle: Path) -> tuple[dict,dict]:
    from paired_probe_v048.audit import audit_run
    require(bundle.is_file(),"v048 증거 ZIP이 없습니다: "+str(bundle))
    require(bundle.stat().st_size<=MAX_ARCHIVE_BYTES,"ZIP 파일 크기 한도 초과")
    raw=bundle.read_bytes()
    with tempfile.TemporaryDirectory(prefix='v049_baseline_') as td:
        root=Path(td); manifest=safe_unpack(raw,root)
        require(manifest.get('contract')=='v048-evidence-bundle-r1',"v048 증거 ZIP 계약이 아닙니다.")
        pp=root/'external_plan/v048.plan.json'; run=root/'run'
        report=audit_run(pp,run,write_report=False)
        require(report['data_integrity'] and report['data_complete'] and report['comparative_analysis_ready'],"완료·비교 가능한 v048 원문 필요. 정답률은 수입 조건이 아닙니다.")
        require(manifest.get('data_complete') is True and manifest.get('plan_sha256')==report['plan_sha256'],"bundle 상태/계획 해시 불일치")
        # 감사 중 바이트 변경도 검사한다. 파생 summary조차 원본 그대로 보존한다.
        require(all(sha((root/n).read_bytes())==h for n,h in manifest['file_hashes'].items()),"기준선 감사 중 원문 변경")
        plan_raw=pp.read_bytes(); old=strict_json(plan_raw)
        ref={'contract':'audited-v048-bundle-reference-r1','anchor':'bundled_external_plan',
             'source_bundle_name':bundle.name,'bundle_sha256':sha(raw),'audited_at':utc_now(),
             'plan_b64':b64(plan_raw),'plan_bytes_sha256':sha(plan_raw),'plan_sha256':old['plan_sha256'],
             'event_tip':report['event_tip'],'recorded_calls':report['inference_calls'],
             'evidence_kind':report['evidence_kind'],'reference_only_scores':{
                arm:{k:report['arms'][arm][k] for k in ('assigned','final_correct','positive_correct','strict_trace_correct')}
                for arm in ('original','commuted','pipeline')},
             'note':'v048 원문은 prepare 시 재감사. 이 receipt는 외부 실행의 전자서명이 아니며 v048 점수와 v049 점수는 합산하지 않음'}
        ref['receipt_sha256']=digest(ref)
        require(sha(bundle.read_bytes())==sha(raw),"수입 중 원본 ZIP 변경")
        return copy.deepcopy(old['baseline']),ref

def bundle_run(plan_path: Path, run: Path, out: Path) -> dict:
    from .audit import audit_run
    require(not out.exists(),"기존 ZIP은 덮어쓰지 않습니다.")
    require(not out.resolve().is_relative_to(run.resolve()),"ZIP은 결과 폴더 밖에 저장하세요.")
    report=audit_run(plan_path,run,write_report=True)
    require(all(not p.is_symlink() for p in run.rglob('*')),"심볼릭 링크가 포함된 결과는 묶지 않습니다.")
    # 외부 계획과 수집한 바이트를 임시 폴더에 고정한 후 그 복사본을 다시 감사한다.
    # 원본 감사 뒤 파일이 바뀌는 경우에도 실제 배포 ZIP은 재감사를 통과한 바이트만 담는다.
    files={"run/"+p.relative_to(run).as_posix():p.read_bytes() for p in sorted(run.rglob('*')) if p.is_file()}
    files['external_plan/v049.plan.json']=plan_path.read_bytes()
    with tempfile.TemporaryDirectory(prefix='v049_bundle_') as td:
        frozen=Path(td)
        for name,data in files.items():
            path=frozen/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        report=audit_run(frozen/'external_plan/v049.plan.json',frozen/'run',write_report=True)
        files={p.relative_to(frozen).as_posix():p.read_bytes() for p in sorted(frozen.rglob('*')) if p.is_file()}
        inventory={n:sha(b) for n,b in files.items()}
        out.parent.mkdir(parents=True,exist_ok=True)
        # 배타 생성: 기존 증거를 덮어쓰지 않는다. 실패한 ZIP은 현재 시도에서만 제거한다.
        created=False
        try:
            with out.open('xb') as output:
                created=True
                with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as z:
                    for name,data in files.items():z.writestr(name,data)
                    z.writestr('BUNDLE_MANIFEST.json',wire({'contract':'v049-evidence-bundle-r1',
                        'plan_sha256':report['plan_sha256'],'data_complete':report['data_complete'],
                        'file_hashes':inventory,'note':'원문/동봉 외부 계획 일관성. 외부 전자서명 아님'}))
        except BaseException:
            if created:out.unlink(missing_ok=True)
            raise
    return report
