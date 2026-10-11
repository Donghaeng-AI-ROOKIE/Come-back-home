from pathlib import Path
import json
from pyproj import Geod
O=Path(__file__).resolve().parents[1];truth=json.loads((O/'truth_private.json').read_text());g=Geod(ellps='WGS84');bad=[];ratios=[]
for row in truth:
 for a,b in zip(row['path'],row['path'][1:]):
  dist=g.inv(a['lng'],a['lat'],b['lng'],b['lat'])[2];cap=(b['minute']-a['minute'])*row['assumptions']['speed_m_min'];ratios.append(dist/cap)
  if dist>cap*1.03:bad.append({'person_id':row['person_id'],'truth_seed':row['truth_seed'],'future':row['future'],'minute':b['minute'],'distance_m':dist,'speed_budget_m':cap})
v={'segments':len(ratios),'max_geodesic_displacement_over_walk_budget':max(ratios),'violations_above_3pct_projection_tolerance':len(bad),'violations':bad};(O/'results/truth_physics_audit.json').write_text(json.dumps(v,indent=2)+'\n');print(v);assert not bad
