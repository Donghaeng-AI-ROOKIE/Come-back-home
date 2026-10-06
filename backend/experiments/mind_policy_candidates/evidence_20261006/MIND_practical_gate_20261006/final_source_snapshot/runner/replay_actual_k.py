"""Diagnostic only: consume saved K outputs unchanged on cached KINTEX roads."""
import hashlib,json,statistics,socket,sys
from pathlib import Path

D=Path(__file__).resolve().parent
B=D.parents[1]/'개발/cbh-simulation-integration-20261004/backend'
sys.path.insert(0,str(B))
from app.geo.roadnet import verified_network
from app.llm.mind_policy import Policy
from app.phase2.person_walk import Population
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint
from tests.test_mind_upgrade import person,prior,START
from tests.test_person_policy import obs

def no_network(*a,**kw):raise RuntimeError('no external calls in replay')
socket.socket.connect=no_network
path=D.parent/'MIND_completion_20261004/map_full_support/kintex_walk.graphml'
assert hashlib.sha256(path.read_bytes()).hexdigest()=='953d2bca91fe7388011e9ca161dc576c3c79366c578ed314d7cc8deea677db92'
net=verified_network(path);center=GeoPoint(lat=37.6652142,lng=126.7483258)
source=next(r['personal'] for r in json.loads((D/'development_inputs.json').read_text()) if r['person_id']=='W1_1')
p=person(center)
p.onboarding_turns=[{'question':'합성 보호자 서술','answer':n['text']} for n in source['notes']]
p.behavior_notes=[]
# Only the synthetic registered goal has a coordinate; this is not evidence of
# the real location/route of a patient's named destination.
p.attraction_points=[AttractionPoint(label='다온공원',location=center,place_type='park')]
results=[]
for rep in (1,2):
    policy_path=D/f'development/person_v6_on/W1_1/{rep}/compiled_policy.json'
    policy=Policy.model_validate(json.loads(policy_path.read_text()))
    pop=Population(net,p,prior(),policy,center,START,count=100,seed=17,
        behavior_observations=[obs('lost_awareness',True),obs('family_present',False,0,90),obs('family_present',True,90)])
    snapshots=[];last=None
    for minute in (60,90,120,240,360):
        out=pop.advance_to(minute)
        row={'minute':minute,'mass':sum(out['cells'].values()),'unresolved_mass':out['quality']['unresolved_mass'],
             'mean_wait':statistics.mean(x.waiting for x in pop.particles),
             'mean_rest':statistics.mean(x.rest for x in pop.particles),
             'mean_walk':statistics.mean(x.walking for x in pop.particles),
             'mean_path_km':statistics.mean(x.distance for x in pop.particles)/1000,
             'moved_particles':sum(x.distance>1e-8 for x in pop.particles),
             'change_from_previous_tv':None if last is None else .5*sum(abs(out['cells'].get(k,0)-last.get(k,0)) for k in set(out['cells'])|set(last))}
        snapshots.append(row);last=out['cells'];print({'rep':rep,**row},flush=True)
    results.append({'model_repeat':rep,'source_policy':str(policy_path),'policy_sha256':hashlib.sha256(policy_path.read_bytes()).hexdigest(),
                    'snapshots':snapshots})
output={'kind':'failed_candidate_diagnostic_not_release_validation','synthetic_people':1,'particles_per_repeat':100,
        'source':'actual saved K final output, no rule edits','model_calls':0,'map_calls':0,
        'region':'KINTEX, Goyang','map_metadata':'kintex_map_metadata.json','synthetic_goal_location':True,
        'observations':'authored family arrival at 90 minutes; not patient observations',
        'clinical_accuracy_measured':False,'results':results}
(D/'actual_k_replay.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
