from pathlib import Path
import os,sys,json,socket,hashlib
os.environ.update(PERSIST_STORAGE='false',PUSH_ENABLED='false',MPLCONFIGDIR='/tmp/cbh-mpl')
socket.socket.connect=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('no network'))
import numpy as np,h3
from shapely.geometry import shape,Point
from shapely.ops import unary_union
O=Path(__file__).resolve().parents[1];R=O.parents[2];B=Path("/Users/damisoda/Desktop/서강대학교/INSIGHT/인공지능 루키대회/결선/실험/PERSONAL_FIRST_ALERT_COST_20261012");E=R/'결선/실험/EFFICIENCY_KINTEX_v1_20261009';X=R/'결선/실험/CHANNEL_ALERT_repair_20261011';L=R/'결선/실험/SAR_DISTANCE_ONLY_20261012'
sys.path.insert(0,str(R/'결선/개발/cbh-independent-alert-core-20261011/backend'))
from app.phase3.area_budget import select,cell_area_km2
from app.geo.h3cover import cover
from app.phase2.combine import alpha_pool
from app.phase3 import alerts,devices
from app.config import settings
from app.schemas.case import Case
from app.schemas.report import MissingReport
from app.schemas.device import Platform,Engagement
from app import storage
p=json.loads((O/'protocol.json').read_text());m=json.loads((O/'truth_manifest.json').read_text())
assert hashlib.sha256((O/'protocol.json').read_bytes()).hexdigest()==m['protocol_sha256']
truth=json.loads((O/'truth_private.json').read_text())
assert hashlib.sha256((O/'truth_private.json').read_bytes()).hexdigest()==m['truth_sha256']
old=json.loads((B/'results/confirmation_selections.json').read_text());pre={(z['person_id'],z['prediction_seed'],z['hour']):z for z in old if z['arm']=='preliminary'};current={(z['person_id'],z['prediction_seed'],z['hour']):z for z in old if z['arm']=='candidate'}
adapt=json.loads((O/'results/adaptive_selections.json').read_text());chosen={(z['person_id'],z['prediction_seed'],z['hour']):z for z in adapt if z['arm']==p['candidate_selection']['candidate']}
guarded=json.loads((O/'results/exploration_selections.json').read_text());chall={(z['person_id'],z['prediction_seed'],z['hour']):z for z in guarded if z['arm']==p['personal50_res8_challenger']['candidate']}
phase1=json.loads((O/'results/phase1_no_guards/exploration_selections.json').read_text());other={(z['person_id'],z['prediction_seed'],z['hour'],z['arm']):z for z in phase1 if z['arm'] in ('base_w0.5_r8','base_w0.7_r8','base_w0.9_r8')}
adm=json.loads((E/'service_comparison/baseline_selections.json').read_text());admr={z['person_id']:z for z in adm['rows']}
geoms={k:shape(json.loads((E/f'service_comparison/boundaries/{k}_osm.geojson').read_text())['features'][0]['geometry']) for k in ('ilsanseo','ilsandong','goyang')}
arms=p['references'];rows=[];selections=[];fanout_checks=0
for pid in p['people']:
 report=MissingReport.model_validate(json.loads((E/f'output/people/{pid}/prepared.json').read_text())['report'])
 q={z['hour']:z['cells'] for z in json.loads((L/f'results/distance_maps/{pid}.json').read_text())['snapshots']}
 district=unary_union([geoms[k] for k in admr[pid]['districts']])
 for seed in p['prediction_seeds']:
  personal={z['hour']:z['personal'] for z in json.loads((X/f'results_independent_sar/{pid}_{seed}.json').read_text())['snapshots']}
  for hr in p['hours']:
   key=(pid,seed,hr);z=chosen[key];assert set(current[key]['cells'])<=set(z['cells'])
   controls={}
   for weight in (.5,.7,.9):controls[f'personal{int(100*weight)}_res8']=other[(*key,f'base_w{weight}_r8')]
   native={'preliminary':(pre[key],7),'current':(current[key],9),'directional_candidate':(z,9),'best_directional50_res8':(chall[key],8),**{a:(v,8) for a,v in controls.items()}}
   matched=select(q[hr],z['area_km2'],500,9);native['stat_only_matched_area']=({'cells':matched,'area_km2':sum(cell_area_km2(c) for c in cover(matched,9))},9)
   local=[t for t in truth if t['person_id']==pid]
   for arm in arms:
    if arm in ('alert_district_proxy','alert_city_proxy'):
     geom=district if arm=='alert_district_proxy' else geoms['goyang'];area=admr[pid]['district_area_km2' if arm=='alert_district_proxy' else 'city_area_km2']
     for t in local:
      pos=next(z['position'] for z in t['snapshots'] if z['hour']==hr)
      rows.append(dict(person_id=pid,prediction_seed=seed,truth_seed=t['truth_seed'],future=t['future'],hour=hr,arm=arm,hit=int(geom.covers(Point(pos['lng'],pos['lat']))),area_km2=area))
     continue
    sel,res=native[arm];cells=sel['cells'];targets=cover(cells,res);area=sum(cell_area_km2(c) for c in targets)
    assert abs(area-sel['area_km2'])<1e-8
    selections.append(dict(person_id=pid,prediction_seed=seed,hour=hr,arm=arm,cells=cells,target_cells=sorted(targets),area_km2=area,target_res=res,core_cells=sel.get('core_cells'),safety_cells=sel.get('safety_cells')))
    weight=.5 if arm=='best_directional50_res8' else .5 if arm=='personal50_res8' else .7 if arm=='personal70_res8' else .9 if arm=='personal90_res8' else 0 if arm=='stat_only_matched_area' else .3
    mixed=q[hr] if weight==0 else alpha_pool([personal[hr],q[hr]],[weight,1-weight])
    settings.push_target_res=res
    case=Case(id='direction-offline',report=report,lkp=report.lkp,lkp_time=report.lkp_time,current_poa=mixed)
    storage.cases.save(case.id,case);devices.reset();expected={}
    for t in local:
     pos=next(z['position'] for z in t['snapshots'] if z['hour']==hr);cell=h3.latlng_to_cell(pos['lat'],pos['lng'],res);hit=int(cell in targets)
     rows.append(dict(person_id=pid,prediction_seed=seed,truth_seed=t['truth_seed'],future=t['future'],hour=hr,arm=arm,hit=hit,area_km2=area))
     for level in Engagement:
      token=f'direction-{t["truth_seed"]}-{t["future"]}-{level.value}';devices.register(token,Platform.android,cell,level);expected[token]=hit
    captured=[]
    def stub(tokens,**kw):
     captured.extend(tokens);assert set(kw['data']['target_cells'])==targets
     return {'sent':len(tokens),'failed':0,'stub':True,'sent_tokens':tokens,'failed_tokens':[]}
    for d in storage.devices.list():devices.set_location(d,d.location_cell)
    alerts.push.send=stub;alerts.send_alerts(case.id,cells,'synthetic study',poa=mixed)
    assert set(captured)=={k for k,v in expected.items() if v};fanout_checks+=len(expected)
 print(pid,flush=True)
def stats(rs):return dict(checks=len(rs),hits=sum(r['hit'] for r in rs),hit_pct=100*np.mean([r['hit'] for r in rs]),mean_area_km2=np.mean([r['area_km2'] for r in rs]),efficiency_pp_per_km2=100*sum(r['hit'] for r in rs)/sum(r['area_km2'] for r in rs))
summary={'profiles':{},'comparisons':{},'fanout_recipient_checks':fanout_checks,'fanout_mismatches':0,'model_calls':0,'remote_calls':0,'actual_push':0,'query_web_directional_integration':'not enabled; candidate is research selector only, production defaults unchanged'}
for arm in arms:
 r=[z for z in rows if z['arm']==arm];summary['profiles'][arm]={'overall':stats(r),'futures':{f:stats([z for z in r if z['future']==f]) for f in p['futures']}}
def compare(base,future=None):
 a=[z for z in rows if z['arm']=='directional_candidate' and (future is None or z['future']==future)]
 b=[z for z in rows if z['arm']==base and (future is None or z['future']==future)]
 v=np.array([[sum(z['hit'] for z in a if z['person_id']==pid),sum(z['area_km2'] for z in a if z['person_id']==pid),sum(z['hit'] for z in b if z['person_id']==pid),sum(z['area_km2'] for z in b if z['person_id']==pid),sum(z['person_id']==pid for z in a)] for pid in p['people']])
 bt=v[np.random.default_rng(2026101250).integers(0,len(v),(10000,len(v)))].sum(axis=1);pt=v.sum(axis=0)
 def measures(t):return {'hit_pp':100*(t[...,0]-t[...,2])/t[...,4],'efficiency_pp_per_km2':100*t[...,0]/t[...,1]-100*t[...,2]/t[...,3],'area_km2':(t[...,1]-t[...,3])/t[...,4]}
 return {k:{'point':float(x),'ci95':np.quantile(measures(bt)[k],[.025,.975]).tolist()} for k,x in measures(pt).items()}
for base in arms:
 if base=='directional_candidate':continue
 summary['comparisons'][base]={f:compare(base,None if f=='overall' else f) for f in ['overall',*p['futures']]}
key=lambda z:(z['person_id'],z['prediction_seed'],z['truth_seed'],z['hour'],z['future'])
cand={key(z):z for z in rows if z['arm']=='directional_candidate'}
summary['paired_losses']={a:{f:sum(z['hit'] and not cand[key(z)]['hit'] for z in rows if z['arm']==a and z['future']==f) for f in p['futures']} for a in ['preliminary','current']}
gates={'current_targets_preserved100pct':True,'current_hit_losses_zero':all(v==0 for v in summary['paired_losses']['current'].values()),'efficiency_positive_ci_vs_current':summary['comparisons']['current']['overall']['efficiency_pp_per_km2']['ci95'][0]>0,'efficiency_positive_ci_vs_preliminary':summary['comparisons']['preliminary']['overall']['efficiency_pp_per_km2']['ci95'][0]>0,'contrary_positive_ci_vs_current':summary['comparisons']['current']['contradictory']['hit_pp']['ci95'][0]>0,'contrary_positive_ci_vs_preliminary':summary['comparisons']['preliminary']['contradictory']['hit_pp']['ci95'][0]>0,'personal_habitual_effect_vs_stat_only_ci':summary['comparisons']['stat_only_matched_area']['habitual']['hit_pp']['ci95'][0]>0}
summary['decision']={'candidate':p['candidate_selection']['candidate'],'gates':gates,'confirm':all(gates.values()),'production_deployed':False,'fresh_truth_seeds':[2026101251,2026101252,2026101253]}
for name,obj in [('confirmation_rows',rows),('confirmation_selections',selections),('confirmation_summary',summary)]:(O/f'results/{name}.json').write_text(json.dumps(obj,indent=2,default=lambda v:v.item())+'\n')
print(json.dumps(summary,indent=2,default=lambda v:v.item()))

