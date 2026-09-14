"""v071 실측 요청과 새 요청의 차이, Gemma 최초 pin/실행 중 drift 경계를 검사한다."""
import unittest, base64
from unittest.mock import patch
from fixtures import *
import previous

class Replication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=design.build_plan(baseline_path(),'v072_replication','synthetic')
        cls.old,cls.oldplan,_,_=previous.inspect_prior(baseline_path().read_bytes())
    def test_archived_model_is_Qwen_target_is_installed_Gemma(self):
        self.assertEqual(self.oldplan['identity']['model'],'qwen3:4b-instruct')
        self.assertEqual(self.plan['identity']['model'],'gemma3:4b')
        tags=common.load(self.old['metadata/b00_before/1.response.raw.json'])['models']
        tag=next(x for x in tags if x['name']=='gemma3:4b')
        self.assertEqual(self.plan['identity']['digest'],tag['digest'])
        self.assertEqual(self.plan['identity']['tag_details'],tag['details'])
    def test_unobserved_native_template_not_fabricated_in_plan(self):
        for field in ('template','parameters','model_info','show_sha256'):
            self.assertNotIn(field,self.plan['identity'])
        self.assertEqual(self.plan['identity']['native_fingerprint_source'],'records/b00_before.json')
    def test_100_slots_and_140_actions_identical_to_v071(self):
        self.assertEqual(self.plan['slots'],self.oldplan['slots'])
        self.assertEqual(self.plan['actions'],self.oldplan['actions'])
    def test_60_fixed_inputs_only_model_field_changes(self):
        checked=0
        for s in self.plan['slots']:
            if s['arm']=='model_depth':continue
            q=design.request_for(self.plan,s)
            old=self.old['wire/'+s['id']+'/request.wire.json']
            q['model']=self.oldplan['identity']['model']
            self.assertEqual(common.wire(q),old)
            checked+=1
        self.assertEqual(checked,60)
    def test_40_history_dependent_requests_preserve_same_function(self):
        # 이전 원문을 넣는 것은 이 회귀시험뿐. 실제 execute는 현 배치 wire를 읽는다.
        checked=0
        for s in self.plan['slots']:
            if s['arm']!='model_depth':continue
            h={sid:self.old['wire/'+sid+'/response.raw.json'] for sid in s['history_ids']}
            q=design.request_for(self.plan,s,h);q['model']=self.oldplan['identity']['model']
            self.assertEqual(common.wire(q),self.old['wire/'+s['id']+'/request.wire.json'])
            checked+=1
        self.assertEqual(checked,40)
    def test_current_bad_Gemma_content_not_replaced_with_Qwen_or_truth(self):
        s=next(s for s in self.plan['slots'] if s['arm']=='model_depth')
        text='\n {"depths":[63,0]} \t'
        env=envelope({'depths':[1,2]},'gemma3:4b');env['message']['content']=text
        q=design.request_for(self.plan,s,{s['history_ids'][0]:common.wire(env)})
        payload=common.load(q['messages'][0]['content'].split('\n\ninput: ')[1])
        self.assertEqual(payload['depth_report'],text)
        self.assertEqual(q['model'],'gemma3:4b')
    def test_frozen_archived_totals_not_current_model_success(self):
        r=report.summarize(self.plan,records_for(self.plan)[0],'complete')
        self.assertEqual(r['archived_v071']['depth_correct'],2)
        self.assertEqual(r['archived_v071']['model_pipeline'],2)
        self.assertFalse(r['limits']['Gemma_constructor_verified'])
        self.assertFalse(r['limits']['v071_concurrent_comparison'])
    def test_cached_baseline_cannot_be_mutated_by_caller(self):
        fs,plan,req,_=previous.inspect_prior(baseline_path().read_bytes())
        req['model']='tampered';plan['protocol']['headers']['depth']='tampered';fs.clear()
        fs,plan,req,_=previous.inspect_prior(baseline_path().read_bytes())
        self.assertEqual(req['model'],'qwen3:4b-instruct')
        self.assertNotEqual(plan['protocol']['headers']['depth'],'tampered')
        self.assertIn('plan.json',fs)

    def test_original_v071_responses_keep_the_same_scores_offline(self):
        records=[];files={}
        for slot in self.plan['slots']:
            history={sid:files['wire/'+sid+'/response.raw.json'] for sid in slot['history_ids']}
            q=design.request_for(self.plan,slot,history)
            env=common.load(self.old['wire/'+slot['id']+'/response.raw.json'])
            env['model']=self.plan['identity']['model']  # 합성 회귀시험의 envelope만 변경한다.
            raw=common.wire(env);files['wire/'+slot['id']+'/response.raw.json']=raw
            records.append({'id':slot['id'],'http_status':200,'error':None,'request_sha256':common.sha(common.wire(q)),
                'response_sha256':common.sha(raw),'response_b64':base64.b64encode(raw).decode(),'elapsed_ns':1})
        r=report.summarize(self.plan,records,'complete');v=verify._summary(self.plan,records,'complete')
        self.assertTrue(common.exact(r,v));self.assertEqual(report.render(r),verify._render(v))
        a=r['overall']
        self.assertEqual((a['depth_reports']['successes'],a['oracle_selection']['successes'],a['model_selection']['successes'],a['model_pipeline']['successes']),(2,28,24,2))
        self.assertEqual(a['model_pipeline_pair_successes'],0)
        self.assertEqual([g['selection']['successes'] for g in r['position_breakdown']],[20,8,20,4])
        self.assertEqual([r['request_repetition'][a]['unique_request_bytes'] for a in ('estimate','oracle_depth','model_depth')],[20,32,16])

class NativePin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan=design.build_plan(baseline_path(),'v072_nativepin','synthetic')
    def items(self):
        e=self.plan['identity'];values=[e['server'],{'models':[{'name':e['model'],'digest':e['digest'],'details':e['tag_details']}]},
            {'details':e['tag_details'],'template':'synthetic native','model_info':{'x':1},'parameters':'b 2\na 1','system':'test-only'}]
        return [{'http_status':200,'error':None,'response_b64':base64.b64encode(common.wire(x)).decode()} for x in values]
    def change(self,items,index,fn):
        x=deepcopy(items);value=common.load(base64.b64decode(x[index]['response_b64']));fn(value)
        x[index]['response_b64']=base64.b64encode(common.wire(value)).decode();return x
    def test_first_pin_production_and_verifier_accept(self):
        x=self.items()
        self.assertTrue(run.identity_matches(x,self.plan['identity']))
        self.assertTrue(verify._identity_matches(x,self.plan['identity']))
    def test_template_system_parameters_modelinfo_drift_rejected(self):
        first=self.items()
        for key,value in [('template','different'),('system','changed'),('parameters','a 2'),('model_info',{'x':2}),('capabilities',['different'])]:
            changed=self.change(first,2,lambda s:s.update({key:value}))
            self.assertFalse(run.identity_matches(changed,self.plan['identity'],first),key)
            self.assertFalse(verify._identity_matches(changed,self.plan['identity'],first),key)
    def test_parameter_order_only_normalization_is_explicit(self):
        first=self.items();changed=self.change(first,2,lambda s:s.update(parameters='a 1\nb 2'))
        self.assertTrue(run.identity_matches(changed,self.plan['identity'],first))
        self.assertTrue(verify._identity_matches(changed,self.plan['identity'],first))
    def test_wrong_digest_version_details_template_types_rejected(self):
        first=self.items()
        changes=[(0,lambda x:x.update(version='different')),(1,lambda x:x['models'][0].update(digest='0'*64)),
            (1,lambda x:x['models'][0]['details'].update(parameter_size='999B')),
            (2,lambda x:x.update(template=None)),(2,lambda x:x.update(template='')),
            (2,lambda x:x.update(parameters=42)),(2,lambda x:x.update(model_info=[]))]
        for i,fn in changes:
            x=self.change(first,i,fn)
            self.assertFalse(run.identity_matches(x,self.plan['identity']))
            self.assertFalse(verify._identity_matches(x,self.plan['identity']))
    def test_missing_template_stops_before_inference(self):
        with executed('missing_template') as (_,pp,p,f,r,res,state):
            self.assertEqual(state['calls'],0);self.assertEqual(r['state'],'stopped')
    def test_native_drift_stops_after_first_block_without_retry(self):
        with executed('late_native') as (_,pp,p,f,r,res,state):
            self.assertEqual(state['calls'],5);self.assertEqual(r['state'],'stopped')
            self.assertFalse(common.load(f['records/b00_after.json'])['identity_ok'])
