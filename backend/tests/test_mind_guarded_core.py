from copy import deepcopy
import json
import pytest
from app.llm import mind_policy_compact as compact
from app.phase0 import mind_preparation as preparation
from app.llm import mind_policy_guarded_core as guarded
from app.config import settings

SOURCE = {'notes':[{'id':'N1','text':'길을 잃었고 가족이 안 보이면 기다렸어요. 제가 데리러 갔어요.'}],
          'places':[{'label':'등록상가'}], 'prepared_initial':{}}


def mixed():
    return {'source_assessment':'대기와 잘못 생성된 이동', 'rules':[
        {'action':'wait','goal_place':'','applies_only_at':[],
         'condition':'lost_awareness and not family_present','hold_minutes':0,'note_ids':['N1']},
        {'action':'seek','goal_place':'','applies_only_at':[],
         'condition':'lost_awareness and not family_present','hold_minutes':0,'note_ids':['N1']}],
        'non_action_note_ids':[]}


def test_partial_recovery_preserves_wait_and_marks_same_note_partial():
    value=mixed();original=deepcopy(value)
    policy,audit=guarded.recover(value,SOURCE)
    assert value==original
    assert [r.action for r in policy.rules]==['wait']
    assert policy.rules[0].id=='a_0'
    assert policy.rules[0].when==compact.compile_d12({**value,'rules':value['rules'][:1]},SOURCE).rules[0].when
    assert [x.note_id for x in policy.unrepresented]==['N1']
    assert audit['quarantined_rule_count']==1 and not audit['semantic_correctness_claimed']


def test_all_invalid_cannot_become_successful_empty_policy():
    value=mixed();value['rules']=value['rules'][1:]
    with pytest.raises(ValueError,match='no usable'):guarded.recover(value,SOURCE)


@pytest.mark.parametrize('change',['unknown_note','unknown_goal','extra_field','unclassified_note'])
def test_invalid_envelope_or_missing_source_fails_closed(change):
    value=mixed();source=deepcopy(SOURCE)
    if change=='unknown_note':value['rules'][1]['note_ids']=['N99']
    if change=='unknown_goal':value['rules'][1]['goal_place']='없는곳'
    if change=='extra_field':value['rules'][1]['execute_anyway']=True
    if change=='unclassified_note':source['notes'].append({'id':'N2','text':'중요한 원문'})
    with pytest.raises((ValueError,TypeError)):guarded.recover(value,source)


def test_invalid_ast_is_not_executed_and_valid_rule_index_is_preserved():
    value=mixed();value['rules'].reverse()
    value['rules'][0]['condition']='__import__("os").system("false")'
    policy,audit=guarded.recover(value,SOURCE)
    assert policy.rules[0].id=='a_1'
    assert audit['quarantined_rules'][0]['rule_index']==0


def test_explicit_walking_guard_is_never_silently_removed():
    source=deepcopy(SOURCE)
    source['notes'][0]['text']='등록상가에서 걷는 중일 때만 시끄러우면 돌아서 나왔어요.'
    value=mixed();value['rules'][0].update(action='avoid_market',applies_only_at=['등록상가'],
        condition='is_walking and market.noisy')
    policy,_=guarded.recover(value,source)
    assert any(a.fact=='is_walking' and a.value is True for a in policy.rules[0].when[0])


def test_valid_registered_seek_survives_an_unrelated_invalid_rule():
    source=deepcopy(SOURCE)
    source['notes'][0]['text']='어머니가 등록상가를 알아보고 그쪽으로 먼저 걸어갔어요.'
    value=mixed();value['rules'][0].update(action='seek',goal_place='등록상가',condition='target_recognized')
    policy,audit=guarded.recover(value,source)
    assert [(r.action,r.goal_label) for r in policy.rules]==[('seek','등록상가')]
    assert audit['quarantined_rule_count']==1


def test_two_failed_outputs_recover_without_third_call_or_false_schema_pass(monkeypatch):
    calls=[]
    monkeypatch.setattr(settings,'mind_policy_contract','guarded_core')
    def invoke(*args,**kwargs):
        calls.append(1)
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(mixed())}}]}
    monkeypatch.setattr(preparation,'logged_json_request',invoke)
    policy,audit=preparation.interpret(SOURCE,'guard-unit')
    assert len(calls)==2 and [x['schema_valid'] for x in audit]==[False,False]
    assert len(policy['rules'])==1 and audit[-1]['recovery']['status']=='partial'


def test_truncated_final_response_cannot_be_salvaged(monkeypatch):
    calls=[]
    monkeypatch.setattr(settings,'mind_policy_contract','guarded_core')
    def invoke(*args,**kwargs):
        calls.append(1)
        return {'choices':[{'finish_reason':'stop' if len(calls)==1 else 'length',
            'message':{'content':json.dumps(mixed())}}]}
    monkeypatch.setattr(preparation,'logged_json_request',invoke)
    with pytest.raises(ValueError,match='incomplete'):preparation.interpret(SOURCE,'guard-unit')
    assert len(calls)==2


def test_valid_first_is_kept_and_not_subject_to_quarantine(monkeypatch):
    value=mixed();value['rules']=value['rules'][:1];calls=[]
    monkeypatch.setattr(settings,'mind_policy_contract','guarded_core')
    def invoke(*args,**kwargs):
        calls.append(1)
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}]}
    monkeypatch.setattr(preparation,'logged_json_request',invoke)
    policy,audit=preparation.interpret(SOURCE,'guard-unit')
    assert len(calls)==1 and audit[0]['schema_valid'] and 'recovery' not in audit[0]
    assert policy['unrepresented']==[]


def test_prompt_preserves_original_source_and_stays_research_only():
    body=guarded.request(SOURCE,'test')
    assert json.loads(body['messages'][1]['content'])['original_notes']==SOURCE['notes']
    assert not guarded.RELEASE_QUALIFIED and body['max_tokens']==16384
