"""고정 소스 ZIP과 내장 PowerShell 생성. 모델·네트워크·이전 실행은 변경하지 않는다."""
from pathlib import Path
import argparse,base64,json
import core090 as c

def build(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    prefix='llm_experiments/v090/probe/'
    files={prefix+n:b for n,b in c.sources().items()}
    manifest=dict(contract='v090-source-release-r1',file_hashes={n:c.sha(b)for n,b in sorted(files.items())})
    files['RELEASE_MANIFEST.json']=c.wire(manifest)
    raw=c.zip_bytes(files);zip_path=out/'v090_fresh_semantic_id_source.zip';c.write(zip_path,raw)
    template=(c.ROOT/'windows/Auto.template.ps1').read_text(encoding='utf-8-sig')
    if template.count('__SHA256__')!=1 or template.count('__PAYLOAD__')!=1:raise ValueError('자동화 템플릿 placeholder')
    encoded=base64.b64encode(raw).decode('ascii')
    template=template.replace('__SHA256__',c.sha(raw)).replace('__PAYLOAD__','\n'.join(encoded[i:i+120]for i in range(0,len(encoded),120)))
    ps=out/'Run-v090-Auto.ps1';c.write(ps,template.encode('utf-8-sig'))
    return dict(source_zip=str(zip_path),source_sha256=c.sha(raw),powershell=str(ps),powershell_sha256=c.sha(ps.read_bytes()),source_files=len(files)-1)

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args();print(json.dumps(build(a.out),ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
