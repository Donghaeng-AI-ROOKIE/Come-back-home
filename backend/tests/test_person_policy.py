"""Mechanics on cached KINTEX; authored policies are not K accuracy evidence."""
import json
from datetime import timedelta
import pytest
from app.llm.mind_policy import Policy,validate,possibilities,source
from app.phase2.person_walk import Population
from app.schemas.environment import BehaviorObservation
from tests.kintex_fixtures import geography,person,prior,START

def rule(action='rest',when=None):
    return dict(id='r1',when=when or [[dict(fact='continuous_walk_minutes',op='gte',value=5),dict(fact='is_walking',op='eq',value=True)]],action=action,goal_label=None,feature=None,place_labels=[],hold_minutes=5 if action=='rest' else None,supersedes=[],evidence=[dict(note_id='N0',quote='무릎이 아프면')])
def policy(*rs):return Policy.model_validate(dict(rules=list(rs),unrepresented=[]))
def obs(fact,value,start=0,end=360):
    return BehaviorObservation(fact=fact,value=value,valid_from=START+timedelta(minutes=start),valid_until=START+timedelta(minutes=end),source='synthetic_scenario')
def population(geography,pol=None,**kw):
    net,center=geography
    return Population(net,person(center),prior(),pol or policy(),center,START,count=kw.pop('count',4),**kw)

def test_exact_quote_and_registered_place_validation():
    src=source(person());p=policy(rule());assert validate(p.model_dump(),src)
    p.rules[0].evidence[0].quote='원문에 없는 주장'
    with pytest.raises(ValueError,match='original answer'):validate(p.model_dump(),src)
def test_unknown_boolean_correlations_do_not_create_impossible_baseline():
    a=rule('wait',when=[[dict(fact='lost_awareness',op='eq',value=True)]])
    b=rule('walk',when=[[dict(fact='lost_awareness',op='eq',value=False)]]);b['id']='r2'
    choices,unknown=possibilities(policy(a,b),{'lost_awareness':None})
    assert {c.action for c in choices}=={'wait','walk'} and unknown==['lost_awareness']
def test_condition_false_vs_unknown():
    a=rule('wait',when=[[dict(fact='lost_awareness',op='eq',value=True)]])
    assert possibilities(policy(a),{'lost_awareness':False})[0]==[None]
    choices,_=possibilities(policy(a),{'lost_awareness':None});assert len(choices)==2 and None in choices

def test_five_minutes_is_walking_not_elapsed_and_rest_resumes(geography):
    p=population(geography,policy(rule()));p.advance_to(12)
    for a in p.particles:
        assert a.walking==pytest.approx(7);assert a.rest==pytest.approx(5)
        assert a.continuous_walk==pytest.approx(2);assert a.distance==pytest.approx(7*p.speed)
def test_family_arrival_ends_the_wait_and_is_not_walked_on(geography):
    # Family beside the person is a reunion: the case lifecycle closes it and
    # the simulation must not walk the person on afterwards (2026-10-10).
    r=rule('wait',when=[[dict(fact='lost_awareness',op='eq',value=True),dict(fact='family_present',op='eq',value=False)]])
    p=population(geography,policy(r),behavior_observations=[obs('lost_awareness',True),obs('family_present',False,0,10),obs('family_present',True,10)])
    p.advance_to(12)
    assert all(a.walking==0 and a.distance==0 for a in p.particles)
    assert all(any(e['kind']=='reunion_observed_no_further_walking' and e['minute']==pytest.approx(10) for e in a.events) for a in p.particles)
def test_expired_observation_becomes_unknown(geography):
    p=population(geography,behavior_observations=[obs('lost_awareness',True,0,10)])
    assert p.facts(p.particles[0])['lost_awareness'] is True
    p.particles[0].minute=10;assert p.facts(p.particles[0])['lost_awareness'] is None
def test_unknown_wait_is_not_universal_standing(geography):
    r=rule('wait',when=[[dict(fact='lost_awareness',op='eq',value=True)]])
    p=population(geography,policy(r),count=40);z=p.advance_to(4)
    assert any(a.waiting>0 for a in p.particles) and any(a.walking>0 for a in p.particles)
    assert z['quality']['uncertain_time_fraction']==pytest.approx(1)
    assert sum(z['cells'].values())==pytest.approx(1)
def test_save_restore_matches_single_run(geography):
    pol=policy(rule());whole=population(geography,pol);split=population(geography,pol)
    a=whole.advance_to(62);split.advance_to(60)
    restored=population(geography,pol,checkpoint=json.loads(json.dumps(split.checkpoint())))
    b=restored.advance_to(62);assert a==b
    for x,y in zip(whole.particles,restored.particles):
        assert x.node==y.node and x.edge_to==y.edge_to;assert x.distance==pytest.approx(y.distance);assert x.rng_state==y.rng_state

def test_physical_arrival_does_not_imply_recognition(geography):
    p=population(geography,behavior_observations=[obs('target_recognized',False)])
    for a in p.particles:a.target='등록 목적지'
    p.advance_to(.5)
    assert all(any(e['kind']=='physical_arrival' for e in a.events) for a in p.particles)
    assert all(a.walking==pytest.approx(.5) for a in p.particles)
def test_map_boundary_mass_is_preserved(geography):
    p=population(geography);p.particles[0].blocked=True;z=p.advance_to(1)
    assert z['quality']['unresolved_mass']==.25;assert sum(z['cells'].values())==pytest.approx(.75)
def test_version_stale_checkpoint_fails(geography):
    p=population(geography);ck=p.checkpoint();ck['version']='old'
    with pytest.raises(ValueError,match='stale'):population(geography,checkpoint=ck)
def test_invalid_or_conflicting_observation(geography):
    with pytest.raises(ValueError):obs('lost_awareness',True,10,1)
    p=population(geography,behavior_observations=[obs('lost_awareness',True),obs('lost_awareness',False)])
    assert p.facts(p.particles[0])['lost_awareness'] is None

def test_short_yes_answer_is_interpreted_with_its_question():
    p=person();p.onboarding_turns=[{'slot':'lost','question':'길 잃음을 알면 가족이 올 때까지 기다리나요?','answer':'네'}]
    src=source(p)
    assert '가족이 올 때까지' in src['notes'][0]['text']
    r=rule('wait',when=[[dict(fact='lost_awareness',op='eq',value=True),dict(fact='family_present',op='eq',value=False)]])
    r['evidence']=[dict(note_id=src['notes'][0]['id'],quote='네')]
    assert validate(policy(r).model_dump(),src)

def test_note_id_copies_source_without_model_requoting():
    src=source(person());r=rule();r['evidence']=[{'note_id':'N0'}]
    out=validate(policy(r).model_dump(),src)
    assert out.rules[0].evidence[0].quote=='무릎이 아프면 앉아서 쉬고 다시 걸어요.'

def test_prepared_environment_and_or_preserved_without_reinterpretation():
    from app.llm.mind_policy import fixed_rules,add_fixed
    src=source(person());src['prepared_initial']['scope']={'environment':{'market':{
        'response':'avoid','scope':'conditional_category','note_ids':['N0'],
        'condition_clauses':[[{'signal':'noisy','state':'present'}],[{'signal':'crowded','state':'present'}]]}}}
    p=add_fixed(policy(),src)
    assert p.rules[0].feature=='market' and p.rules[0].place_labels==[]
    assert len(p.rules[0].when)==2
    assert possibilities(p,{'market.noisy':False,'market.crowded':True},near_features=['market'])[0][0].action=='avoid'

def test_unmapped_environment_is_unknown_not_confirmed_absence():
    r=rule('avoid',when=[[]]);r.update(feature='market')
    options,unknown=possibilities(policy(r),{},near_features=None)
    assert {x.action if x else None for x in options}=={'avoid',None}
    assert unknown==['spatial_scope:feature:market']
    assert possibilities(policy(r),{},near_features=[])[0]==[None]

def test_named_place_does_not_require_a_second_category_layer():
    r=rule('avoid',when=[[]]);r.update(feature='market',place_labels=['등록 목적지'])
    options,_=possibilities(policy(r),{},near_places=['등록 목적지'],near_features=None)
    assert [x.action for x in options]==['avoid']
