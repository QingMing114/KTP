"""Server-side live smoke; tokens stay in process memory."""
import json
import sqlite3
import time
from pathlib import Path
from uuid import uuid4
import requests
from dotenv import load_dotenv
load_dotenv('/data/yuehao/apps/ktp/app/backend/.env')
from ktp_backend.auth import _encode_jwt
from schemas.runtime import AuthTokenPayload

http = requests.Session()
http.headers['Authorization'] = 'Bearer ' + _encode_jwt(AuthTokenPayload(user_id='workspace_smoke_20261012',role='admin',exp=time.time()+1800))
base='http://127.0.0.1:8005/api/product/v1'
def call(method,path,**kwargs):
    result=http.request(method,base+path,timeout=90,**kwargs)
    result.raise_for_status()
    return result.json()

manifest=call('GET','/manifest')
assert manifest['features']['workspace_assistant_actions']
connection=sqlite3.connect('/data/yuehao/apps/ktp/data/ktp_v2_runtime.sqlite3')
rows=connection.execute('SELECT payload_json FROM product_analysis_workflows ORDER BY rowid DESC').fetchall()
seed=next(item for item in (json.loads(row[0]) for row in rows) if item.get('status')=='completed' and item.get('owner_id')!='workspace_smoke_20261012' and any(step['step_id']=='lai' and step['status']=='completed' for step in item['steps']))
context={'workspace_id':'workspace-smoke-'+str(uuid4()),'revision':int(time.time()*1000),'execution_mode':'live','aoi':seed['aoi'],'farm_id':seed.get('farm_id'),'imagery_item_id':None,'imagery_snapshot':None,'active_workflow_id':None,'draft_task_ids':[]}
conversation=call('POST','/conversations',json={'title':'工作台助手部署验收 2026-10-12'})['conversation_id']
def turn(message,context,key):
    call('PUT','/workspaces/'+context['workspace_id']+'/context',json=context)
    body={'input':{'message':message},'context':{'workspace':context},'client':{'name':'workspace-smoke','version':'1'}}
    response=call('POST','/conversations/'+conversation+'/submissions',json=body,headers={'Idempotency-Key':key})
    for _ in range(120):
        sub=call('GET','/submissions/'+response['submission_id'])
        if sub['status'] in {'completed','failed','cancelled'}:
            break
        time.sleep(1)
    assert sub['status']=='completed',sub
    run=call('GET','/runs/'+sub['run_id'])
    print(json.dumps({'request':message,'status':run['status'],'summary':run['assistant']['summary'],'parts':[p['type'] for p in run['assistant']['parts']]},ensure_ascii=False),flush=True)
    return response,run,body

_,advice,_=turn('我已经框选区域，接下来我应该干嘛？',context,'no-image-'+str(uuid4()))
assert advice['assistant']['parts'][-1]['data']['action']=='search_imagery'
context={**context,'revision':context['revision']+1,'imagery_item_id':seed['imagery_item_id'],'imagery_snapshot':seed['imagery_snapshot']}
_,choices,_=turn('先告诉我这个选区能做什么分析，暂时不要执行。',context,'advice-'+str(uuid4()))
assert not any(part['type']=='workflow_reference' for part in choices['assistant']['parts'])
key='execute-'+str(uuid4())
submitted,execution,body=turn('请直接执行 LAI 反演和农作物识别两项任务。',context,key)
reference=next(part for part in execution['assistant']['parts'] if part['type']=='workflow_reference')
workflow_id=reference['data']['workflow_id']
replay=call('POST','/conversations/'+conversation+'/submissions',json=body,headers={'Idempotency-Key':key})
assert replay==submitted
for _ in range(180):
    workflow=call('GET','/analysis-workflows/'+workflow_id)
    if workflow['status'] in {'completed','failed','blocked'}:
        break
    time.sleep(1)
assert set(workflow['requested_task_ids'])=={'lai','crop'}
assert workflow['parameters']['target_resolution_m']==20
result={'conversation_id':conversation,'workflow_id':workflow_id,'workflow_status':workflow['status'],'steps':[{'step_id':s['step_id'],'status':s['status'],'detail':s['detail']} for s in workflow['steps']],'exactly_once_replay':True,'model_advice_and_execution':True}
Path('/data/yuehao/apps/ktp/releases/workspace-assistant-20261012/live-smoke-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False),flush=True)
assert workflow['status']=='completed',result
