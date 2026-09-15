"""신규 구조 8개를 응답 관측 없이 결정적으로 구성한다. 실행 중 문제를 생성/선별하지 않는다.

구조 단위는 같은 facts/goal을 공유하는 두 proof DAG의 쌍이다.
단일 가지/부분 모티프가 겹칠 수 있으므로 8개를 IID 무작위 표본이라고 부르지 않는다.
"""
from __future__ import annotations
from copy import deepcopy
from itertools import permutations
from pathlib import Path
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parent
# 각 튜플은 전제 -> 새 결과다. A/B/C는 공통 초기 사실, G는 공통 목표다.
# e/d 이름은 아래 재명명 때 완전히 제거되며 모델 입력에 노출되지 않는다.
CASES = [
    ('T01', 'equal_rule_count',
     [('AB','e0'),('BC','e1'),('AC','e2'),(['e0','e1','e2'],'G')],
     [('AB','d0'),('C','d1'),(['d0','d1'],'d2'),(['d2'],'G')]),
    ('T02', 'equal_rule_count',
     [('AB','e0'),(['e0','C'],'e1'),(['e0'],'e2'),(['e1','e2'],'G')],
     [('AB','d0'),(['d0'],'d1'),(['d1','C'],'d2'),(['d2'],'G')]),
    ('T03', 'equal_rule_count',
     [('A','e0'),('B','e1'),('C','e2'),(['e0','e1'],'e3'),(['e3','e2'],'G')],
     [('A','d0'),('BC','d1'),(['d0','d1'],'d2'),(['d2'],'d3'),(['d3'],'G')]),
    ('T04', 'equal_rule_count',
     [('AB','e0'),(['e0'],'e1'),('C','e2'),(['e2'],'e3'),(['e1','e3'],'G')],
     [('A','d0'),('B','d1'),(['d0','d1'],'d2'),(['d2','C'],'d3'),(['d3'],'G')]),
    ('T05', 'inverted_rule_count',
     [('AB','e0'),('BC','e1'),('AC','e2'),(['e0','e1','e2'],'G')],
     [('A','d0'),(['d0','B'],'d1'),(['d1','C'],'G')]),
    ('T06', 'inverted_rule_count',
     [('AB','e0'),('BC','e1'),(['e0'],'e2'),(['e1'],'e3'),(['e2','e3'],'G')],
     [('ABC','d0'),(['d0'],'d1'),(['d1'],'d2'),(['d2'],'G')]),
    ('T07', 'inverted_rule_count',
     [('A','e0'),('B','e1'),(['e0','C'],'e2'),(['e1','C'],'e3'),(['e2','e3'],'G')],
     [('A','d0'),(['d0','B','C'],'d1'),(['d1'],'d2'),(['d2'],'G')]),
    ('T08', 'inverted_rule_count',
     [('AB','e0'),(['e0','C'],'e1'),(['e0'],'e2'),('C','e3'),(['e1','e2','e3'],'G')],
     [('AB','d0'),(['d0','C'],'d1'),(['d1','B'],'d2'),(['d2'],'G')]),
]

FROZEN_REQUEST_KEYS = (
    'model','identity','seeds','conditions','reference_conditions','candidate_orders',
    'candidate_ids','selector_schema','generation_schema','headers','api_defaults',
    'num_predict','request_utf8_byte_limit','timeout_seconds','generator_variants',
    'id_assignments','count_select_header','count_conditions','control_select_addendum',
    'support_origin','support_only_in_selector',
)


def ordered_codes(namespace: str) -> list[str]:
    """Python random 구현/버전과 무관한 SHA-256 순서. 실험 결과에 의존하지 않는다."""
    return sorted((f'{i:02d}' for i in range(100)),
                  key=lambda x: hashlib.sha256(f'v084-fixed-labels-20260915/{namespace}/{x}'.encode()).digest())


def profile(problem: dict, ids: list[str]) -> dict:
    depth = {a: 0 for a in problem['facts']}
    by_id = {r['id']: r for r in problem['rules']}
    steps = []
    for rid in ids:
        r = by_id[rid]
        d = 1 + max(depth[a] for a in r['premises'])
        steps.append({'rule_id':rid, 'conclusion':r['conclusion'],
                      'premises':[{'atom':a,'depth':depth[a]} for a in r['premises']], 'depth':d})
        depth[r['conclusion']] = d
    return {'facts':[{'atom':a,'depth':0} for a in problem['facts']],
            'steps':steps,'goal_depth':depth[problem['goal']], 'rule_count':len(ids)}


def topology_signature(problem: dict, paths: list[list[str]]) -> str:
    """공통 사실 매핑을 보존한 두 DAG의 완전한 기호 불변 정규형.

    fact 및 내부 결과의 모든 전단사를 열거한다. 깊이/층별 노드 수만 비교하지 않는다.
    후보의 shallow/deep 순서는 서로 다른 실제 D로 구별되므로 정규형에서도 유지한다.
    """
    facts = problem['facts']; goal = problem['goal']
    by_id = {r['id']:r for r in problem['rules']}
    possibilities = []
    for fact_order in permutations(facts):
        fids = {a:i for i,a in enumerate(fact_order)}
        encoded = []
        for path in paths:
            rules = [by_id[r] for r in path]
            inner = [r['conclusion'] for r in rules if r['conclusion'] != goal]
            representations = []
            for order in permutations(inner):
                labels = dict(fids)
                labels.update({a:len(facts)+i for i,a in enumerate(order)})
                labels[goal] = len(facts)+len(inner)
                representations.append(tuple(sorted((labels[r['conclusion']], tuple(sorted(labels[a] for a in r['premises']))) for r in rules)))
            encoded.append(min(representations))
        possibilities.append(tuple(encoded))
    return json.dumps([len(facts),min(possibilities)],separators=(',',':'))


def build_protocol() -> dict:
    old = json.loads((ROOT/'data/v083_protocol.json').read_text(encoding='utf-8'))
    s = deepcopy(old)
    problems = []; plans = {}; profiles = {}; metadata = {}; signatures = {}
    for pi,(pid,family,short,long) in enumerate(CASES):
        atoms = list('ABC')+[con for _,con in short+long if con!='G']+['G']
        acodes = ordered_codes(pid+'/atoms')
        amap = {a:chr(ord('N')+pi)+code for a,code in zip(atoms,acodes)}
        rcodes = ordered_codes(pid+'/rules'); cursor = 0; rules = []; routes = []
        for route in (short,long):
            names=[]
            for premise, conclusion in route:
                rid=chr(ord('a')+pi)+rcodes[cursor];cursor+=1;names.append(rid)
                rules.append({'id':rid,'premises':[amap[a] for a in premise], 'conclusion':amap[conclusion]})
            routes.append(names)
        rules.sort(key=lambda r:hashlib.sha256((pid+'/dictionary/'+r['id']).encode()).digest())
        problem={'id':pid,'facts':[amap[a] for a in 'ABC'],'rules':rules,'goal':amap['G']}
        problems.append(problem)
        plans[pid]=dict(zip(s['reference_conditions'],routes))
        profiles[pid]=[profile(problem,r) for r in routes]
        metadata[pid]={'family':family, 'structural_problem_id':pid,
            'shallow_D':profiles[pid][0]['goal_depth'],'deep_D':profiles[pid][1]['goal_depth'],
            'shallow_rule_count':len(routes[0]),'deep_rule_count':len(routes[1]),
            'evaluation_role':'response_unseen_prespecified_structural_case',
            'prior_exposure_batches':[],
            'presentation':'SHA-256 고정 기호 및 규칙 사전 순서; 네 후보 위치/ID 표시를 모두 배정'}
        signatures[pid]=topology_signature(problem,routes)
    old_sigs={p['id']:topology_signature(p,[old['reference_plans'][p['id']][k] for k in old['reference_conditions']]) for p in old['problems']}
    if len(set(signatures.values()))!=8 or set(signatures.values()) & set(old_sigs.values()):
        raise ValueError('신규 구조 중복 또는 v083 구조의 단순 재명명')
    s.update(contract='v084-frozen-structural-holdout-r1',problems=problems,reference_plans=plans,
        frozen_profiles=profiles,problem_metadata=metadata,
        depth_ranges={pid:[x['goal_depth'] for x in ps] for pid,ps in profiles.items()},
        metrics_by_problem={pid:['D'] if m['family']=='equal_rule_count' else ['D','W'] for pid,m in metadata.items()},
        baseline_sha256='6132c1db632afd8e1bd8d5c98bc2a0639252ddcedd21a44423ff876b1d239a5e',
        baseline_plan_sha256='1e9ad6f1be311d3c8e5de34eed786f4234f0f94e3b6e05cc0e444e5262f3ed8e',
        prior_verifier_source_sha256=hashlib.sha256((ROOT/'prior/v083_source.zip').read_bytes()).hexdigest(),
        prior_observed_calls=1576, selector_variants=['candidate_id','correct_values'],
        generation_selector_variants=['candidate_id','correct_values'], diagnostic_only_variants=[],
        swapped_field_policy='not_assigned_in_v084',
        assigned_model_trials=384, assigned_control_trials=32, assigned_D_trials=256, assigned_W_trials=128,
        assigned_D_pairs=128, assigned_W_pairs=64, selector_calls=384,
        generated_model_trials=256, selection_only_trials=128,
        max_inference_calls=2284, max_action_slots=2316, metadata_slots=32,
        expected_inference_calls_if_all_target_routes_selected=2220,
        minimum_inference_calls_if_all_selections_mappable=2156,
        distinct_structural_problems=8, independent_new_structures=8, holdout=True,
        holdout_definition='v083과 비동형인 사전 고정 신규 구조쌍; 응답 미관측, IID 무작위 표본 아님',
        iid_structure_sampling=False, outcome_based_case_selection=False,
        scientific_design='동결된 직접/정확숫자 선택기와 explicit_rule 생성기로 신규 구조 8개에서 D 양방향 종단 재현. W는 선택 전용 보조 대조.',
        primary_estimand='equal_weight_structural_case_mean_of_paired_D_bidirectional_end_to_end_differences',
        primary_unit='structural_case_not_seed_or_presentation',
        secondary_estimands=['per_case_pair_counts','presentation_robust_end_to_end','all_seed_all_presentation_end_to_end','W_selection','shared_reference_generation'],
        no_automatic_p_value=True, frozen_request_keys=list(FROZEN_REQUEST_KEYS),
        structure_signatures=signatures, prior_structure_signatures=old_sigs,
        release_design_status='frozen_before_any_v084_model_response')
    return s


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check',action='store_true');p.add_argument('--out',type=Path)
    a=p.parse_args();s=build_protocol()
    if a.check:
        on_disk=json.loads((ROOT/'data/protocol.json').read_text(encoding='utf-8'))
        if s!=on_disk:raise ValueError('동결 protocol과 재구성 결과 불일치')
        print('신규 구조 8개 및 동결 protocol 재구성 일치; 모델 호출 0회')
    elif a.out:
        with a.out.open('x',encoding='utf-8') as f:json.dump(s,f,ensure_ascii=False,indent=2);f.write('\n')
    else:
        for pid,m in s['problem_metadata'].items():print(pid,m['family'],m['shallow_D'],m['deep_D'],m['shallow_rule_count'],m['deep_rule_count'])
    return 0

if __name__=='__main__':raise SystemExit(main())
