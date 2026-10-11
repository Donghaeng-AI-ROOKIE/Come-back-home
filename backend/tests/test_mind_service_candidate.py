"""Service contract and source-bound continuation; synthetic, not clinical labels."""
from copy import deepcopy
import json
import pytest
from app.llm import mind_policy as m, mind_policy_candidate as c, mind_policy_compact as base
from app.phase0 import mind_preparation
from app.config import settings

ANSWER = '길을 잃었다는 걸 알면 십 분 기다린 뒤 다시 걸었어요.'

def source(answer=ANSWER):
    return {'notes': [{'id': 'N1', 'text': '질문: 길을 잃었다고 느낄 때 어떻게 하셨나요?\n답변: '+answer}],
            'places': [{'label': '등록공원'}], 'prepared_initial': {}}


def output(follow=True):
    return {'source_assessment': '명시된 대기와 뒤이은 이동 관찰',
        'rules': [{'action': 'wait', 'goal_place': '', 'applies_only_at': [],
                   'condition': 'lost_awareness', 'hold_minutes': 10, 'note_ids': ['N1'],
                   'after_wait': [{'action': 'walk', 'goal_place': '', 'note_id': 'N1', 'quote': ANSWER}] if follow else []}],
        'non_action_note_ids': []}


def test_source_bound_wait_and_continuation_compile():
    policy=c.compile(output(),source());r=policy.rules[0]
    assert r.hold_minutes == 10 and r.after_wait.action == 'walk'
    assert r.after_wait.evidence[0].quote == ANSWER


def test_finite_wait_entry_guard_is_new_candidate_only():
    x=output();x['rules'][0]['condition']='is_walking and lost_awareness'
    assert c.compile(x,source()).rules[0].hold_minutes==10
    old=deepcopy(x);old['rules'][0].pop('after_wait')
    with pytest.raises(ValueError,match='waiting must remain'):
        base.compile_d12(old,source())


def test_unspecified_wait_duration_cannot_use_self_cancelling_walking_guard():
    x=output(False);x['rules'][0].update(condition='is_walking and lost_awareness',hold_minutes=0)
    with pytest.raises(ValueError,match='waiting must remain'):
        c.compile(x,source())


@pytest.mark.parametrize('change', ['no_duration','not_wait','invented_quote','invented_goal','walk_with_goal','extra_followup','wrong_note'])
def test_invalid_continuation_is_rejected(change):
    x=output();r=x['rules'][0];f=r['after_wait'][0]
    if change=='no_duration': r['hold_minutes']=0
    if change=='not_wait':r.update(action='rest',condition='is_walking and continuous_walk_minutes >= 10')
    if change=='invented_quote':f['quote']='없는 관찰'
    if change=='invented_goal':f.update(action='seek',goal_place='없는장소')
    if change=='walk_with_goal':f['goal_place']='등록공원'
    if change=='extra_followup':r['after_wait'].append(deepcopy(f))
    if change=='wrong_note':f['note_id']='N2'
    with pytest.raises(ValueError):c.compile(x,source())


def test_absent_continuation_is_not_filled_from_population_prior():
    assert c.compile(output(False),source()).rules[0].after_wait is None


@pytest.mark.parametrize('condition', ['__import__("os").system("echo bad")', 'clock_hour >= 23 and clock_hour < 1', 'lost_awareness and not lost_awareness'])
def test_unsafe_or_impossible_conditions_rejected(condition):
    x=output(False);x['rules'][0]['condition']=condition
    with pytest.raises(ValueError):c.compile(x,source())


def test_service_request_has_same_compact_base_plus_explicit_extension():
    old=base.request(source(),'test');new=c.request(source(),'test')
    assert new['messages'][0]['content'].startswith(base.SYSTEM_A)
    assert '대기 조건에 is_walking을 넣으면' in old['messages'][0]['content']
    assert '대기 조건에 is_walking을 넣으면' not in new['messages'][0]['content']
    assert '시간을 모르는 대기에는 is_walking을 넣지 않는다' in new['messages'][0]['content']
    assert new['temperature']==old['temperature']==1.
    assert new['max_tokens']==16384
    assert new['response_format']['type']=='json_schema'
    assert 'after_wait' in new['response_format']['json_schema']['schema']['properties']['rules']['items']['properties']
    assert '실종 사건이 종결' in new['messages'][0]['content']


def test_interpret_uses_new_contract_for_both_calls(monkeypatch):
    bodies=[]
    def request(url,body,**kwargs):
        bodies.append(body)
        assert kwargs['max_started']==2
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(output(),ensure_ascii=False)}}]}
    monkeypatch.setattr(mind_preparation,'logged_json_request',request)
    policy,audit=mind_preparation.interpret(source(),'synthetic-unit')
    assert len(bodies)==2 and all(a['schema_valid'] for a in audit)
    assert 'draft_to_review' in json.loads(bodies[1]['messages'][1]['content'])
    assert policy['rules'][0]['after_wait']['action']=='walk'


def test_production_cannot_enable_research_by_having_an_api_key(monkeypatch):
    monkeypatch.setattr(m,'RELEASE_QUALIFIED',False)
    monkeypatch.setattr(settings,'mind_policy_deployment','production')
    assert not mind_preparation.enabled()
    monkeypatch.setattr(settings,'mind_policy_deployment','staging')
    assert mind_preparation.enabled()
