"""모델의 실제 출력을 다음 요청에 연결한다. 정답표·oracle import 없음."""
from __future__ import annotations
from .contracts import *
from .plan import dependency_ids
# 두 oneshot에서는 이 한 구절만 바뀐다.
GAP_ORIGINAL='same_as_goal AND NOT in_facts'
GAP_COMMUTED='(NOT in_facts) AND same_as_goal'
READING=(
 '단독 사실 주장 probe를 검사한다. rules로 새 증명을 만들지 않는다.\n'
 'observed에 입력의 probe.atom, problem.goal, problem.facts를 각각 probe_atom, goal_atom, facts로 그대로 적는다.\n'
 'primitives.same_as_goal은 probe.atom과 problem.goal이 정확히 같은 문자열인지다.\n'
 'primitives.in_facts는 probe.atom이 problem.facts 배열의 원소인지다.\n')
ONE_END='각 중간값과 최종 판정을 직접 작성한다. 이 값들은 프로그램이 대신 채우지 않는다. JSON 객체 하나만 출력한다.'
EXPRESSIONS={'proof':'(a AND b)','gap_direct':'((NOT b) AND a)','not':'(NOT b)','gap_and':'(a AND b)'}

def request_bytes(plan,slot,parents):
    # parents는 응답의 형식만 검사한 payload. 올바른지 판단하여 대체하지 않는다.
    for pid in dependency_ids(slot):require(parents.get(pid) is not None,'유효한 실제 부모 응답 필요')
    stage=slot['stage'];case=next(c for c in plan['cases'] if c['id']==slot['case_id'])
    base=strict_json(unb64(plan['baseline']['templates']['00']['request_b64']))
    base['options']['seed']=slot['seed']
    if stage in ('extract','oneshot_original','oneshot_commuted'):
        system=READING
        if stage=='extract':system+='입력 읽기와 두 primitives만 작성한다. finding이나 새 증명을 작성하지 않는다. JSON 객체 하나만 출력한다.'
        else:
            formula=GAP_ORIGINAL if stage=='oneshot_original' else GAP_COMMUTED
            system+='finding.answer_only_accepts = same_as_goal; finding.proof_and_goal_accepts = same_as_goal AND in_facts; finding.gap_detected = '+formula+'.\n'+ONE_END
        schema=schema_for(stage)
        system+='\n출력 JSON Schema(정답값이 아닌 형식 명세):\n'+wire(schema).decode()
        base['format']=schema
        base['messages']=[{'role':'system','content':system},{'role':'user','content':'problem: '+wire(case['problem']).decode()+'\nprobe: '+wire(case['probe']).decode()}]
    else:
        # v049 불리언 요청 문구/형식을 그대로 이용하고 a/b/식/seed만 연결한다.
        prim=parents[slot['block_id']+'__extract']['primitives']
        b=prim['in_facts'] if stage!='gap_and' else parents[slot['block_id']+'__not']['value']
        inp={'a':prim['same_as_goal'],'b':b,'expression':EXPRESSIONS[stage]}
        base['messages'][1]['content']='input: '+wire(inp).decode()
    return wire(base)
