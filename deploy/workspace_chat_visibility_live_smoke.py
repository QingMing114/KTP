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
http.headers['Authorization']='Bearer '+_encode_jwt(AuthTokenPayload(user_id='workspace_scroll_smoke_20261012',role='admin',exp=time.time()+1800))
base='http://127.0.0.1:8005/api/product/v1'
def call(method,path,**kwargs):
    r=http.request(method,base+path,timeout=90,**kwargs);r.raise_for_status();return r.json()
context={'workspace_id':'scroll-smoke-'+str(uuid4()),'revision':int(time.time()*1000),'execution_mode':'live','farm_id':None,'aoi':None,'imagery_item_id':None,'imagery_snapshot':None,'active_workflow_id':None,'draft_task_ids':[]}
call('PUT','/workspaces/'+context['workspace_id']+'/context',json=context)
conversation=call('POST','/conversations',json={'title':'冠层与估产说明验收 2026-10-12'})['conversation_id']
message='我们的遥感冠层指数能与 APSIM 产量估计互相替代吗？如果估产缺气象和土壤资料，是否可以直接把冠层分数作为产量？只解释，不配置也不启动任务。'
accepted=call('POST','/conversations/'+conversation+'/submissions',json={'input':{'message':message},'context':{'workspace':context}},headers={'Idempotency-Key':str(uuid4())})
for _ in range(90):
    sub=call('GET','/submissions/'+accepted['submission_id'])
    if sub['status'] in {'completed','failed','cancelled'}:break
    time.sleep(1)
run=call('GET','/runs/'+sub['run_id'])
assert run['status']=='completed'
parts=run['assistant']['parts']
assert not any(p['type'] in {'analysis_plan','parameter_set','action_card','workflow_reference'} for p in parts)
assert call('GET','/workspaces/'+context['workspace_id']+'/workflows')==[]
summary=run['assistant']['summary']
assert '冠层' in summary and any(term in summary for term in ['不能','不可','无法'])
result={'conversation_id':conversation,'run_id':run['run_id'],'summary':summary,'read_only':True,'workflow_count':0}
Path('/data/yuehao/apps/ktp/releases/workspace-chat-visibility-20261012/live-smoke-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False),flush=True)
