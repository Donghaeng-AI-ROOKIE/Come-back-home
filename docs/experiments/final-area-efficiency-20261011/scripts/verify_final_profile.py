"""Final default pooling / target geography parity; saved verified channels only."""
from pathlib import Path
import sys,os,socket,json
R=Path(sys.argv[1]).resolve();C=Path(sys.argv[2]).resolve();X=R/'결선/실험/CHANNEL_ALERT_repair_20261011';D=C/'docs/experiments/final-area-efficiency-20261011'
os.environ['PERSIST_STORAGE']='false'
for k in ('PUSH_TARGET_RES','PERSONAL_CHANNEL_WEIGHT','ALERT_COVERAGE'):os.environ.pop(k,None)
def blocked(*a,**k):raise RuntimeError('Network disabled for saved-channel verification')
socket.socket.connect=blocked;socket.create_connection=blocked;sys.path.insert(0,str(C/'backend'))
from app.config import settings
from app.phase2.combine import alpha_pool
from app.phase3.alerts import select_alert_cells,target_parent_cells
from app.geo.h3cover import overlapping_cells
from shapely.geometry import Polygon
from pyproj import Geod
import h3
assert (settings.personal_channel_weight,settings.push_target_res,settings.alert_coverage)==(.9,9,.95)
sel=json.loads((D/'selection.json').read_text());assert (sel['weight'],sel['res'],sel['coverage'])==(.9,9,.95)
expected=json.loads((X/'results_area_efficiency_final/seen31_native_rows.json').read_text());rows=[];g=Geod(ellps='WGS84')
for s in json.loads((X/'results_independent_sar/E09_104729.json').read_text())['snapshots']:
 mixed=alpha_pool([s['personal'],s['statistical']],[settings.personal_channel_weight,1-settings.personal_channel_weight],mode='linear');chosen=select_alert_cells(mixed);targets=target_parent_cells(chosen)
 assert all(overlapping_cells(c,9)<=targets for c in chosen)
 area=sum(abs(g.geometry_area_perimeter(Polygon([(lon,lat) for lat,lon in h3.cell_to_boundary(c)]))[0])/1e6 for c in targets)
 e=next(r for r in expected if r['person_id']=='E09' and r['seed']==104729 and r['hour']==s['hour'] and r['weight']==.9 and r['res']==9 and r['coverage']==.95)
 assert abs(area-e['area_km2'])<1e-10
 rows.append({'hour':s['hour'],'selected_mass':sum(mixed[c] for c in chosen),'selected_count':len(chosen),'target_count':len(targets),'area_km2':area,'saved_score_area_delta':area-e['area_km2'],'all_selected_cells_geographically_covered':True})
out={'settings':{'personal_weight':.9,'target_res':9,'coverage':.95},'saved_channel_executor_proof':'channel_executor_verification.json','does_not_rerun_models_or_reestimate_channels':True,'new_model_calls':0,'new_map_calls':0,'new_push_calls':0,'rows':rows};(D/'final_profile_verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
