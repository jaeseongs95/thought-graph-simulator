"""저장된 Modelfile의 FROM blob과 로컬 GGUF 바이트를 비교. 모델 실행·다운로드·네트워크 없음.
메타데이터 digest와 가중치 blob SHA-256은 서로 다르다. 이 검사는 손상 여부이지 성능 검사/공식 서명 인증이 아니다.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path
from .common import ContractError, require, read_json, write_json


def recorded_blob(manifest: dict) -> tuple[str,str]:
    text=manifest['ollama_metadata']['show']['modelfile']
    match=re.search(r'^FROM\s+(.+?)\s*$',text,re.MULTILINE)
    require(match is not None,'기록된 Modelfile에 FROM이 없습니다.')
    name=match.group(1).strip().strip('"')
    digest_match=re.search(r'(?:^|[\\/])sha256-([a-f0-9]{64})$',name)
    require(digest_match is not None,'FROM에 가중치 blob 해시 경로가 없습니다. 태그 digest를 가중치 해시로 사용하지 않습니다.')
    require(not name.startswith(('\\\\','//')),'네트워크 공유 경로는 읽지 않습니다.')
    return name,digest_match.group(1)


def inspect_file(path: Path, expected_sha256: str) -> dict:
    require(re.fullmatch('[a-f0-9]{64}',expected_sha256) is not None,'기대 SHA256 형식 오류')
    require(path.is_file(),'로컬 가중치 파일이 없습니다: '+str(path))
    before=path.stat();h=hashlib.sha256();count=0;header=b''
    with path.open('rb') as f:
        while True:
            chunk=f.read(8*1024*1024)
            if not chunk:break
            if not header:header=chunk[:8]
            h.update(chunk);count+=len(chunk)
    after=path.stat();stable=(before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns) and count==after.st_size
    magic=header[:4]==b'GGUF';version=struct.unpack('<I',header[4:8])[0] if len(header)==8 else None
    actual=h.hexdigest()
    return {'weights_path':str(path),'bytes_read':count,'expected_blob_sha256':expected_sha256,
            'actual_blob_sha256':actual,'sha256_matches':actual==expected_sha256,
            'gguf_magic':magic,'gguf_version':version,'file_stable_during_read':stable,
            'passed':actual==expected_sha256 and magic and stable,
            'model_called':False,'network_called':False,
            'scope':'저장된 blob 이름과 로컬 바이트의 일치. 공식 가중치 인증/양자화 품질/추론 커널/정답률은 검사하지 않음.'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--check-weights',action='store_true');p.add_argument('--weights',type=Path);p.add_argument('--out',type=Path)
    args=p.parse_args(argv)
    try:
        manifest=read_json(args.input/'manifest.json');path,expected=recorded_blob(manifest)
        if args.check_weights:
            require(args.out is not None,'--check-weights에는 새 --out JSON 파일이 필요합니다.')
            out=args.out.resolve();source=args.input.resolve()
            require(out!=source and not out.is_relative_to(source),'원본 폴더에 결과를 쓰지 않습니다.')
            require(not out.exists(),'기존 결과 파일을 덮어쓰지 않습니다.')
            weights=args.weights or Path(path)
            require(not str(weights).startswith(('\\\\','//')),'네트워크 공유 경로는 읽지 않습니다.')
            result=inspect_file(weights,expected);write_json(out,result)
        else:
            result={'model_called':False,'network_called':False,'weights_read':False,
                    'recorded_path':path,'expected_blob_sha256':expected,
                    'manifest_digest_not_weight_digest':manifest['frozen']['model']['digest'],
                    'note':'실제 바이트 검사는 --check-weights --out 새파일.json으로 명시 실행합니다.'}
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result.get('passed',True) else 1
    except (ContractError,OSError,KeyError,TypeError,ValueError) as exc:
        print('오류: '+str(exc),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
