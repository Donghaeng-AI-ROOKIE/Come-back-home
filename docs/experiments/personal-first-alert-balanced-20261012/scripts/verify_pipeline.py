"""Verify the reviewed core executor against the saved raw-channel replay; offline."""
from pathlib import Path
import os,sys,socket,json
ROOT=Path(__file__).resolve().parents[4];B=ROOT/'결선';X=ROOT/'결선/실험/CHANNEL_ALERT_repair_20261011';O=Path(__file__).resolve().parents[1]
os.environ.update(PERSIST_STORAGE='false',PUSH_ENABLED='false',MIND_POLICY_CONTRACT='guarded_core',MIND_POLICY_DEPLOYMENT='staging',MC_NUM_WALKERS='500',MPLCONFIGDIR='/tmp/cbh-mpl',KEXAONE_MODEL=(B/'실험/EFFICIENCY_avoid_wait_fix_20261010/scripts/KEXAONE_MODEL.txt').read_text().strip())
sys.path.insert(0,str(B/'개발/cbh-independent-alert-core-20261011/backend'))
def blocked(*a,**k):raise RuntimeError('no network in core verification')
socket.socket.connect=blocked;socket.create_connection=blocked
from app.phase2 import continuous_prediction as cp,combine,pipeline
from app import storage
from app.config import settings
from datetime import timedelta
settings.statistical_channel_definition='literature_distance_prior'
settings.alert_selection_policy='area_budget'
settings.max_alert_area_km2=5.8
settings.push_target_res=9
settings.personal_channel_weight=.3
settings.alert_coverage=.95
from app.schemas.persona import Persona
from app.schemas.prediction import PriorParams
from app.schemas.case import Case
from app.schemas.report import MissingReport
from app.geo.roadnet import verified_network
from app.geo.road_anchors import connect_anchors
saved=json.loads((B/'실험/EFFICIENCY_KINTEX_v1_20261009/output/people/E09/prepared.json').read_text());spec=saved['arms']['D_full_prepared'];p=Persona.model_validate(spec['persona']);pr=PriorParams.model_validate(spec['prior']);sar=PriorParams.model_validate(saved['SAR_personal']);pr.sar_numeric_baseline={k:sar.model_dump(mode='json')[k] for k in ('strategy_probs','attraction_weights','radius_lognormal','attraction_levels','source','fallback_reason')};p.prepared_mind['policy']=json.loads((X/'cases/current_policies/E09.json').read_text())['policy'];report=MissingReport.model_validate(saved['report']);c=Case(id='core-pair-E09',report=report,lkp=report.lkp,lkp_time=report.lkp_time)
net=connect_anchors(verified_network(B/'실험/MIND_completion_20261004/map_full_support/kintex_walk.graphml'),[report.lkp]+[a.location for a in p.attraction_points]);expected=json.loads((X/'results_independent_sar/E09_104729.json').read_text());rows=[]
literature={s['hour']:s['cells'] for s in json.loads((B/'실험/SAR_DISTANCE_ONLY_20261012/results/distance_maps/E09.json').read_text())['snapshots']}
storage.personas.save(p.id,p);c.prior=pr;c.prior_context_key=cp.prior_key(c,p)
pipeline._load_roadnet=lambda *a,**k:(net,'')
pipeline.situation_link.cached=lambda *a:[]
def forbidden(*a,**k):raise AssertionError('new model or legacy walk forbidden')
pipeline._initial_prior=forbidden;pipeline.simulation.run_monte_carlo=forbidden
for e in expected['snapshots']:
 result=pipeline.run_prediction(c,now=c.lkp_time+timedelta(hours=e['hour']),seed=104729)
 a=result.poa_bottomup.cells;b=result.poa_statistical.cells;q=result.quality
 assert q['unresolved_mass']==0 and q['statistical_definition']=='literature_distance_prior'
 assert not q['statistical_uses_onboarding_prior'] and not q['statistical_uses_conditional_mind_program']
 def delta(got,want):return max(abs(got.get(k,0)-want.get(k,0)) for k in set(got)|set(want))
 da,db=delta(a,e['personal']),delta(b,literature[e['hour']]);assert max(da,db)<1e-12
 assert 'statistical' not in c.continuous_state
 from app.phase3 import alerts
 from app.phase3.area_budget import cell_area_km2
 selected=alerts.select_alert_cells(c.current_poa);targets=alerts.target_parent_cells(selected);area=sum(cell_area_km2(t) for t in targets);assert area<=5.8+1e-9
 assert set(alerts.describe_alert(c)['target_cells'])==targets
 rows.append({'area_km2':area,'statistical_only_selected_cells':len(set(selected)-set(a)), 'hour':e['hour'],'personal_max_delta':da,'literature_max_delta':db,'checkpoint_committed':q['checkpoint_committed'],'source':q['statistical_prior_source']});print(rows[-1],flush=True)
before=c.model_dump(mode='json');preview=pipeline.poa_at_elapsed(c,1,seed=104729);assert c.model_dump(mode='json')==before
want=combine.alpha_pool([expected['snapshots'][0]['personal'],literature[1]],[.3,1-.3]);assert delta(preview,want)<1e-12
(O/'results/product_pipeline_verification.json').write_text(json.dumps({'person_id':'E09','walkers':500,'prediction_seed':104729,'new_model_calls':0,'external_calls':0,'actual_push':0,'actual_pipeline':True,'preview_side_effects':False,'preview_max_delta':delta(preview,want),'rows':rows},indent=2)+'\n')
