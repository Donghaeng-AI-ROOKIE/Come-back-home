from pathlib import Path
import json,numpy as np
O=Path(__file__).resolve().parents[1];R=O.parents[2]
s=json.loads((O/'results/confirmation_summary.json').read_text());rows=json.loads((O/'results/confirmation_rows.json').read_text());families={v['person_id']:v['family'] for v in json.loads((R/'결선/실험/EFFICIENCY_KINTEX_v1_20261009/inputs.json').read_text())};result={}
for family in sorted(set(families.values())):
 result[family]={}
 for arm in s['profiles']:
  result[family][arm]={}
  for future in ['habitual','departure','contradictory']:
   local=[z for z in rows if z['arm']==arm and z['future']==future and families[z['person_id']]==family];result[family][arm][future]={'checks':len(local),'hits':sum(z['hit'] for z in local),'pct':100*sum(z['hit'] for z in local)/len(local)}
gates={family:result[family]['candidate']['habitual']['pct']>=result[family]['current']['habitual']['pct'] for family in result}
(O/'results/family_subgroups.json').write_text(json.dumps({'groups':result,'habitual_family_point_gates':gates,'all_families_habitual_preserved':all(gates.values())},indent=2)+'\n')
print({family:{arm:result[family][arm]['habitual']['pct'] for arm in s['profiles']} for family in result});print(gates)
