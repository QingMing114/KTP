"""Read real public observations without replacing the running application."""
import importlib.util,json,sqlite3,sys,time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv('/data/yuehao/apps/ktp/app/backend/.env')
import runtime,infra.imagery
root=Path('/data/yuehao/apps/ktp/releases/workspace-simple-yield-20261012/staging')
for name,file in [('infra.imagery.stac_provider','stac_provider.py'),('runtime.simple_yield','simple_yield.py'),('infra.imagery.power_weather','power_weather.py'),('infra.imagery.season_series','season_series.py'),('runtime.simple_yield_runner','simple_yield_runner.py')]:
 spec=importlib.util.spec_from_file_location(name,root/file);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m)
 setattr(sys.modules[name.rsplit('.',1)[0]],name.rsplit('.',1)[1],m)
from schemas.analysis_workflow import AnalysisWorkflowSummary
from runtime.simple_yield_runner import run_simple_yield
from runtime.simple_yield import SimpleYieldError,estimate_observed_season
c=sqlite3.connect('/data/yuehao/apps/ktp/data/ktp_v2_runtime.sqlite3')
seed=next(w for (raw,) in c.execute('SELECT payload_json FROM product_analysis_workflows ORDER BY rowid DESC') if (w:=json.loads(raw))['status']=='completed' and any(s['step_id']=='crop' and s['status']=='completed' for s in w['steps']))
w=AnalysisWorkflowSummary.model_validate(seed)
# This selects a test parameter profile, not verified field crop ground truth.
w.yield_inputs.confirmed_crop_class_id=0
started=time.time()
def progress(detail,percent):
 print(json.dumps({'percent':percent,'detail':detail},ensure_ascii=False),flush=True)
try:
 result=run_simple_yield(w,Path('/data/yuehao/apps/ktp/app/backend/var/artifacts/simple_yield_cache'),progress)
 result['engineering_test_crop_assumption']=True
 (root/'data-smoke-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps({'success':True,'estimate':result['estimated_yield_t_ha'],'season':result['season'],'observations':len(result['observations']),'rejected':len(result['rejected_observations']),'elapsed':round(time.time()-started)},ensure_ascii=False),flush=True)
except SimpleYieldError as exc:
 result={'success':False,'code':exc.code,'detail':str(exc),'elapsed':round(time.time()-started)}
 (root/'data-smoke-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps(result,ensure_ascii=False),flush=True)
