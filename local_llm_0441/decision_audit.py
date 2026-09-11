"""v043 결과를 읽기 전용으로 재검사한다. 원본 실패를 바꾸지 않으며 네트워크를 쓰지 않는다."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .common import ContractError, load_core, require, write_json
from .decision_source import load_decision_source
from .decision_table import summarize_records, summary_markdown


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        source=args.input.resolve();out=args.out.resolve()
        require(source!=out and not out.is_relative_to(source) and not source.is_relative_to(out),'원본과 별도의 결과 폴더가 필요합니다.')
        require(not out.exists() or (out.is_dir() and not any(out.iterdir())),'비어 있지 않은 결과 폴더입니다.')
        core,info=load_core();data=load_decision_source(core,info,source)
        tables=summarize_records(data['manifest']['frozen']['plan'],data['records'])
        write_json(out/'decision_tables.json',tables)
        write_json(out/'validation.json',data['validation'])
        write_json(out/'core_compatibility.json',data['core_compatibility'])
        (out/'summary.md').write_text('# v043 원문 재검사\n'+summary_markdown(tables),encoding='utf-8')
        print(json.dumps({'model_called':False,'validation':data['validation'],
                         'core_compatibility':data['core_compatibility'],
                         'groups':{k:{f:v[f] for f in ('recorded','correct_full_rows','false_acceptance_count','all_four_rows_match_ignore_b_shortcut')}
                                   for k,v in tables.items()},'out':str(out)},ensure_ascii=False,indent=2));return 0
    except (ContractError,OSError,KeyError,TypeError,ValueError) as exc:
        print('오류: '+str(exc),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
