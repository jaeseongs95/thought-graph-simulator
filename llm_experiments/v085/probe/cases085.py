"""관측된 T01~T08의 보존 검사. 새 holdout을 생성하거나 응답에 따라 문제를 선택하지 않는다."""
from __future__ import annotations
from itertools import permutations
import json

FROZEN_REQUEST_KEYS = (
    'model','identity','seeds','conditions','reference_conditions','candidate_orders',
    'candidate_ids','selector_schema','generation_schema','headers','api_defaults',
    'num_predict','request_utf8_byte_limit','timeout_seconds','generator_variants',
    'id_assignments','count_select_header','count_conditions','control_select_addendum',
    'support_origin','support_only_in_selector',
)



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


def build_protocol():
    import core085
    return core085.spec()


def main():
    import argparse
    from audit085 import validate_protocol
    p=argparse.ArgumentParser(description='관측된 v084 구조를 변경 없이 사용하는지 확인한다.')
    p.add_argument('--check',action='store_true',required=True);p.parse_args()
    s=build_protocol();validate_protocol(s)
    print(json.dumps({'checked':True,'structural_cases':8,'new_holdout_cases':0,'model_calls':0},ensure_ascii=False))

if __name__=='__main__':main()
