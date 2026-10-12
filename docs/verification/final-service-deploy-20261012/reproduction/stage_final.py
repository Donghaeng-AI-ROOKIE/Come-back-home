import os,json,datetime,socket,uuid
from pathlib import Path
def blocked(*a,**kw):raise RuntimeError('network forbidden in preflight')
socket.socket.connect=blocked;socket.create_connection=blocked
from app import storage
from app.config import settings
from app.schemas.persona import Persona
from app.schemas.report import MissingReport
from app.schemas.case import Case
from app.schemas.prediction import PriorParams
from app.phase0 import person_preparation,mind_preparation
from app.phase2 import pipeline,continuous_prediction,situation_link
from app.llm import exaone,mind_policy
from app.phase3 import alerts,webpush_entry
from app.phase3.area_budget import cell_area_km2
f=json.loads(Path('/fixture.json').read_text())
p=Persona.model_validate(f['persona']);p.id='deploy-final-e09';p.guardian_id=os.environ.get('SMOKE_OWNER','00000000-0000-4000-8000-000000000009')
p.prepared_initial['fingerprint']=person_preparation.fingerprint(p)
p.prepared_mind['policy']=f['policy'];p.prepared_mind['revision']=mind_policy.revision(p)
p.mind_preparation_status=dict(p.mind_preparation_status,state='ready',revision=p.prepared_mind['revision'])
assert mind_preparation.ready(p)[0] is not None,mind_preparation.ready(p)[1]
r=MissingReport.model_validate(f['report']);r.id='deploy-final-e09-r';r.persona_id=p.id;r.lkp_time=datetime.datetime.now()-datetime.timedelta(hours=1)
sar=PriorParams.model_validate(f['sar']);prior=person_preparation.apply_prepared(p,r,sar,exaone._default_prior(p,r),[])
assert prior.initial_interpretation['status']=='applied',prior.initial_interpretation
prior.sar_numeric_baseline={k:sar.model_dump(mode='json')[k] for k in ('strategy_probs','attraction_weights','radius_lognormal','attraction_levels','source','fallback_reason')}
prior.source='prepared_person'
c=Case(id='deploy-final-e09-c',guardian_id=p.guardian_id,synthetic_test=True,report=r,lkp=r.lkp,lkp_time=r.lkp_time,prior=prior)
c.prior_context_key=continuous_prediction.prior_key(c,p)
c.situation_links={'key':situation_link._key(c,p),'status':'none','links':[]}
storage.personas.save(p.id,p);storage.cases.save(c.id,c)
if os.environ.get('SEED_ONLY')!='true':
 result=pipeline.run_prediction(c,now=c.lkp_time+datetime.timedelta(hours=1),seed=104729)
 q=result.quality
 assert q['statistical_definition']=='literature_distance_prior' and q['personal_channel_weight']==.3 and not q['channels_identical']
 assert q['unresolved_mass']==0 and c.roadnet_used
 combined=result.poa_combined.cells;a=result.poa_bottomup.cells;b=result.poa_statistical.cells
 delta=max(abs(combined.get(x,0)-(.3*a.get(x,0)+.7*b.get(x,0))) for x in set(a)|set(b))
 assert delta<1e-12
 target=set(alerts.describe_alert(c)['target_cells']);area=sum(cell_area_km2(t) for t in target)
 assert area<=5.8+1e-9 and settings.push_target_res==9
 assert set(alerts.target_parent_cells(webpush_entry.target_for_case(c)[1]))==target
 assert alerts.notify_prediction(c)['status']=='synthetic_isolated'
 print(json.dumps({'passed':True,'personalization_applied':True,'engine':q['engine'],'channels_identical':q['channels_identical'],'channel_tv':q['channel_total_variation'],'weight_delta':delta,'target_cells':len(target),'area_km2':area,'res':settings.push_target_res,'model_calls':0,'saved_synthetic_SAR_K_replay':True,'real_push':0}),flush=True)
else:print(json.dumps({'seeded':True,'synthetic_only':True,'prepared_policy_ready':True,'initial_interpretation_applied':True,'model_calls':0}),flush=True)
