"""보존된 v057/v058 의존성과 새 v059 소스를 바이트 그대로 묶고 검사한다."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEPENDENCY_ROOT = ROOT.parents[1] / 'v057' / 'probe'
SOURCES = (
    (DEPENDENCY_ROOT, 'llm_experiments/v057/probe'),
    (ROOT.parents[1] / 'v058' / 'probe', 'llm_experiments/v058/probe'),
    (ROOT, 'llm_experiments/v059/probe'),
)
ENTRYPOINT = 'llm_experiments/v059/probe'
DEPENDENCY = 'llm_experiments/v057/probe and v058/probe are included unchanged; no runtime download.'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build(out):
    files = {}
    for folder, archive_root in SOURCES:
        if not folder.is_dir():
            raise ValueError('필수 소스 루트 없음: '+str(folder))
        for path in sorted(folder.rglob('*')):
            if '__pycache__' in path.parts or path.suffix in ('.pyc','.pyo'):
                continue
            if path.is_symlink():
                raise ValueError('소스 링크 거부: '+str(path))
            if path.is_file():
                if path.suffix not in ('.py','.md','.json','.ps1','.cmd','.txt'):
                    raise ValueError('배포 대상 외 파일: '+str(path))
                name=archive_root+'/'+path.relative_to(folder).as_posix()
                files[name]=path.read_bytes()
    manifest={'contract':'v059-source-release-r1','file_hashes':{n:sha(b) for n,b in files.items()},
              'dependency':DEPENDENCY, 'entrypoint':ENTRYPOINT, 'new_model_inference':False}
    raw=(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8')
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('xb') as stream:
        with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for name,content in files.items(): z.writestr(name,content)
            z.writestr('RELEASE_MANIFEST.json',raw)
    check(out)
    return {'files':len(files),'sha256':sha(out.read_bytes()),'path':str(out.resolve())}


def check(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if len(names)!=len(set(n.casefold() for n in names)):
            raise ValueError('중복 배포 경로')
        for info in z.infolist():
            name=info.filename
            p=PurePosixPath(name)
            if p.is_absolute() or p.as_posix()!=name or '\\' in name or ':' in name or '..' in p.parts:
                raise ValueError('배포 경로 오류')
            if info.is_dir() or ((info.external_attr>>16)&0o170000)==0o120000:
                raise ValueError('배포 링크/디렉터리 항목')
        manifest=json.loads(z.read('RELEASE_MANIFEST.json'))
        fields={'contract','file_hashes','dependency','entrypoint','new_model_inference'}
        if (set(manifest)!=fields or manifest['contract']!='v059-source-release-r1'
                or manifest['dependency']!=DEPENDENCY or manifest['entrypoint']!=ENTRYPOINT
                or manifest['new_model_inference'] is not False
                or set(manifest['file_hashes'])!=set(names)-{'RELEASE_MANIFEST.json'}):
            raise ValueError('배포 manifest 목록 불일치')
        prefixes=tuple(root+'/' for _,root in SOURCES)
        members=set(manifest['file_hashes'])
        if (not all(name.startswith(prefixes) for name in members)
                or not all(any(name.startswith(prefix+'/') for name in members) for _,prefix in SOURCES)):
            raise ValueError('배포 소스 경로 불일치')
        for name,h in manifest['file_hashes'].items():
            if sha(z.read(name))!=h: raise ValueError('배포 해시 불일치: '+name)
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--out',type=Path)
    group.add_argument('--check',type=Path)
    a=parser.parse_args()
    if a.out:
        print(json.dumps(build(a.out),ensure_ascii=False,indent=2))
    else:
        m=check(a.check)
        print('release manifest: PASS ('+str(len(m['file_hashes']))+' files)')
