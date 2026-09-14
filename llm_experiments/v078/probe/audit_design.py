"""동결 문제의 D/규칙 수 관계를 생산 preflight/measure 없이 검산한다."""
from collections import Counter
from itertools import product
from audit_io import need


def validate_protocol(s):
    ps=s['problems'];need(len(ps)==4 and len({p['id'] for p in ps})==4,'four structural problems')
    need(s['generator_variants']==['base'],'base only')
    need(len(s['seeds'])==2 and s['candidate_orders']==[[0,1],[1,0]],'factor schedule')
    families=[];reference=maximum=correct=0
    for p in ps:
        need(set(p)=={'id','facts','rules','goal'},'no answer-bearing problem fields')
        facts=set(p['facts']);need(len(facts)==len(p['facts']),'unique facts')
        by={r['id']:r for r in p['rules']};need(len(by)==len(p['rules']),'unique rules')
        target=p['goal'];meta=s['problem_metadata'][p['id']];families.append(meta['family'])
        depths=[];sizes=[];all_ids=[]
        for cname in s['reference_conditions']:
            ids=s['reference_plans'][p['id']][cname];need(len(ids)==len(set(ids)),'unique candidate rule ids')
            active={by[i]['conclusion']:by[i] for i in ids}
            need(len(active)==len(ids) and not set(active)&facts,'unique candidate productions')
            seen=set();usedfacts=set()
            def visit(atom,chain):
                need(atom not in chain,'cycle')
                if atom in facts:usedfacts.add(atom);return 0
                need(atom in active,'reachable candidate')
                r=active[atom];seen.add(r['id']);need(bool(r['premises']),'nonempty premises')
                return 1+max(visit(a,chain|{atom}) for a in r['premises'])
            d=visit(target,set())
            need(seen==set(ids) and usedfacts==facts,'all rules and facts support goal')
            known=set(facts)
            for rid in ids:
                r=by[rid];need(set(r['premises'])<=known,'candidate execution order');known.add(r['conclusion'])
            depths.append(d);sizes.append(len(seen));all_ids+=ids
        need(Counter(all_ids)==Counter(by.keys()),'all rules covered exactly once')
        def all_depths(atom,trail):
            need(atom not in trail,'full problem cyclic')
            ds={0} if atom in facts else set()
            for r in by.values():
                if r['conclusion']==atom:
                    for assignment in product(*(all_depths(a,trail|{atom}) for a in r['premises'])):
                        ds.add(1+max(assignment))
            return ds
        possible=all_depths(target,set());need(possible and depths==[min(possible),max(possible)] and depths[0]<depths[1],'actual global depth extremes')
        need(depths==s['depth_ranges'][p['id']]==[meta['shallow_D'],meta['deep_D']],'frozen depth metadata')
        need(sizes==[meta['shallow_rule_count'],meta['deep_rule_count']],'rule count metadata')
        if meta['family']=='equal_rule_count':need(sizes[0]==sizes[1],'equal count')
        elif meta['family']=='inverted_rule_count':need(sizes[0]>sizes[1],'inverted count')
        else:need(False,'unknown family')
        need(len(facts)+max(sizes)<=16,'existing graph node bound')
        reference+=sum(2*(n+2) for n in sizes)
        maximum+=8*(max(sizes)+2)
        correct+=8+6*sum(n+2 for n in sizes)
    need(Counter(families)=={'equal_rule_count':2,'inverted_rule_count':2},'two problems per stratum')
    need(reference==s['reference_generator_calls']==92 and maximum==s['max_model_generator_calls']==192,'independent generator budget')
    need(reference+maximum+32==s['max_inference_calls']==316 and correct==s['expected_inference_calls_if_all_target_routes_selected']==308,'independent calls budget')
    need(s['max_action_slots']==332 and s['metadata_slots']==16,'action budget')
    return {'verified':True,'distinct_structural_problems':len(ps),'actual_model_inference':False}
