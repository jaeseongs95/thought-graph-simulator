"""모델 패키지 비교. 순서·방향·문제·seed가 같은 요청끼리만 비교한다."""
from .contracts import digest
from order_probe_v054.design import PROBLEMS, ARMS, DIRECTIONS, RULE_ORDERS
MODELS = ('reference', 'candidate')
CANDIDATE = 'gemma3:4b'
MAX_CALLS = 240
POLICY = {
    'question': '같은 한국어 D 지시·두 규칙순서에서 모델 패키지를 바꾸면 선택적 제어가 달라지는가',
    'models': '기존 Qwen 4B Q4_K_M과 gemma3:4b 4B급 Q4_K_M. 새 기준선에도 Qwen 120회를 실제 재실행',
    'intervention': '동일 문제/순서/방향/seed의 HTTP 요청은 model 필드만 다름. 모델별 프롬프트/샘플링 최적화 없음',
    'schedule': '10 seed마다 두 모델의 12요청 블록. 모델 선후 5:5, 블록 내부 순서는 두 모델에서 동일',
    'budget': '총 240회: 모델당 방향지정 80, 중립 40. metadata 조회는 추론 호출 아님. warmup 0',
    'primary': '문제·순서·seed별 shallow/deep 둘 다 유효하고 최소/최대 깊이가 달라야 선택적 성공',
    'robust': '문제·seed별 두 규칙순서에서 모두 선택적 성공. 실패 순서나 문제를 제외하지 않음',
    'secondary': '모델별 유효성, 순서 효과, 중립 대비 변화. 같은 응답의 재집계를 독립 표본으로 더하지 않음',
    'incomplete': 'HTTP/identity/사용자 중단은 미완료. 전체 비교율은 null. 출력 형식 오류/무효 증명은 원문대로 관측',
    'provenance': '합성 서버는 synthetic_fixture로 고정. 실제 가중치·GPU 실행의 외부 전자서명 아님',
    'interpretation': '모델 패키지에는 가중치·학습·tokenizer·native template·언어 처리 차이가 함께 포함됨. 학습 우선순위의 단독 인과 검증 아님',
    'sampling': '같은 숫자 옵션/seed이지 모델별 분포·동일 난수 경로·동일 FLOPs 보장 아님. 모델 권장설정 순위 평가 아님',
    'cost': '블록별 cold load/cache가 섞인다. 원문 token/time만 보고하며 속도 우월성을 검정하지 않음',
    'scope': '고정된 2문제의 외부 유효 증명 깊이 D. 내부 사고 상태나 A/M 통합 성공으로 확대하지 않음',
    'retry': False, 'repair': False, 'host_answer_fill': False, 'download_models': False,
}

def schedule(previous):
    """완전 교차 240회. 모델 선후는 seed index의 짝/홀로 사전 균형화한다."""
    out=[]
    for i,seed in enumerate(previous['seeds']):
        cells=[s for s in previous['slots'] if s['seed']==seed]
        assert len(cells)==12
        order=MODELS if i%2==0 else tuple(reversed(MODELS))
        for j,key in enumerate(order):
            for cell in cells:
                out.append({**cell,'id':key+'__'+cell['id'],'reference_slot_id':cell['id'],
                    'model_key':key,'block':2*i+j,'seed_index':i,'position':len(out), 'task':'model_probe'})
    return out

def actions(slots):
    result=[]
    for block in range(20):
        cells=[s for s in slots if s['block']==block];assert len(cells)==12
        model=cells[0]['model_key']
        result.append({'kind':'metadata','id':f'b{block:02d}.before','block':block,'model_key':model})
        result.extend({'kind':'call','id':s['id'],'slot':s} for s in cells)
        result.append({'kind':'metadata','id':f'b{block:02d}.after','block':block,'model_key':model})
    for index,item in enumerate(result):item['index']=index
    return result
