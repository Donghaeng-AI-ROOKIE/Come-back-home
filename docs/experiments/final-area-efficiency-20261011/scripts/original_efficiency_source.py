from pathlib import Path
import json,sys,os,hashlib
import numpy as np,h3
R=Path.cwd();X=R/'결선/실험/CHANNEL_ALERT_repair_20261011';O=X/'results_area_efficiency_final';E=R/'결선/실험/EFFICIENCY_KINTEX_v1_20261009'
sys.path.insert(0,str(R/'결선/개발/cbh-independent-alert-core-20261011/backend'));os.environ['PERSIST_STORAGE']='false';sys.path.insert(0,str(E/'area_coverage_curve'));from calculate import ranked_areas,contribution,cell_area
sel=json.loads((O/'selection.json').read_text());meta=json.loads((O/'seen31_summary.json').read_text());native=json.loads((O/'seen31_native_rows.json').read_text());auc=json.loads((O/'seen31_auc_rows.json').read_text());ids=[f'E{i:02d}' for i in range(9,41) if i!=20];w,res,cov=sel['weight'],sel['res'],sel['coverage']
chosen=[r for r in native if r['weight']==w and r['res']==res and r['coverage']==cov]
old=[json.loads(s) for s in (R/'결선/실험/EFFICIENCY_avoid_wait_fix_20261010/service_final/rows.jsonl').read_text().splitlines()];pre=[r for r in old if r['person_id'] in ids and r['arm']=='preliminary'];final=[r for r in old if r['person_id'] in ids and r['arm']=='final']
def eff(rows):return 100*sum(r['hit'] for r in rows)/sum(r['area_km2'] for r in rows)
vectors=np.array([[sum(r['hit'] for r in chosen if r['person_id']==p),sum(r['area_km2'] for r in chosen if r['person_id']==p),sum(r['hit'] for r in pre if r['person_id']==p),sum(r['area_km2'] for r in pre if r['person_id']==p)] for p in ids]);ix=np.random.default_rng(2026101106).integers(0,len(ids),(10000,len(ids)));boot=vectors[ix].sum(axis=1);ce=100*boot[:,0]/boot[:,1];pe=100*boot[:,2]/boot[:,3]
truth={(r['person_id'],s['hour'],r['future']):s['position'] for r in json.loads((E/'truth_private.json').read_text()) for s in r['snapshots']};candidate_common=[r for r in auc if r['weight']==w and r['res']==9];original=[];precommon=[]
for p in ids:
 for seed in (104729,130363):
  data=json.loads((X/f'results_independent_sar/{p}_{seed}.json').read_text())
  before=json.loads((E/f'service_comparison/output/people/{p}/walk_preliminary_{seed}.json').read_text())
  for s,ps in zip(data['snapshots'],before['snapshots']):
   assert s['hour']==ps['hour'];fine_rank={};a=0.
   for c,pr in sorted(ps['cells'].items(),key=lambda t:(-t[1],t[0])):
    if pr<=0:continue
    a+=cell_area(c);fine_rank[c]=a
   mixed={c:w*s['personal'].get(c,0)+(1-w)*s['statistical'].get(c,0) for c in set(s['personal'])|set(s['statistical'])};total=sum(mixed.values());mixed={c:pr/total for c,pr in mixed.items()};new_rank=ranked_areas(mixed);old_rank=ranked_areas(ps['cells'])
   for future in ('habitual','departure','contradictory'):
    pos=truth[p,s['hour'],future];fine=h3.latlng_to_cell(pos['lat'],pos['lng'],9);coarse=h3.latlng_to_cell(pos['lat'],pos['lng'],7);base={'person_id':p,'seed':seed,'hour':s['hour'],'future':future}
    precommon.append(base|{'first_area_km2':fine_rank.get(fine),'auc10':100*contribution(fine_rank.get(fine),10)})
    original.append(base|{'candidate_auc10':100*contribution(new_rank.get(coarse),10),'preliminary_auc10':100*contribution(old_rank.get(coarse),10)})
def budget(rows,b):return float(np.mean([r['first_area_km2'] is not None and r['first_area_km2']<=b for r in rows]))
d=np.array([np.mean([r['candidate_auc10']-r['preliminary_auc10'] for r in original if r['person_id']==p]) for p in ids])
cd=np.array([np.mean([r['auc10'] for r in candidate_common if r['person_id']==p])-np.mean([r['auc10'] for r in precommon if r['person_id']==p]) for p in ids])
result={'status':'fixed_dev_selection_seen31_exploratory','settings':meta['settings'],'selection_sha256':meta['selection_sha256'],'primary_efficiency':{'formula':'100 * sum(hits) / sum(area_km2); ratio of totals, not mean of per-event ratios','unit':'percentage points of synthetic truth inclusion per km2','preliminary':eff(pre),'old_final':eff(final),'selected':eff(chosen),'delta_pp_per_km2':eff(chosen)-eff(pre),'delta_ci95':np.quantile(ce-pe,[.025,.975]).tolist(),'relative_gain_pct':100*(eff(chosen)/eff(pre)-1),'relative_gain_ci95':np.quantile(100*(ce/pe-1),[.025,.975]).tolist(),'cost_is_area_proxy_not_actual_recipients_or_money':True},'common_res9_same_area_budget':{'method':'Same res9 fine-cell ranking and WGS84 areas for both forecast surfaces, no delivery claims for old client','preliminary_auc10':float(np.mean([r['auc10'] for r in precommon])),'selected_auc10':float(np.mean([r['auc10'] for r in candidate_common])),'delta':float(cd.mean()),'delta_ci95':np.quantile(cd[ix].mean(axis=1),[.025,.975]).tolist(),'budgets':[{ 'area_km2':b,'preliminary_inclusion':budget(precommon,b),'selected_inclusion':budget(candidate_common,b)} for b in [1,2,3,5,10,20,30]]},'original_common_res7_auc10':{'preliminary':float(np.mean([r['preliminary_auc10'] for r in original])),'selected':float(np.mean([r['candidate_auc10'] for r in original])),'delta':float(d.mean()),'delta_ci95':np.quantile(d[ix].mean(axis=1),[.025,.975]).tolist()},'native_comparison':{k:meta[k] for k in ['candidate_native','preliminary_native','candidate_minus_preliminary','gates']},'bootstrap':{'people':31,'checks':744,'unit':'person','paired':True,'draws':10000,'seed':2026101106,'confidence':.95},'release_qualification':False,'fresh_holdout':False,'new_model_calls':0}
result['primary_efficiency']['positive_ci']=result['primary_efficiency']['delta_ci95'][0]>0
out=O/'area_efficiency_summary.json';assert not out.exists();out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');(O/'common_res9_rows.json').write_text(json.dumps({'preliminary':precommon,'selected':candidate_common},indent=1)+'\n');print(json.dumps(result,ensure_ascii=False))
