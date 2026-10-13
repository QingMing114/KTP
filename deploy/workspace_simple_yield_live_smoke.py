"""Live model/real public-data smoke. Credentials stay in process memory."""
import json, sqlite3, time
from pathlib import Path
from uuid import uuid4

import requests
from dotenv import load_dotenv

load_dotenv('/data/yuehao/apps/ktp/app/backend/.env')
from ktp_backend.auth import _encode_jwt
from schemas.runtime import AuthTokenPayload

release = Path('/data/yuehao/apps/ktp/releases/workspace-simple-yield-20261012')
http = requests.Session()
http.headers['Authorization'] = 'Bearer ' + _encode_jwt(AuthTokenPayload(user_id='simple_yield_smoke_20261012', role='admin', exp=time.time()+1800))
base = 'http://127.0.0.1:8005/api/product/v1'
def call(method, path, **kwargs):
    response = http.request(method, base+path, timeout=90, **kwargs)
    response.raise_for_status()
    return response.json()

c = sqlite3.connect('/data/yuehao/apps/ktp/data/ktp_v2_runtime.sqlite3')
seed = next(w for (raw,) in c.execute('SELECT payload_json FROM product_analysis_workflows ORDER BY rowid DESC') if (w:=json.loads(raw))['status']=='completed' and any(s['step_id']=='crop' and s['status']=='completed' for s in w['steps']))
context = {'workspace_id': 'simple-smoke-'+str(uuid4()), 'revision': int(time.time()*1000), 'execution_mode': 'live', 'farm_id': seed.get('farm_id'), 'aoi': seed['aoi'], 'imagery_item_id': seed['imagery_item_id'], 'imagery_snapshot': seed['imagery_snapshot'], 'draft_task_ids': [], 'active_workflow_id': None}
conversation = call('POST', '/conversations', json={'title': '小麦玉米自动简化估产验收'})['conversation_id']

def turn(message, key=None):
    call('PUT', '/workspaces/'+context['workspace_id']+'/context', json=context)
    payload = {'input': {'message': message}, 'context': {'workspace': context}}
    key = key or str(uuid4())
    accepted = call('POST', '/conversations/'+conversation+'/submissions', json=payload, headers={'Idempotency-Key': key})
    for _ in range(100):
        sub = call('GET', '/submissions/'+accepted['submission_id'])
        if sub['status'] in {'completed', 'failed', 'cancelled'}: break
        time.sleep(1)
    run = call('GET', '/runs/'+sub['run_id'])
    assert run['status']=='completed', run['assistant']['summary']
    print(json.dumps({'message': message, 'summary': run['assistant']['summary'], 'part_types': [p['type'] for p in run['assistant']['parts']]}, ensure_ascii=False), flush=True)
    replay = call('POST', '/conversations/'+conversation+'/submissions', json=payload, headers={'Idempotency-Key': key})
    assert replay['submission_id']==accepted['submission_id']
    return run

assert call('GET', '/manifest')['features']['simple_yield_estimation']
configured = turn('这个地块想做小麦或玉米的产量估计，没有历史实收数据，也不能填写播种收获日期。先配置自动简化估产，不要启动。')
plan = next(p['data'] for p in configured['assistant']['parts'] if p['type']=='analysis_plan')
assert plan['requested_task_ids']==['yield_simple'], plan['requested_task_ids']
assert not any(p['type']=='workflow_reference' for p in configured['assistant']['parts'])
context.update(revision=context['revision']+1, draft_task_ids=['yield_simple'])
executed = turn('开始执行自动简化估产。')
ref = next(p['data'] for p in executed['assistant']['parts'] if p['type']=='workflow_reference')
def finish():
    for _ in range(240):
        w = call('GET', '/analysis-workflows/'+ref['workflow_id'])
        if w['status'] in {'completed', 'blocked', 'failed'}: return w
        time.sleep(1)
    raise AssertionError('workflow timeout')
w = finish()
assert w['effective_task_ids']==['crop', 'yield_simple']
step = next(s for s in w['steps'] if s['step_id']=='yield_simple')
confirmed = False
if step['result'].get('reason_code')=='crop_confirmation_required':
    # Engineering profile assumption only; not a ground-truth crop assertion.
    call('PUT', '/analysis-workflows/'+w['workflow_id']+'/yield-inputs', json={'yield_inputs': {'confirmed_crop_class_id': 0}})
    confirmed = True
    w = finish()
    step = next(s for s in w['steps'] if s['step_id']=='yield_simple')
assert w['status'] in {'completed', 'blocked'}, w['status']
assert w['yield_inputs']['sowing_date'] is None and w['yield_inputs']['field_dataset_id'] is None
assert [s['step_id'] for s in w['steps']]==['imagery', 'crop', 'yield_simple']
assert requests.get('http://127.0.0.1:8005'+w['report_uri'], timeout=30).status_code in {401, 403}
report = http.get('http://127.0.0.1:8005'+w['report_uri'], timeout=30)
assert report.status_code==200
if step['status']=='completed':
    assert step['result']['yield_basis']=='grain_dry_matter' and step['result']['locally_calibrated'] is False
    assert http.get('http://127.0.0.1:8005'+step['result']['report_uri'], timeout=30).status_code==200
else:
    assert step['result']['reason_code'] in {'season_in_progress', 'insufficient_observations', 'season_not_identified', 'observation_gap', 'weak_season_signal', 'weather_incomplete', 'weather_unavailable', 'weather_empty'}
    assert 'estimated_yield_t_ha' not in step['result']
context.update(revision=context['revision']+1, active_workflow_id=w['workflow_id'])
explained = turn('现在估产是什么状态？只解释当前结果和限制，不修改配置也不启动任务。')
assert not any(p['type'] in {'analysis_plan', 'parameter_set', 'action_card', 'workflow_reference'} for p in explained['assistant']['parts'])
assert len(call('GET', '/workspaces/'+context['workspace_id']+'/workflows'))==1
result = {'conversation_id': conversation, 'workflow_id': w['workflow_id'], 'status': w['status'], 'reason_code': step['result'].get('reason_code'), 'observations': step['result'].get('observation_count', len(step['result'].get('observations', []))), 'as_of': step['result'].get('as_of'), 'requested': w['requested_task_ids'], 'effective': w['effective_task_ids'], 'no_manual_dates': True, 'one_workflow': True, 'replay_same_submission': True, 'summary_report_200': True, 'crop_profile_was_engineering_assumption': confirmed, 'not_scientific_accuracy_validation': True, 'status_explanation': explained['assistant']['summary']}
(release/'live-smoke-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False), flush=True)
