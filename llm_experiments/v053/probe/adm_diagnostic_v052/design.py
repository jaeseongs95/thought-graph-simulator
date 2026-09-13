"""실험 전 고정: 핵심 factorial, 중립 대조, 별도 복사 진단, D 단독 생성."""
import copy
from adm_pilot_v051.design import PROBLEM as K01, ROLES
from .contracts import digest
TRANSFER={'id':'T02','facts':['Lp','Ls'],'rules':[
    {'id':'r83','premises':['Lp','Ls'],'conclusion':'Lg'},
    {'id':'r21','premises':['Lp'],'conclusion':'Lq'},
    {'id':'r57','premises':['Lq','Ls'],'conclusion':'Lr'},
    {'id':'r04','premises':['Lr'],'conclusion':'Lt'},
    {'id':'r69','premises':['Lt'],'conclusion':'Lg'}],'goal':'Lg'}
PROBLEMS={'K01':copy.deepcopy(K01),'T02':TRANSFER}
CYCLES=1; ORDER_SEED=5201729; MAX_CALLS=440
TASK_COUNTS={'legacy':120,'factorial':240,'neutral':20,'copy_control':20,'graph_only':40}
POLICY={
 'hypothesis':'동일 문제·목표에서 역할 조작이 실제 유효한 A/D/M 기록을 선택적으로 바꾸는가',
 'primary':'explicit factorial 240건만 본 가설의 직접 증거. legacy는 대응 구현 대조',
 'negative_control':'neutral 20건. 같은 schema·공통 계약에서 A/D/M 지정만 제거. 12역할 재채점은 12개 새 표본이 아님',
 'calibration':'copy_control 20건은 정답 제공 형식 복사. 가설 성공 분자·분모에서 전부 제외',
 'component':'graph_only 40건은 D 단독 생성. A/M 동시 제어 성공으로 세지 않음',
 'scope':'외부 생성 기록의 조작·구조 전이. 내부 hidden state나 잠재 사고차원은 측정하지 않음',
 'A':'실제 근거에 연결된 보편 도식 vs 사례; 단순 역할 라벨을 읽지 않음',
 'D':'규칙 원자성 고정 아래 실제 목표 지지 깊이. K01=1/2, T02=1/4',
 'M':'검토 대상과 판정 진위를 별도 측정. M2가 M1을 요구하지 않음',
 'comparison':'legacy/explicit 차이는 필드명·배열 직렬화·설명 명확화의 묶음 효과. 개별 내부 원인 확정 아님',
 'transfer':'T02는 기존 simulator의 conjunction_4와 같은 구조를 이름 변경. 새로운 구조에 대한 첫 로컬 LLM 탐색, 광범위 일반화 아님',
 'failure':'모든 seed·역할 유지. 불완전 수집은 확증 판정하지 않음',
 'cycles':1,'max_calls':440,'repair':False,'retry':False,'host_answer_fill':False,
 'repeats':'새 실행은 요청별 1회. 반복 안정성 추정은 하지 않음; legacy는 과거 원문과 비교 가능',
 'decisions':'복사만 성공하면 가설 지지 아님; 중립과 구별 못하면 요청축 제어 근거 아님; 구조/판정/선택성 각각 보고',
}

def schedule(seeds):
    specs=[]
    for si,seed in enumerate(seeds):
        for pid in PROBLEMS:
            for role in ROLES:
                if pid=='K01':specs.append(dict(seed=seed,cycle=0,problem_id=pid,task='legacy',arm='legacy',role_id=role['id'],stage='trace'))
                specs.append(dict(seed=seed,cycle=0,problem_id=pid,task='factorial',arm='explicit',role_id=role['id'],stage='trace'))
            for task in ('neutral','copy_control'):
                specs.append(dict(seed=seed,cycle=0,problem_id=pid,task=task,arm='explicit',role_id=None,stage='trace'))
            for depth in ('shallow','deep'):
                specs.append(dict(seed=seed,cycle=0,problem_id=pid,task='graph_only',arm='explicit',role_id='instance_'+depth+'_M0',stage='graph'))
    for s in specs:s['id']=f"s{seeds.index(s['seed']):02d}_{s['problem_id']}_{s['task']}_{s['role_id'] or 'none'}"
    # 모든 조건은 동일 배치에 배정한다. 관측 점수에 따라 진단 조건을 선택하지 않는다.
    specs.sort(key=lambda s:digest([ORDER_SEED,s['id']]))
    for i,s in enumerate(specs):s['position']=i
    return specs

def role_for(slot):
    return copy.deepcopy(next((r for r in ROLES if r['id']==slot['role_id']),None))

def problem_for(slot):return copy.deepcopy(PROBLEMS[slot['problem_id']])
