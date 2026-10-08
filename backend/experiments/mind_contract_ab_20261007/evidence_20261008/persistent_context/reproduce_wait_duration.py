from pathlib import Path
import json,sys,random
from datetime import datetime
base=Path(sys.argv[1]);kind=sys.argv[2];sys.path.insert(0,str(base))
from app.phase2.person_walk import Population,Particle
from app.llm.mind_policy import Policy
if kind=='persistent':
 from app.phase2.persistent_context_walk import PersistentContextPopulation as Population
pop=object.__new__(Population)
pop.policy=Policy.model_validate({'rules':[dict(id='wait',when=[[dict(fact='lost_awareness',op='eq',value=True)]],action='wait',goal_label=None,feature=None,place_labels=[],hold_minutes=10,supersedes=[],evidence=[dict(note_id='N0')])],'unrepresented':[]})
pop._policy_cache={};pop.started_at=datetime(2026,10,8);pop.place_recognitions=[];pop.unknown_true_weights={};pop.goals={}
pop.facts=lambda p:{'lost_awareness':True,'is_walking':p.mode=='walk','continuous_walk_minutes':p.continuous_walk,'distance_since_rest_m':p.distance_since_rest}
pop.near=lambda p:([],{});pop._population_rest=lambda p:False
p=Particle(0,17,strategy='random_walk');rng=random.Random(17);counts={'wait':0,'walk':0}
deadlines=[]
for minute in range(12):
 p.minute=minute;pop._decide(p,rng);counts[p.mode]+=1
 deadlines.append(p.hold_until)
print(json.dumps({'scope':'decision-only; no geography','executor':kind,'minutes':12,'counts':counts,'deadlines':deadlines}))
