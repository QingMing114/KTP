"""Exercise the deployed demo workflow and report without printing credentials."""
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

release = Path('/data/yuehao/apps/ktp/releases/workspace-yield-demo-20261013')
session = requests.Session()
session.headers['Authorization'] = 'Bearer '+_encode_jwt(AuthTokenPayload(user_id='yield_demo_smoke_20261013',role='admin',exp=time.time()+1800))
base = 'http://127.0.0.1:8005/api/product/v1'

def call(method,path,**kwargs):
    response = session.request(method,base+path,timeout=60,**kwargs)
    response.raise_for_status()
    return response.json()

connection = sqlite3.connect('/data/yuehao/apps/ktp/data/ktp_v2_runtime.sqlite3')
seed = next(item for (raw,) in connection.execute('SELECT payload_json FROM product_analysis_workflows ORDER BY rowid DESC') if (item:=json.loads(raw)).get('data_mode','live')=='live' and item['status']=='completed')
results = []
for task,crop in [('yield_simple','wheat'),('yield_simple','maize'),('yield','wheat'),('yield','maize')]:
    conversation = call('POST','/conversations',json={'title':'估产模拟演示验收'})['conversation_id']
    context = {'workspace_id':'yield-demo-'+str(uuid4()),'revision':int(time.time()*1000),'execution_mode':'live',
               'farm_id':seed.get('farm_id'),'aoi':seed['aoi'],'imagery_item_id':seed['imagery_item_id'],'imagery_snapshot':seed['imagery_snapshot'],
               'active_workflow_id':None,'draft_task_ids':[task]}
    call('PUT','/workspaces/'+context['workspace_id']+'/context',json=context)
    action = str(uuid4())
    body = {'input':{'message':'使用模拟数据演示估产','workspace_action':{'action_id':action,'task_ids':[task],'yield_demo_crop':crop}},'context':{'workspace':context}}
    path = '/conversations/'+conversation+'/submissions'
    accepted = call('POST',path,json=body,headers={'Idempotency-Key':action})
    for _ in range(120):
        submission = call('GET','/submissions/'+accepted['submission_id'])
        if submission['status'] in {'completed','failed','cancelled'}: break
        time.sleep(.5)
    assert submission['status']=='completed',submission['status']
    run = call('GET','/runs/'+submission['run_id'])
    reference = next(part for part in run['assistant']['parts'] if part['type']=='workflow_reference')
    assert reference['data']['data_mode']=='demo'
    for _ in range(120):
        workflow = call('GET','/analysis-workflows/'+reference['data']['workflow_id'])
        if workflow['status'] in {'completed','failed','blocked'}: break
        time.sleep(.5)
    assert workflow['status']=='completed' and workflow['data_mode']=='demo' and workflow['demo_crop']==crop
    assert workflow['run_id']==run['run_id']
    result = next(step['result'] for step in workflow['steps'] if step['step_id']==task)
    assert result['simulated'] and not result['apsim_executed']
    expected = 6.2 if crop=='wheat' else 9.1
    assert result['estimated_yield_t_ha']==expected
    report = session.get('http://127.0.0.1:8005'+result['report_uri'],timeout=30)
    report.raise_for_status()
    assert all(text in report.text for text in ['APSIM 模板','模拟数据','未运行 APSIM','LAI 时序','生长阶段时间轴',f'{expected:.3f}'])
    data = session.get('http://127.0.0.1:8005'+result['report_data_uri'],timeout=30)
    data.raise_for_status()
    assert data.json()['result']['estimated_yield_t_ha']==expected
    assert max(data.json()['result']['timeseries']['grain_wt'])*.01==expected
    summary = session.get('http://127.0.0.1:8005'+workflow['report_uri'],timeout=30)
    summary.raise_for_status()
    assert '模拟数据' in summary.text
    replay = call('POST',path,json=body,headers={'Idempotency-Key':action})
    assert replay['submission_id']==accepted['submission_id']
    assert len(call('GET','/workspaces/'+context['workspace_id']+'/workflows'))==1
    history = call('GET','/conversations/'+conversation+'/runs')['items']
    assert next(p for p in history[0]['assistant']['parts'] if p['type']=='workflow_reference')['data']['workflow_id']==workflow['workflow_id']
    results.append({'task':task,'crop':crop,'workflow_id':workflow['workflow_id'],'yield_t_ha':expected,'report_uri':result['report_uri'],
                    'report_200':True,'data_200':True,'summary_200':True,'one_workflow':True,'history_matches':True})
output = {'passed':True,'cases':results}
(release/'live-smoke-result.json').write_text(json.dumps(output,ensure_ascii=False,indent=2))
print(json.dumps(output,ensure_ascii=False),flush=True)
