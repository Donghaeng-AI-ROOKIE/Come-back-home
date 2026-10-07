from copy import deepcopy
import pytest
from tests.test_mind_grounded_contract import context,answer
from experiments.mind_grounded.cache import GroundedBudget,MindBudgetExhausted


def test_no_reuse_across_person_state_observation_time_or_history():
    c=context();b=GroundedBudget(1,lambda _:answer(),'candidate-fixed');b.resolve(c)
    variants=[]
    for key,value in [('clock_time','2026-09-28T19:00:00'),('person_revision','corrected')]:
        x=deepcopy(c);x[key]=value;variants.append(x)
    x=deepcopy(c);x['state']['fatigue']=.1;variants.append(x)
    x=deepcopy(c);x['state']['last_rest_end_minutes']=59;variants.append(x)
    x=deepcopy(c);x['environment']['observed_signals']={'market':{'noisy':True}};variants.append(x)
    x=deepcopy(c);x['state']['recent_events']=[{'kind':'orientation_lost'}];variants.append(x)
    for x in variants:
        with pytest.raises(MindBudgetExhausted):b.resolve(x)
    assert b.attempts==1
    cached=b.resolve(c);cached.output['decision']['action']='roam'
    assert b.resolve(c).output['decision']['action']=='rest'


def test_failed_request_spends_budget_without_caching_bad_output():
    bad=answer();bad['state_check']['fatigue_band']='low'
    b=GroundedBudget(1,lambda _:bad,'candidate-fixed')
    with pytest.raises(ValueError):b.resolve(context())
    with pytest.raises(MindBudgetExhausted):b.resolve(context())
    assert not b.cache and b.attempts==1
