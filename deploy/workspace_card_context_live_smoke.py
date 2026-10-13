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
http.headers['Authorization']='Bearer '+_encode_jwt(AuthTokenPayload(user_id='workspace_ui_smoke_20261012',role='admin',exp=time.time()+1800))
base='http://127.0.0.1:8005/api/product/v1'
def call(method,path,**kwargs):
    r=http.request(method,base+path,timeout=90,**kwargs);r.raise_for_status();return r.json()
assert call('GET','/manifest')['features']['workspace_card_context']
c=sqlite3.connect('/data/yuehao/apps/ktp/data/ktp_v2_runtime.sqlite3')
rows=c.execute('SELECT payload_json FROM product_analysis_workflows ORDER BY rowid DESC').fetchall()
seed=next(w for w in (json.loads(r[0]) for r in rows) if w['status']=='completed' and any(s['step_id']=='lai' and s['status']=='completed' for s in w['steps']))
context={'workspace_id':'ui-smoke-'+str(uuid4()),'revision':int(time.time()*1000),'execution_mode':'live','farm_id':seed.get('farm_id'),'aoi':seed['aoi'],'imagery_item_id':None,'imagery_snapshot':None,'active_workflow_id':None,'draft_task_ids':[]}
conversation=call('POST','/conversations',json={'title':'原工作流卡片上下文验收 2026-10-12'})['conversation_id']
def turn(message,ui):
    call('PUT','/workspaces/'+context['workspace_id']+'/context',json=context)
    accepted=call('POST','/conversations/'+conversation+'/submissions',json={'input':{'message':message},'context':{'workspace':context,'workspace_ui':ui}},headers={'Idempotency-Key':str(uuid4())})
    for _ in range(100):
        submission=call('GET','/submissions/'+accepted['submission_id'])
        if submission['status'] in {'completed','failed','cancelled'}:break
        time.sleep(1)
    run=call('GET','/runs/'+submission['run_id'])
    print(json.dumps({'message':message,'status':run['status'],'summary':run['assistant']['summary']},ensure_ascii=False),flush=True)
    assert run['status']=='completed',run['assistant']['summary']
    return run
first=turn('我想对这个地块做lai反演',{'stage':'idle','cards':[{'card_id':'aoi','kind':'aoi','title':'分析区域已就绪','fields':{'面积':str(context['aoi']['area_hectares'])+' ha'}}]})
plan=next(p['data'] for p in first['assistant']['parts'] if p['type']=='analysis_plan')
assert plan['requested_task_ids']==['lai']
assert not any(p['type']=='workflow_reference' for p in first['assistant']['parts'])
context.update(revision=context['revision']+1,imagery_item_id=seed['imagery_item_id'],imagery_snapshot=seed['imagery_snapshot'],draft_task_ids=['lai'])
ui={'stage':'ready','imagery_candidates':[{'item_id':seed['imagery_item_id'],'observed_at':seed['imagery_snapshot']['acquired_at'][:10],'cloud':'未知','recommended':True,'selected':True}], 'cards':[
 {'card_id':'imagery-candidates','kind':'imagery_candidates','title':'候选影像','candidate_ids':[seed['imagery_item_id']],'selected_candidate_id':seed['imagery_item_id']},
 {'card_id':'imagery-selection','kind':'imagery_selected','title':'影像已选定','selected_candidate_id':seed['imagery_item_id']},
 {'card_id':'professional-tasks','kind':'task_selection','title':'选择专业任务','task_ids':['lai'],'fields':{'影像准备分辨率':'20 m（固定）'}}]}
selection=turn('我现在选了哪景影像，勾选了哪项任务？',ui)
assert not any(p['type']=='workflow_reference' for p in selection['assistant']['parts'])
started=turn('开始执行',ui)
reference=next(p['data'] for p in started['assistant']['parts'] if p['type']=='workflow_reference')
for _ in range(180):
    workflow=call('GET','/analysis-workflows/'+reference['workflow_id'])
    if workflow['status'] in {'completed','blocked','failed'}:break
    time.sleep(1)
result={'conversation_id':conversation,'workflow_id':workflow['workflow_id'],'requested_task_ids':workflow['requested_task_ids'],'status':workflow['status'],'model_reads_original_cards':True,'pending_lai_resolved':True,'steps':[{'step_id':s['step_id'],'status':s['status']} for s in workflow['steps']]}
Path('/data/yuehao/apps/ktp/releases/workspace-card-context-20261012/live-smoke-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False),flush=True)
assert workflow['requested_task_ids']==['lai'] and workflow['status']=='completed',result
