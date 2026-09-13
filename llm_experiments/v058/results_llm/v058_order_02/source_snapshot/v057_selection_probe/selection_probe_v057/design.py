"""전체 증명과 마지막 규칙 선택의 출력 과제를 비교한다. 선택 성공을 증명 성공으로 세지 않는다."""
from copy import deepcopy
from order_probe_v054.design import PROBLEMS,ARMS,DIRECTIONS,RULE_ORDERS
from .contracts import require
MODELS=('reference','candidate')
MODES=('graph','choice')
REFERENCE_LAYOUT='merged'
MAX_CALLS=480
POLICY={
 'question':'D 지시를 받았을 때 완전한 증명 DAG를 쓰지 않고 마지막 규칙 하나만 선택해도 실패하는가',
 'baseline_layout':'두 모델 모두 v056 merged로 고정. 기존 split 원문도 원 v056 ZIP 안에 보존. 모델마다 좋은 배치를 골라 섞지 않음',
 'intervention':'graph는 v056 merged 요청과 바이트 동일. choice는 동일 문제/경로지시를 유지하고 전체 DAG 작성 대신 마지막 규칙 ID 하나를 요구하는 출력 과제 묶음',
 'fixed':'두 모델의 digest/show/template, 옵션, 전체 10 seed, 두 문제, 두 규칙순서, 방향/중립 지시, 문제 facts/rules/goal 보존',
 'not_fixed':'DAG 작성 설명과 JSON schema는 choice 과제에 맞춰 변경. 출력 길이만의 순수 효과나 내부 이해/학습 원인으로 해석하지 않음',
 'no_answer_leak':'선택 후보 증명/정답 경로/정답 깊이/후보별 깊이/정답 ID enum을 주지 않음. 문자열 하나만 출력. 채점용 경로 열거는 실행 요청 생성에 참여하지 않음',
 'measurement':'graph의 D는 실제 유효 그래프에서 계산. choice의 implied_depth는 문제 명세상 선택 규칙에 대응하는 깊이이며 생성된 증명 D가 아님',
 'primary':'모델/과제/문제/순서/seed별 shallow와 deep 각각 조건에 맞아야 선택적 성공. choice 성공을 ADM 핵심 성공으로 합산하지 않음',
 'interpretation':'choice만 성공하면 축소된 선택 과제와 전체 증명 작성 사이의 격차. 실제 같은 호출 안에서 선택을 이해했다가 잊었다는 증거 아님',
 'schedule':'seed별 두 모델 24회 블록, 모델 선후 5:5, 블록 안 graph/choice 선후 6:6',
 'budget':'480회: graph 240 + choice 240. 방향 지정 320 + 중립 160. 이전 응답 재집계를 새 표본으로 합산하지 않음',
 'neutral':'방향 없는 응답도 각 과제에서 실제 생성. 한 중립 응답을 두 방향 기준으로 재평가해도 독립 응답 둘로 세지 않음',
 'incomplete':'미실행은 미관측, 전체 비교율 null. 파싱 미측정/ID 선택 오류/증명 논리 오류를 분리',
 'history':'v056 원문 전체를 재감사한 뒤 merged 240요청만 기준은행으로 가져옴. 이전 모델 성공률로 개별 seed/문제를 걸러내지 않음',
 'retry':False,'repair':False,'host_answer_fill':False,'download_models':False,
}

def schedule(reference):
    cells={(s['model_key'],s['seed'],s['problem_id'],s['arm'],s['direction']):s for s in reference['slots']}
    require(len(cells)==240,'기준선 240개 조건 중복/누락')
    result=[]
    for i,seed in enumerate(reference['seeds']):
        keys=sorted((pid,arm,d) for pid in PROBLEMS for arm in ARMS for d in DIRECTIONS)
        for j,model in enumerate(MODELS if i%2==0 else MODELS[::-1]):
            for n,(pid,arm,d) in enumerate(keys):
                old=cells[model,seed,pid,arm,d]
                for mode in MODES if (i+n)%2==0 else MODES[::-1]:
                    result.append({**old,'id':mode+'__'+old['id'],'reference_slot_id':old['id'],'mode':mode,
                        'task':'selection_probe','stage':mode,'block':2*i+j,'seed_index':i,'position':len(result)})
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
