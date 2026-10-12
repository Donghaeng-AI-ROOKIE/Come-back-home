"""Verify both existing product profiles against saved maps without editing app."""
from pathlib import Path
import os,sys,socket,json,hashlib
from datetime import timedelta
O=Path(__file__).resolve().parents[1];R=O.parents[2];B=R/'결선/실험';C=R/'결선/개발/cbh-independent-alert-core-20261011'
os.environ.update(PERSIST_STORAGE='false',PUSH_ENABLED='false',MIND_POLICY_CONTRACT='guarded_core',MIND_POLICY_DEPLOYMENT='staging',MC_NUM_WALKERS='500',KEXAONE_MODEL=(B/'EFFICIENCY_avoid_wait_fix_20261010/scripts/KEXAONE_MODEL.txt').read_text().strip(),PERSONAL_CHANNEL_WEIGHT='.3',ALERT_SELECTION_POLICY='area_budget',MAX_ALERT_AREA_KM2='5.8',PUSH_TARGET_RES='9')
def blocked(*a,**k):raise RuntimeError('external network disabled')
socket.socket.connect=blocked;socket.create_connection=blocked;sys.path.insert(0,str(C/'backend'))
from app import storage
from app.config import settings
from app.phase2 import pipeline,continuous_prediction as cp,situation_link
from app.schemas.persona import Persona
from app.schemas.report import MissingReport
from app.schemas.prediction import PriorParams
from app.schemas.case import Case
from app.geo.roadnet import verified_network
from app.geo.road_anchors import connect_anchors
from app.phase3 import alerts,webpush_entry
from app.phase3.area_budget import cell_area_km2
from app.llm.usage_ledger import append_event
ledger=R/'결선/연구지원_사용기록/usage_events.jsonl';append_event({'event_type':'offline_product_verification_started','run_id':O.name,'model_calls':0,'remote_calls':0,'actual_cost':None},ledger)
saved=json.loads((B/'EFFICIENCY_KINTEX_v1_20261009/output/people/E09/prepared.json').read_text());spec=saved['arms']['D_full_prepared'];p=Persona.model_validate(spec['persona']);pr=PriorParams.model_validate(spec['prior']);sar=PriorParams.model_validate(saved['SAR_personal']);pr.sar_numeric_baseline={k:sar.model_dump(mode='json')[k] for k in ('strategy_probs','attraction_weights','radius_lognormal','attraction_levels','source','fallback_reason')};p.prepared_mind['policy']=json.loads((B/'CHANNEL_ALERT_repair_20261011/cases/current_policies/E09.json').read_text())['policy'];report=MissingReport.model_validate(saved['report'])
net=connect_anchors(verified_network(B/'MIND_completion_20261004/map_full_support/kintex_walk.graphml'),[report.lkp]+[a.location for a in p.attraction_points]);pipeline._load_roadnet=lambda *a,**k:(net,'')
def forbidden(*a,**k):raise AssertionError('fresh prior/model or legacy walk unexpectedly invoked')
pipeline._initial_prior=forbidden;pipeline.simulation.run_monte_carlo=forbidden
storage.personas.save(p.id,p)
raw=json.loads((B/'CHANNEL_ALERT_repair_20261011/results_independent_sar/E09_104729.json').read_text())['snapshots'];literature={s['hour']:s['cells'] for s in json.loads((B/'SAR_DISTANCE_ONLY_20261012/results/distance_maps/E09.json').read_text())['snapshots']}
def delta(got,want):return max(abs(got.get(k,0)-want.get(k,0)) for k in set(got)|set(want))
rows=[]
for arm,definition in [('current_literature70','literature_distance_prior'),('personalized_sar70','onboarded_population_prior')]:
 settings.statistical_channel_definition=definition
 c=Case(id='last-profile-E09-'+arm,report=report,lkp=report.lkp,lkp_time=report.lkp_time,prior=pr.model_copy(deep=True))
 c.prior_context_key=cp.prior_key(c,p);c.situation_links={'key':situation_link._key(c,p),'status':'none','links':[]}
 for snap in raw:
  hr=snap['hour'];result=pipeline.run_prediction(c,now=c.lkp_time+timedelta(hours=hr),seed=104729);q=result.quality
  a=result.poa_bottomup.cells;b=result.poa_statistical.cells;expected=literature[hr] if arm=='current_literature70' else snap['statistical']
  da,db=delta(a,snap['personal']),delta(b,expected);assert max(da,db)<1e-12
  assert q['unresolved_mass']==0 and q['personal_channel_weight']==.3 and not q['channels_identical']
  targets=alerts.target_parent_cells(alerts.select_alert_cells(c.current_poa));area=sum(cell_area_km2(t) for t in targets);assert area<=5.8+1e-9
  assert set(alerts.describe_alert(c)['target_cells'])==targets and set(alerts.target_parent_cells(webpush_entry.target_for_case(c)[1]))==targets
  rows.append({'arm':arm,'hour':hr,'personal_max_delta':da,'statistical_max_delta':db,'channel_tv':q['channel_total_variation'],'statistical_source':q['statistical_prior_source'],'statistical_uses_personal_mind':q['statistical_uses_conditional_mind_program'],'area_km2':area,'checkpoint_committed':q['checkpoint_committed']});print(rows[-1],flush=True)
 before=c.model_dump(mode='json');preview=pipeline.poa_at_elapsed(c,1,seed=104729);assert before==c.model_dump(mode='json')
 assert delta(preview,{k:.3*raw[0]['personal'].get(k,0)+.7*(literature[1] if arm=='current_literature70' else raw[0]['statistical']).get(k,0) for k in set(raw[0]['personal'])|set(literature[1] if arm=='current_literature70' else raw[0]['statistical'])})<1e-12
out={'person_id':'E09','prediction_seed':104729,'maps_verified':8,'rows':rows,'preview_side_effects':False,'engine_changes':0,'model_calls':0,'external_calls':0,'actual_push':0,'core_source_hashes':{str(p.relative_to(C)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [C/'backend/app/phase2/person_walk.py',C/'backend/app/phase2/persistent_context_walk.py',C/'backend/app/phase2/continuous_prediction.py']}}
(O/'results/product_pipeline_verification.json').write_text(json.dumps(out,indent=2)+'\n');append_event({'event_type':'offline_product_verification_finished','run_id':O.name,'model_calls':0,'remote_calls':0,'actual_cost':None,'verified_maps':8,'max_delta':max(max(r['personal_max_delta'],r['statistical_max_delta']) for r in rows)},ledger)
