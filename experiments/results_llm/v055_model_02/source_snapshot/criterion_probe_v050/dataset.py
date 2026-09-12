"""원래 criterion_witness의 네 경우. 정답/진리표는 이 입력 데이터에 포함하지 않는다.

local_llm/calibration_v4.py와 micro_probe.py에서 정의된 K01/K11 단독 사실 주장을
재구성했다. 모델이 규칙으로 새 증명을 만드는 과제가 아니며 probe.parents=[]이다.
"""
from __future__ import annotations
import copy

SOURCE={
    'repository':'jaeseongs95/thought-graph-simulator',
    'task_file':'local_llm/micro_probe.py',
    'fixtures_file':'local_llm/calibration_v4.py',
    'fixtures_blob_sha':'4642be7c29aeaaec2f424c05203a9f3e4b703e5c',
    'scope':'기존 criterion_witness 의미 재통합. v042 당시 HTTP 바이트 재실행은 아님',
}
# 원래 Random(503)의 규칙 순서를 고정 리터럴로 보존한다.
P0={'id':'K01','facts':['Ca'],'rules':[
    {'id':'k10','premises':['Ca'],'conclusion':'Cb'},
    {'id':'k17','premises':['Cb'],'conclusion':'Cc'},
    {'id':'k03','premises':['Ca'],'conclusion':'Cc'}], 'goal':'Cc'}
# 규칙 배열 순서는 판단 정답에 영향을 주지 않지만 실행 도중 바꾸지 않는다.

def cases():
    rows=[]
    for i,(atom,given) in enumerate((('Cz',False),('Ca',False),('Cc',False),('Cc',True)),1):
        p=copy.deepcopy(P0)
        if given:p['id']='K11';p['facts'].append('Cc')
        rows.append({'id':f'case{i:02d}','problem':p,'probe':{'atom':atom,'rule':None,'parents':[]}})
    return rows
