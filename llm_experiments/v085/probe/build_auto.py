"""배포 ZIP과 동일한 바이트를 내장하는 단일 PowerShell 실행 파일을 만든다."""
import argparse,base64,textwrap
from pathlib import Path
import core085 as common
import build_release

def build(source_zip,out):
    build_release.check(source_zip)
    raw=source_zip.read_bytes();template=(common.ROOT/'windows/Auto.template.ps1').read_text(encoding='utf-8-sig')
    if template.count('__PAYLOAD__')!=1 or template.count('__SHA256__')!=1:raise ValueError('auto template placeholders')
    text=template.replace('__PAYLOAD__','\n'.join(textwrap.wrap(base64.b64encode(raw).decode(),120))).replace('__SHA256__',common.sha(raw))
    common.write(out,text.encode('utf-8-sig'))
    return {'auto':str(out.resolve()),'source_sha256':common.sha(raw),'auto_sha256':common.sha(out.read_bytes())}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-zip',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();print(build(a.source_zip,a.out))
