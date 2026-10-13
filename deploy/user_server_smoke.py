"""Validate a deployed user server without printing login credentials or tokens."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--admin-user', required=True)
    parser.add_argument('--url', default='http://127.0.0.1:3002')
    args = parser.parse_args()
    app, data = args.app.resolve(), args.data_dir.resolve()
    from dotenv import load_dotenv
    load_dotenv(app / 'backend/.env', override=True)
    sys.path.insert(0, str(app / 'backend'))
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin
    import requests

    root = data / 'validation'
    root.mkdir(parents=True, exist_ok=True)
    http = requests.Session()
    base = args.url.rstrip('/')
    assert http.get(base+'/health', timeout=20).status_code == 200
    assert http.get(base+'/api/product/v1/conversations', timeout=20).status_code == 401
    login = http.post(base+'/v2/auth/login', json={'user_id': args.admin_user,
                      'password': (data/'credentials/admin-password').read_text().strip()}, timeout=30)
    assert login.status_code == 200, 'Admin login failed'
    http.headers['Authorization'] = 'Bearer '+login.json()['access_token']
    def call(method, path, **kwargs):
        response = http.request(method, base+'/api/product/v1'+path, timeout=60, **kwargs)
        assert response.ok, f'{method} {path}: HTTP {response.status_code}'
        return response.json()
    manifest = call('GET', '/manifest')
    assert manifest['features']['workspace_card_context']
    geometry = {'type':'Polygon','coordinates':[[[100.35,38.95],[100.351,38.95],[100.351,38.951],[100.35,38.951],[100.35,38.95]]]}
    snapshot = {'item_id':'deployment-demo-scene','collection':'sentinel-2-l2a','acquired_at':'2026-09-10T00:00:00Z'}
    conversation = call('POST','/conversations',json={'title':'kt-server 部署验收：估产模拟演示'})['conversation_id']
    results = []
    for crop in ['wheat','maize']:
        context = {'workspace_id':'deploy-demo-'+str(uuid4()),'revision':int(time.time()*1000),'execution_mode':'live',
                   'aoi':{'geometry':geometry,'source':'drawn'},'imagery_item_id':snapshot['item_id'],'imagery_snapshot':snapshot,
                   'draft_task_ids':['yield_simple'],'active_workflow_id':None}
        call('PUT','/workspaces/'+context['workspace_id']+'/context',json=context)
        action = str(uuid4())
        endpoint = '/conversations/'+conversation+'/submissions'
        body = {'input':{'message':'使用模拟数据演示估产','workspace_action':{'action_id':action,'task_ids':['yield_simple'],'yield_demo_crop':crop}},'context':{'workspace':context}}
        accepted = call('POST',endpoint,json=body,headers={'Idempotency-Key':action})
        for _ in range(150):
            submission = call('GET','/submissions/'+accepted['submission_id'])
            if submission['status'] in {'completed','failed'}: break
            time.sleep(.5)
        assert submission['status']=='completed'
        run = call('GET','/runs/'+submission['run_id'])
        ref = next(part for part in run['assistant']['parts'] if part['type']=='workflow_reference')
        for _ in range(150):
            workflow = call('GET','/analysis-workflows/'+ref['data']['workflow_id'])
            if workflow['status'] in {'completed','failed','blocked'}: break
            time.sleep(.5)
        assert workflow['status']=='completed' and workflow['data_mode']=='demo'
        result = next(step['result'] for step in workflow['steps'] if step['step_id']=='yield_simple')
        expected = 6.2 if crop=='wheat' else 9.1
        assert result['estimated_yield_t_ha']==expected
        report = http.get(base+result['report_uri'],timeout=30)
        assert report.status_code==200 and 'APSIM 模板' in report.text and '模拟数据' in report.text
        replay = call('POST',endpoint,json=body,headers={'Idempotency-Key':action})
        assert replay['submission_id']==accepted['submission_id']
        assert len(call('GET','/workspaces/'+context['workspace_id']+'/workflows'))==1
        results.append({'crop':crop,'workflow_id':workflow['workflow_id'],'report_200':True,'idempotent':True})
    # Read-only natural-language planning must reach the configured real model.
    context['revision']+=1
    context['active_workflow_id']=workflow['workflow_id']
    call('PUT','/workspaces/'+context['workspace_id']+'/context',json=context)
    accepted = call('POST',endpoint,json={'input':{'message':'解释这次估产为何是模拟数据，以及真实估产需要哪些输入；不要执行新任务。'},'context':{'workspace':context}})
    for _ in range(180):
        status = call('GET','/submissions/'+accepted['submission_id'])
        if status['status'] in {'completed','failed'}: break
        time.sleep(.5)
    assert status['status']=='completed','Real model conversation did not complete'
    model_run = call('GET','/runs/'+status['run_id'])
    explanation = model_run['assistant']['summary']
    assert explanation and any(word in explanation for word in ('模拟', '演示', '构造'))
    assert len(call('GET','/workspaces/'+context['workspace_id']+'/workflows'))==1
    # Run actual algorithms against a clearly named synthetic probe, not field accuracy validation.
    lut = np.loadtxt(os.environ['LAI_LUT_PATH'])
    selected = lut[np.argmin(abs(lut[:,0]-3.0)),[1,2,3,6,7]]
    image = root/'synthetic-deployment-probe.tif'
    values = np.broadcast_to(selected[:,None,None],(5,12,12)).astype(np.float32).copy()
    with rasterio.open(image,'w',driver='GTiff',height=12,width=12,count=5,dtype='float32',
                       crs='EPSG:32647',transform=from_origin(600000,4300000,20,20)) as output:
        output.write(values)
    from v2.tools.lai_report_handler import run_lai_html_report
    observation, artifacts = run_lai_html_report(image_path=str(image),artifact_output_dir=str(root/'lai'))
    assert observation.status=='success', 'Actual LAI computation failed on synthetic probe'
    assert all(Path(observation.payload[key]).is_file() for key in ['report_path','lai_raster_path','lai_preview_path'])
    from infra.imagery.crop_spatial import run_crop_spatial_analysis
    crop = run_crop_spatial_analysis(reflectance_path=image,output_dir=root/'crop')
    assert len(crop['class_scores'])==6
    assert np.isclose(sum(row['score'] for row in crop['class_scores']),1)
    # Existing APSIM validation output should also open through its canonical report endpoint.
    apsim = call('POST','/apsim/yield-reports',json={'mode':'demo'})
    assert apsim['status']=='success'
    report = http.get(base+apsim['artifact']['view_url'],timeout=30)
    assert report.status_code==200 and 'APSIM' in report.text
    summary = {'passed':True,'auth_login':True,'anonymous_api_rejected':True,'real_model_conversation':True,
               'yield_demo_cases':results,'actual_lai_on_synthetic_probe':True,'crop_model_inference_on_synthetic_probe':True,
               'apsim_validation_report_200':True,'scientific_accuracy_validated':False}
    (root/'live-smoke-result.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False))


if __name__ == '__main__':
    main()
