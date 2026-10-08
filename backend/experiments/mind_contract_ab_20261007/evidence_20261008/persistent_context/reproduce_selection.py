"""Regression of uncertainty mechanics, not a clinical behavior accuracy test."""
import random
from collections import Counter
from pathlib import Path
import json

from app.llm.mind_policy import Policy
from app.phase2.person_walk import Population, Particle

def run(executor='legacy'):
    # No road: isolate the decision selector from movement and the model.
    cls=Population
    if executor=='persistent':
        from app.phase2.persistent_context_walk import PersistentContextPopulation
        cls=PersistentContextPopulation
    pop=object.__new__(cls)
    from datetime import datetime
    pop.started_at=datetime(2026,10,8)
    pop.place_recognitions=[];pop.unknown_true_weights={};pop.goals={}
    pop.policy=Policy.model_validate({'rules':[
        dict(id='wait',when=[[dict(fact='lost_awareness',op='eq',value=True)]],
             action='wait',goal_label=None,feature=None,place_labels=[],hold_minutes=None,
             supersedes=[],evidence=[dict(note_id='N0')]),
        dict(id='rest',when=[[dict(fact='is_walking',op='eq',value=True),
                             dict(fact='continuous_walk_minutes',op='gte',value=6)]],
             action='rest',goal_label=None,feature=None,place_labels=[],hold_minutes=5,
             supersedes=[],evidence=[dict(note_id='N1')])
    ],'unrepresented':[]})
    pop._policy_cache={}
    pop.facts=lambda p: {'lost_awareness':None,'is_walking':p.mode=='walk',
                        'continuous_walk_minutes':p.continuous_walk}
    pop.near=lambda p:([],{})
    pop._population_rest=lambda p:False
    parts=[Particle(0,i,strategy='random_walk') for i in range(500)]
    rngs=[random.Random(i) for i in range(500)]
    timeline=[]
    first_wait={}
    for minute in range(120):
        for p,rng in zip(parts,rngs):
            p.minute=minute
            pop._decide(p,rng)
            if p.mode=='wait':
                first_wait.setdefault(p.seed,minute)
            if p.mode=='walk':p.continuous_walk+=1
        if minute in (0,5,10,20,59,119):
            timeline.append({'minute':minute,'modes':dict(Counter(p.mode for p in parts))})
    return {'scope':'decision-only, no geography or patient model',
            'unknown_lost_awareness_never_changes':True,
            'first_wait_minute_counts':dict(Counter(first_wait.values())),
            'timeline':timeline}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--executor',choices=('legacy','persistent'),default='legacy')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise SystemExit('refuse overwrite')
    result=run(args.executor)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
