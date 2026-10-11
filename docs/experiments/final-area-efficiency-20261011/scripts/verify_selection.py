"""Recompute the frozen development-grid decision without private inputs."""
import json
from pathlib import Path
s=json.loads((Path(__file__).resolve().parents[1]/'selection.json').read_text())
p=s['preliminary_native']
feasible=[r for r in s['grid'] if r['hit']>=p['hit'] and r['area_km2']<=p['area_km2']]
best=sorted(feasible,key=lambda r:(-r['efficiency_pp_per_km2'],-r['hit'],r['area_km2'],abs(r['weight']-.7),r['res']))[0]
assert best==s['chosen']
print(json.dumps(best,indent=2))
