"""Verify task launch text and persisted reply/task linkage against the live service."""
import json, sqlite3, time
from pathlib import Path
from uuid import uuid4
import requests
from dotenv import load_dotenv

load_dotenv('/data/yuehao/apps/ktp/app/backend/.env')
from ktp_backend.auth import _encode_jwt
from schemas.runtime import AuthTokenPayload
release = Path('/data/yuehao/apps/ktp/releases/workspace-task-receipts-20261012')
http = requests.Session()
http.headers['Authorization'] = 'Bearer '+_encode_jwt(AuthTokenPayload(user_id='task_receipt_smoke_20261012', role='admin', exp=time.time()+1800))
base = 'http://127.0.0.1:8005/api/product/v1'
def call(method, path, **kwargs):
    r = http.request(method, base+path, timeout=90, **kwargs)
    r.raise_for_status()
    return r.json()

c = sqlite3.connect('/data/yuehao/apps/ktp/data/ktp_v2_runtime.sqlite3')
seed = next(w for (raw,) in c.execute('SELECT payload_json FROM product_analysis_workflows ORDER BY rowid DESC') if (w:=json.loads(raw))['status']=='completed' and any(s['step_id']=='crop' and s['status']=='completed' for s in w['steps']))
conversation = call('POST', '/conversations', json={'title':'任务与启动回复关联验收'})['conversation_id']
context = {'workspace_id':'receipt-smoke-'+str(uuid4()), 'revision':int(time.time()*1000), 'execution_mode':'live', 'farm_id':seed.get('farm_id'), 'aoi':seed['aoi'], 'imagery_item_id':seed['imagery_item_id'], 'imagery_snapshot':seed['imagery_snapshot'], 'draft_task_ids':['crop'], 'active_workflow_id':None}
call('PUT', '/workspaces/'+context['workspace_id']+'/context', json=context)
action = str(uuid4())
payload = {'input':{'message':'执行作物识别', 'workspace_action':{'action_id':action,'task_ids':['crop']}}, 'context':{'workspace':context}}
accepted = call('POST','/conversations/'+conversation+'/submissions',json=payload,headers={'Idempotency-Key':action})
for _ in range(90):
    submission = call('GET','/submissions/'+accepted['submission_id'])
    if submission['status'] in {'completed','failed','cancelled'}: break
    time.sleep(1)
run = call('GET','/runs/'+submission['run_id'])
assert run['status']=='completed'
assert run['assistant']['summary'].endswith('下方任务卡片可查看进度和结果。')
ref = next(p for p in run['assistant']['parts'] if p['type']=='workflow_reference')
assert ref['part_id']
for _ in range(120):
    workflow = call('GET','/analysis-workflows/'+ref['data']['workflow_id'])
    if workflow['status'] in {'completed','failed','blocked'}: break
    time.sleep(1)
assert workflow['status']=='completed', workflow['detail']
assert workflow['run_id']==run['run_id'] and workflow['conversation_id']==conversation
assert workflow['requested_task_ids']==['crop']
replay = call('POST','/conversations/'+conversation+'/submissions',json=payload,headers={'Idempotency-Key':action})
assert replay['submission_id']==accepted['submission_id']
history = call('GET','/conversations/'+conversation+'/runs')['items']
assert len(history)==1 and history[0]['run_id']==run['run_id']
assert next(p for p in history[0]['assistant']['parts'] if p['type']=='workflow_reference')['data']['workflow_id']==workflow['workflow_id']
assert len(call('GET','/workspaces/'+context['workspace_id']+'/workflows'))==1
report = http.get('http://127.0.0.1:8005'+workflow['report_uri'], timeout=30)
assert report.status_code==200
result = {'passed':True,'conversation_id':conversation,'run_id':run['run_id'],'workflow_id':workflow['workflow_id'],'summary':run['assistant']['summary'],'status':workflow['status'],'reply_reference_matches_task':True,'history_restores_reference':True,'one_workflow':True,'replay_same_submission':True,'report_200':True}
(release/'live-smoke-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False),flush=True)
