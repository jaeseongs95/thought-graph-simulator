"""설치 재사용은 manifest 이름이 아니라 실제 파일 목록/바이트를 검사한다."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path,PurePosixPath

IGNORED={'__pycache__'}
def verify_package(root:Path):
    root=root.resolve();manifest=root/'PACKAGE_MANIFEST.json'
    data=json.loads(manifest.read_text(encoding='utf-8-sig'))
    if data.get('contract')!='v057-source-package-r1' or not isinstance(data.get('file_hashes'),dict):raise ValueError('잘못된 소스 manifest')
    expected=data['file_hashes'];actual=set()
    for path in root.rglob('*'):
        if path.is_symlink():raise ValueError('소스 symlink 거부: '+str(path))
        if path.is_file() and not any(p in IGNORED for p in path.relative_to(root).parts):actual.add(path.relative_to(root).as_posix())
    if actual!=set(expected)|{'PACKAGE_MANIFEST.json'}:raise ValueError('소스 파일 목록 불일치: '+str(sorted(actual^(set(expected)|{'PACKAGE_MANIFEST.json'}))))
    for name,digest in expected.items():
        pp=PurePosixPath(name)
        if pp.is_absolute() or '..' in pp.parts or '\\' in name or not(root/name).resolve().is_relative_to(root):raise ValueError('manifest 경로 이탈')
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('소스 해시 불일치: '+name)
    return data
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('root',type=Path,nargs='?',default=Path(__file__).resolve().parents[1]);a=ap.parse_args();m=verify_package(a.root);print('소스 무결성 확인:',len(m['file_hashes']),'files')
