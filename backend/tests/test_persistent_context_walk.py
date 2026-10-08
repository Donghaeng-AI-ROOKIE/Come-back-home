"""KINTEX regressions: persistent unknowns and sourced waiting episodes."""
import json
import random
from copy import deepcopy
import pytest
from app.phase2.person_walk import Population, BaselineRestPolicy
from app.phase2.persistent_context_walk import PersistentContextPopulation
from tests.test_place_bound_walk import cached, make, recognition
from tests.test_person_policy import rule, policy, obs

def create(cached, pol, **kw):
    return make(cached, cls=PersistentContextPopulation, pol=pol,
                rest_policy=BaselineRestPolicy(enabled=False), **kw)

def waiting(duration=None, fact='lost_awareness'):
    r=rule('wait',when=[[dict(fact=fact,op='eq',value=True)]])
    r['id']='waiting';r['hold_minutes']=duration
    return r

def test_rest_cycle_does_not_resample_same_unknown_wait(cached):
    rest=rule();rest['id']='rest'
    pop=create(cached,policy(waiting(),rest))
    pop.advance_to(1)
    waiting_seeds={p.seed for p in pop.particles if p.mode=='wait'}
    states=[deepcopy(p.context_assumptions) for p in pop.particles]
    pop.advance_to(60)
    assert {p.seed for p in pop.particles if p.mode=='wait'}==waiting_seeds
    assert [p.context_assumptions for p in pop.particles]==states
    assert any(p.walking>0 and p.rest>0 for p in pop.particles)
    assert all(pop.facts(p)['lost_awareness'] is None for p in pop.particles)

def test_unrelated_target_does_not_resample_global_unknown(cached):
    pop=create(cached,policy(waiting()))
    p=pop.particles[0];rng=random.Random(17);choices=[]
    for target in ['A','B',None]*10:
        p.target=target
        r,_,_=pop._select_rule(p,rng,pop.facts(p),*pop.near(p))
        choices.append(r.id if r else None)
    assert len(set(choices))==1
    assert p.context_assumptions['global:lost_awareness']['generation']==0

def test_known_fact_overrides_hypothesis_and_expiry_is_new_unknown(cached):
    pop=create(cached,policy(waiting()),behavior_observations=[obs('lost_awareness',True,1,2)])
    p=pop.particles[0];rng=random.Random(17)
    pop._select_rule(p,rng,pop.facts(p),*pop.near(p))
    p.minute=1
    r,_,_=pop._select_rule(p,rng,pop.facts(p),*pop.near(p))
    assert r.id=='waiting' and p.context_assumptions['global:lost_awareness']['state']=='known'
    p.minute=2
    pop._select_rule(p,rng,pop.facts(p),*pop.near(p))
    assert pop.facts(p)['lost_awareness'] is None
    assert p.context_assumptions['global:lost_awareness']['generation']==1
    before=deepcopy(p.context_assumptions)
    pop._select_rule(p,rng,pop.facts(p),*pop.near(p))
    assert p.context_assumptions==before

@pytest.mark.parametrize('minutes',[3.5,10.])
def test_sourced_wait_ends_once_not_extended_each_step(cached,minutes):
    pop=create(cached,policy(waiting(minutes)),behavior_observations=[obs('lost_awareness',True)])
    pop.advance_to(minutes+2)
    for p in pop.particles:
        assert p.waiting==pytest.approx(minutes)
        assert p.walking==pytest.approx(2)
        assert p.completed_waits==['waiting']

def test_new_condition_episode_rearms_completed_wait(cached):
    pop=create(cached,policy(waiting(2)),behavior_observations=[
        obs('lost_awareness',True,0,3),obs('lost_awareness',False,3,4),obs('lost_awareness',True,4,10)])
    pop.advance_to(8)
    assert all(p.waiting==pytest.approx(4) and p.walking==pytest.approx(4) for p in pop.particles)

def test_walking_trigger_does_not_cancel_sourced_wait_on_next_tick(cached):
    r=waiting(3.5,'is_walking')
    pop=create(cached,policy(r));pop.advance_to(3.5)
    assert all(p.waiting==pytest.approx(3.5) for p in pop.particles)

def test_external_condition_false_releases_before_deadline(cached):
    pop=create(cached,policy(waiting(10)),behavior_observations=[
        obs('lost_awareness',True,0,.25),obs('lost_awareness',False,.25,20)])
    pop.advance_to(2)
    assert all(p.waiting==pytest.approx(.25) and p.walking==pytest.approx(1.75) for p in pop.particles)

def test_unspecified_duration_is_not_an_invented_restart(cached):
    pop=create(cached,policy(waiting()),behavior_observations=[obs('lost_awareness',True)])
    result=pop.advance_to(65)
    assert all(p.waiting==pytest.approx(65) and p.walking==0 for p in pop.particles)
    assert result['quality']['unreported_wait_duration'].startswith('not_inferred')
    assert result['quality']['conflicting_action_tie']=='legacy_when_known; stable_hash_when_unknown; not_clinical_priority'

def test_correlated_opposite_conditions_remain_consistent(cached):
    wait=waiting()
    walk=rule('walk',when=[[dict(fact='lost_awareness',op='eq',value=False)]]);walk['id']='walk'
    pop=create(cached,policy(wait,walk))
    p=pop.particles[0];r,_,_=pop._select_rule(p,random.Random(17),pop.facts(p),*pop.near(p))
    assumption=p.context_assumptions['global:lost_awareness']['value']
    assert r.action==('wait' if assumption else 'walk')

def test_same_snapshot_whole_vs_fractional_restore(cached):
    pol=policy(waiting(3.5))
    kw={'behavior_observations':[obs('lost_awareness',True)]}
    whole=create(cached,pol,**kw);split=create(cached,pol,**kw)
    expected=whole.advance_to(15)
    for t in (.25,1,3.5,7):
        split.advance_to(t)
        split=create(cached,pol,checkpoint=json.loads(json.dumps(split.checkpoint())),**kw)
    assert split.advance_to(15)==expected
    assert split.checkpoint()==whole.checkpoint()

def test_unknown_hypotheses_survive_checkpoint(cached):
    pol=policy(waiting(),rule())
    whole=create(cached,pol);split=create(cached,pol)
    expected=whole.advance_to(30);split.advance_to(6)
    split=create(cached,pol,checkpoint=json.loads(json.dumps(split.checkpoint())))
    assert split.advance_to(30)==expected
    assert split.checkpoint()==whole.checkpoint()

def test_changed_assumption_or_executor_cannot_reuse_snapshot(cached):
    pop=create(cached,policy(waiting()));pop.advance_to(1)
    ck=pop.checkpoint()
    with pytest.raises(ValueError,match='assumptions changed'):
        create(cached,policy(waiting()),checkpoint=ck,unknown_true_weights={'lost_awareness':.1})
    with pytest.raises(ValueError,match='executor changed'):
        make(cached,cls=Population,pol=policy(waiting()),checkpoint=ck,rest_policy=BaselineRestPolicy(enabled=False))

def test_recognition_is_bound_to_named_place(cached):
    r=waiting(fact='target_recognized');r['place_labels']=['A']
    pop=create(cached,policy(r),place_recognitions=[recognition('A',False),recognition('B',True)])
    p=pop.particles[0];p.target='B'
    chosen,_,_=pop._select_rule(p,random.Random(17),pop.facts(p),*pop.near(p))
    assert chosen is None

def test_distinct_place_noise_assumptions_do_not_alias(cached):
    a=rule('avoid',when=[[dict(fact='market.noisy',op='eq',value=True)]])
    a.update(id='a',feature='market',place_labels=['A'])
    b=deepcopy(a);b.update(id='b',place_labels=['B'])
    pop=create(cached,policy(a,b));p=pop.particles[0];rng=random.Random(17)
    for label in ['A','B','A']:
        p.node=pop.goals[label]
        pop._select_rule(p,rng,pop.facts(p),*pop.near(p))
    keys=[k for k in p.context_assumptions if 'market.noisy' in k]
    assert len(keys)==2 and any('"A"' in k for k in keys) and any('"B"' in k for k in keys)
    assert all(pop.facts(p)[key] is None for key in ['market.noisy'])

def test_invalid_weights_rejected(cached):
    with pytest.raises(ValueError,match='uncertainty'):
        create(cached,policy(waiting()),unknown_true_weights={'lost_awareness':float('nan')})

def test_fully_known_competing_actions_preserve_original_choice(cached):
    rest=rule('rest',when=[[]]);rest['id']='rest'
    avoid=rule('avoid',when=[[]]);avoid.update(id='avoid',feature='market',place_labels=['A'])
    pol=policy(rest,avoid)
    old=make(cached,cls=Population,pol=pol,rest_policy=BaselineRestPolicy(enabled=False))
    new=create(cached,pol)
    for a,b in zip(old.particles,new.particles):
        ra,rb=random.Random(a.seed),random.Random(b.seed)
        for minute in (0,1,6,7,12):
            a.minute=b.minute=minute
            x=old._select_rule(a,ra,old.facts(a),*old.near(a))
            y=new._select_rule(b,rb,new.facts(b),*new.near(b))
            assert x==y and ra.getstate()==rb.getstate()

def test_wait_duration_end_does_not_invent_an_unsourced_followup_walk(cached):
    pop=create(cached,policy(waiting(2)),behavior_observations=[obs('lost_awareness',True)])
    for p in pop.particles:
        p.strategy='staying_put'
    pop.advance_to(4)
    assert all(p.rule_minutes['waiting']==pytest.approx(2) for p in pop.particles)
    assert all(p.last_baseline and p.walking==0 for p in pop.particles)
