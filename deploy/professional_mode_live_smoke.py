"""Authenticated live planning checks; never prints deployment credentials."""
import json
import time
from pathlib import Path
from uuid import uuid4
import requests

base = 'http://127.0.0.1:3002'
data = Path('/home/D/zhanghuaxiang_D/apps/ktp')
http = requests.Session()
assert http.get(base + '/health', timeout=20).status_code == 200
assert http.get(base + '/workspace', timeout=20).status_code == 200
login = http.post(base + '/v2/auth/login', json={'user_id': 'zhanghuaxiang_D', 'password': (data / 'credentials/admin-password').read_text().strip()}, timeout=30)
assert login.status_code == 200, 'Login failed'
http.headers['Authorization'] = 'Bearer ' + login.json()['access_token']
def call(method, path, **kwargs):
    response = http.request(method, base + '/api/product/v1' + path, timeout=60, **kwargs)
    assert response.ok, f'{method} {path}: HTTP {response.status_code}'
    return response.json()

assert call('GET', '/manifest')['features']['workspace_professional_reviews']
farm = call('GET', '/farms')['items'][0]
workspace = 'professional-validation-' + str(uuid4())
context = {'workspace_id': workspace, 'revision': 1, 'execution_mode': 'live', 'professional_mode': True,
           'farm_id': farm['farm_id'], 'aoi': {'geometry': farm['geometry'], 'source': 'drawn'},
           'imagery_item_id': None, 'imagery_snapshot': None, 'draft_task_ids': ['lai'],
           'imagery_search': {'start_date': '2026-06-01', 'end_date': '2026-09-30', 'max_cloud_cover': 20}}
context = call('PUT', f'/workspaces/{workspace}/context', json=context)
conv = call('POST', '/conversations', json={'title': '专业模式部署验收'})['conversation_id']
sub = call('POST', f'/conversations/{conv}/submissions', json={'input': {'message': '请执行当前选区的 LAI 反演，使用六月至九月的低云影像，先给我参数确认。'}, 'context': {'workspace': context}})
for _ in range(100):
    status = call('GET', '/submissions/' + sub['submission_id'])
    if status['status'] in {'completed', 'failed', 'cancelled'}:
        break
    time.sleep(.5)
assert status['status'] == 'completed', 'Live planner did not complete'
run = call('GET', '/runs/' + status['run_id'])
review = next(part['data']['review'] for part in run['assistant']['parts'] if part['type'] == 'professional_review')
assert review['phase'] == 'search' and review['status'] == 'pending'
assert not call('GET', f'/workspaces/{workspace}/workflows'), 'An unconfirmed tool started'
assert call('GET', f'/workspaces/{workspace}/professional-reviews')[0]['review_id'] == review['review_id']
endpoint = '/professional-reviews/' + review['review_id'] + '/decision'
body = {'context': context, 'decision': 'cancel'}
key = {'Idempotency-Key': 'live-review-' + review['review_id']}
cancelled = call('POST', endpoint, json=body, headers=key)
assert cancelled['review']['status'] == 'cancelled'
assert call('POST', endpoint, json=body, headers=key) == cancelled
assert not call('GET', f'/workspaces/{workspace}/workflows')
result = {'health_200': True, 'workspace_200': True, 'authenticated': True, 'real_planner': True,
          'professional_review_pending': True, 'no_unconfirmed_workflow': True, 'cancelled': True, 'idempotent_replay': True,
          'workspace_id': workspace, 'run_id': run['run_id']}
(data / 'validation/professional-mode-live.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result))
