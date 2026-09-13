"""배포 ZIP을 푼 뒤 기존 Python 코드 보존과 배포 manifest를 오프라인 확인한다."""
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path

def main():
    root=Path(__file__).resolve().parent.parent
    manifest=json.loads((root/'PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
    files=manifest['file_hashes']
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()
        and '__pycache__' not in p.parts and p.suffix!='.pyc' and p.name!='PACKAGE_MANIFEST.json'}
    if actual!=set(files):raise ValueError('배포 파일 누락/추가: '+str(sorted(actual^set(files))))
    for name,h in files.items():
        p=root/name
        if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=h:raise ValueError('배포 내용 변경: '+name)
    old=json.loads((root/'docs/PRESERVED_SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    for name,h in old.items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=h:raise ValueError('기존 Python 소스 변경: '+name)
    print(json.dumps({'release_integrity':True,'file_count':len(files),'old_python_files_preserved':len(old)},ensure_ascii=False))
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError) as e:print('배포 검사 실패: '+str(e),file=sys.stderr);raise SystemExit(2)
