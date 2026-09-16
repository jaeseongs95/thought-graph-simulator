"""독립 검산기의 바이트 처리. 실행기·생산 채점기를 import하지 않는다."""
import base64,hashlib,io,json,math,zipfile
from pathlib import PurePosixPath

def digest(b):return hashlib.sha256(b).hexdigest()
def dump(o):return json.dumps(o,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')
def load(b):
    if isinstance(b,str):b=b.encode('utf-8')
    if len(b)>8*1024**2:raise ValueError('audit JSON limit')
    def pairs(ps):
        d={}
        for k,v in ps:
            if k in d:raise ValueError('duplicate JSON key')
            d[k]=v
        return d
    def reject(x):raise ValueError('nonfinite JSON')
    def number(x):
        v=float(x)
        if not math.isfinite(v):reject(x)
        return v
    return json.loads(b.decode('utf-8'),object_pairs_hook=pairs,parse_constant=reject,parse_float=number)
def same(a,b):
    if type(a) is not type(b):return False
    if isinstance(a,dict):return a.keys()==b.keys() and all(same(a[k],b[k]) for k in a)
    if isinstance(a,list):return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
    return a==b
def need(test,message):
    if not test:raise ValueError(message)
def b64(text):
    need(isinstance(text,str),'base64 type');return base64.b64decode(text,validate=True)
def archive(raw):
    need(len(raw)<=320*1024**2,'archive compressed limit')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos=z.infolist();need(0<len(infos)<=40000 and sum(i.file_size for i in infos)<=768*1024**2,'archive expanded limit')
        seen=set();out={}
        reserved={'CON','PRN','AUX','NUL','CLOCK$','CONIN$','CONOUT$'}|{x+str(i) for x in ('COM','LPT') for i in range(1,10)}
        for i in infos:
            n=i.filename;p=PurePosixPath(n)
            need(bool(n) and not p.is_absolute() and p.as_posix()==n and '\\' not in n and not any(c in n for c in ':<>"|?*')
                 and not any(ord(c)<32 for c in n) and all(x not in ('.','..') and not x.endswith((' ','.')) and x.split('.')[0].upper() not in reserved for x in p.parts),'archive path')
            need(n.casefold() not in seen and not i.is_dir() and (i.external_attr>>16)&0o170000!=0o120000,'archive duplicate/link/dir')
            seen.add(n.casefold());out[n]=z.read(i)
        return out
