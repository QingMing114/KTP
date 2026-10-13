"""Live original-card context smoke; auth material remains in memory."""
import json,sqlite3,time
from pathlib import Path
from uuid import uuid4
import requests
from dotenv import load_dotenv
load_dotenv('/data/yuehao/apps/ktp/app/backend/.env')
from ktp_backend.auth import _encode_jwt
from schemas.runtime import AuthTokenPayload
http=requests.Session()
http.headers['Authorization']='Bearer '+_encode_jwt(AuthTokenPayload(user_id='workspace_flow_smoke_20261012',role='admin',exp=time.time()+1800))
base='http://127.0.0.1:8005/api/product/v1'
release=Path('/data/yuehao/apps/ktp/releases/workspace-flow-20261012')

def call(method,path,**kwargs):
    r=http.request(method,base+path,timeout=90,**kwargs);r.raise_for_status();return r.json()
c=sqlite3.connect('/data/yuehao/apps/ktp/data/ktp_v2_runtime.sqlite3')
seed=next(w for (raw,) in c.execute('SELECT payload_json FROM product_analysis_workflows ORDER BY rowid DESC') if (w:=json.loads(raw))['status']=='completed' and any(s['step_id']=='lai' and s['status']=='completed' for s in w['steps']))
context={'workspace_id':'flow-smoke-'+str(uuid4()),'revision':int(time.time()*1000),'execution_mode':'live','farm_id':seed.get('farm_id'),'aoi':seed['aoi'],'imagery_item_id':None,'imagery_snapshot':None,'active_workflow_id':None,'draft_task_ids':[]}
conversation=call('POST','/conversations',json={'title':'对话到任务流程验收 2026-10-12'})['conversation_id']

def ui():
    selected=context['imagery_item_id']
    return {'stage':'done' if context['active_workflow_id'] else 'ready' if selected else 'idle','cards':[
        {'card_id':'current-aoi','kind':'aoi','title':'当前分析 · 区域','fields':{'面积':str(context['aoi']['area_hectares'])+' ha'}},
        {'card_id':'professional-tasks','kind':'task_selection','title':'当前分析 · 任务选择','task_ids':context['draft_task_ids'],'selected_candidate_id':selected}],
        'imagery_candidates':[{'item_id':selected,'observed_at':seed['imagery_snapshot']['acquired_at'][:10],'cloud':'未知','recommended':True,'selected':True}] if selected else []}

def turn(message,action=None):
    call('PUT','/workspaces/'+context['workspace_id']+'/context',json=context)
    payload={'input':{'message':message,'workspace_action':action},'context':{'workspace':context,'workspace_ui':ui()}}
    key=action['action_id'] if action else str(uuid4())
    accepted=call('POST','/conversations/'+conversation+'/submissions',json=payload,headers={'Idempotency-Key':key})
    for _ in range(100):
        submission=call('GET','/submissions/'+accepted['submission_id'])
        if submission['status'] in {'completed','failed','cancelled'}:break
        time.sleep(1)
    run=call('GET','/runs/'+submission['run_id'])
    print(json.dumps({'message':message,'status':run['status'],'summary':run['assistant']['summary']},ensure_ascii=False),flush=True)
    assert run['status']=='completed',run['assistant']['summary']
    if action:
        replay=call('POST','/conversations/'+conversation+'/submissions',json=payload,headers={'Idempotency-Key':key})
        assert replay['submission_id']==accepted['submission_id']
    return run

def finish(run,expected):
    ref=next(p['data'] for p in run['assistant']['parts'] if p['type']=='workflow_reference')
    for _ in range(180):
        workflow=call('GET','/analysis-workflows/'+ref['workflow_id'])
        if workflow['status'] in {'completed','blocked','failed'}:break
        time.sleep(1)
    assert workflow['status']=='completed' and workflow['requested_task_ids']==expected, workflow['status']
    print(json.dumps({'workflow_id':workflow['workflow_id'],'status':workflow['status'],'tasks':workflow['requested_task_ids']},ensure_ascii=False),flush=True)
    return workflow

configured=turn('我想对这个地块做 LAI 反演，先准备配置')
plan=next(p['data'] for p in configured['assistant']['parts'] if p['type']=='analysis_plan')
assert plan['requested_task_ids']==['lai'] and not any(p['type']=='workflow_reference' for p in configured['assistant']['parts'])
context.update(revision=context['revision']+1,imagery_item_id=seed['imagery_item_id'],imagery_snapshot=seed['imagery_snapshot'],draft_task_ids=['lai'])
first=finish(turn('执行叶面积指数反演',{'action_id':str(uuid4()),'task_ids':['lai']}),['lai'])
context.update(revision=context['revision']+1,active_workflow_id=first['workflow_id'])
status=turn('当前任务完成了吗？只说明状态，不修改任务也不启动新任务。')
assert not any(p['type'] in {'analysis_plan','parameter_set','action_card','workflow_reference'} for p in status['assistant']['parts'])
next_plan=turn('接下来准备新一轮分析，只做作物识别，先不要启动。')
assert next(p['data'] for p in next_plan['assistant']['parts'] if p['type']=='analysis_plan')['requested_task_ids']==['crop']
assert not any(p['type']=='workflow_reference' for p in next_plan['assistant']['parts'])
context.update(revision=context['revision']+1,active_workflow_id=None,draft_task_ids=['crop'])
second=finish(turn('开始执行'),['crop'])
items=call('GET','/workspaces/'+context['workspace_id']+'/workflows')
assert len(items)==2 and first['workflow_id']!=second['workflow_id']
result={'conversation_id':conversation,'button_workflow_id':first['workflow_id'],'natural_workflow_id':second['workflow_id'],'button_tasks':first['requested_task_ids'],'natural_tasks':second['requested_task_ids'],'both_completed':True,'read_only_question_has_no_configuration':True,'typed_replay_same_submission':True,'workflow_count':len(items)}
(release/'live-smoke-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False),flush=True)
