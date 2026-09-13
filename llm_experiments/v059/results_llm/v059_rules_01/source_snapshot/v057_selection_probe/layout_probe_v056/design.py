"""두 모델×두 메시지 배치×두 문제×두 규칙순서×세 방향×10 seed, 총 480회."""
from copy import deepcopy
from order_probe_v054.design import PROBLEMS,ARMS,DIRECTIONS,RULE_ORDERS
from .contracts import require,canonical
MODELS=('reference','candidate')
LAYOUTS=('split','merged')
MAX_CALLS=480
POLICY={
    'question':'지시문과 문제를 한 사용자 메시지로 합치면 증명 유효성과 선택적 D 제어가 달라지는가',
    'intervention':'split은 실제 v055 요청 원문과 동일. merged는 system 내용 + 줄바꿈 두 개 + user 내용을 하나의 user 메시지로 연결',
    'fixed':'모델 가중치/digest/template, 샘플링 옵션, seed, 문제, 규칙순서, 원 지시문 내용, 출력 schema, 채점 보존',
    'scope':'역할과 턴 경계를 함께 바꾸는 배치 묶음의 효과. system 권한/토큰 위치/분리자의 효과를 개별 분해하지 않음',
    'schedule':'각 seed 두 모델의 24회 블록. 모델 선후 5:5. 블록 안 각 조건의 split/merged 선후 6:6',
    'primary':'각 모델·배치·문제·규칙순서·seed에서 shallow/deep 둘 다 유효하고 각각 최소/최대 깊이여야 선택적 성공',
    'neutral':'배치별 중립 생성 포함. 기존 응답 재집계를 새 독립 표본으로 합산하지 않음',
    'budget':'480회: 방향지정 320 + 중립 160. metadata 40회(각 3 HTTP 요청)는 추론 수에 포함하지 않음. warmup 0',
    'historical':'v055 전체 무결성·완료를 검사하되 모델 정답률로 기준선을 선택하지 않음. 원 ZIP을 별도 파일로 한 번 보존',
    'interpretation':'Gemma 무효 증명과 Qwen 비선택적 유효 증명을 같은 원인으로 합치지 않음. 학습된 정책/내부 우선순위 직접 계측 아님',
    'incomplete':'미실행은 미관측. 전체 비교율 null. 구조 오류와 파싱 미측정은 분리',
    'retry':False,'repair':False,'host_answer_fill':False,'download_models':False,
}

def schedule(reference):
    result=[]
    for i,seed in enumerate(reference['seeds']):
        cells=sorted((s for s in reference['slots'] if s['seed']==seed and s['model_key']=='reference'),key=lambda s:s['reference_slot_id'])
        require(len(cells)==12,'기준선 seed당 12조건 필요')
        model_order=MODELS if i%2==0 else MODELS[::-1]
        for j,key in enumerate(model_order):
            for n,cell in enumerate(cells):
                layouts=LAYOUTS if (i+n)%2==0 else LAYOUTS[::-1]
                old_id=key+'__'+cell['reference_slot_id']
                for layout in layouts:
                    result.append({**cell,'id':layout+'__'+old_id,'reference_slot_id':old_id,'model_key':key,
                        'layout':layout,'task':'layout_probe','block':2*i+j,'seed_index':i,'position':len(result)})
    return result

def actions(slots):
    result=[]
    for block in range(20):
        cells=[s for s in slots if s['block']==block];require(len(cells)==24,'모델 블록은 24회')
        result.append({'kind':'metadata','id':f'b{block:02d}.before','block':block,'model_key':cells[0]['model_key']})
        result.extend({'kind':'call','id':s['id'],'slot':s} for s in cells)
        result.append({'kind':'metadata','id':f'b{block:02d}.after','block':block,'model_key':cells[0]['model_key']})
    for i,a in enumerate(result):a['index']=i
    return result
