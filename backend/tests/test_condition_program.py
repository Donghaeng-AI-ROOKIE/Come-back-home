"""Handwritten contract fixtures; not a measure of model interpretation quality."""
from copy import deepcopy
import json
import pytest
from app.llm import mind_policy as m
from experiments.mind_policy_candidates import condition_program as c, note_policy_eval as ev


def personal():
    return {'notes':[{'id':'N0','text':'질문: 설명\n답변: 합성 원문 전체'}],
            'places':[{'label':'장소 A'}], 'prepared_initial':{}}


def entry(condition, command='rest', kind='functional_need'):
    return {'kind':kind, 'command':command, 'condition':condition, 'place_labels':[],
            'hold_minutes':0, 'evidence':[{'note_id':'N0','quote':'합성 원문 전체'}]}


@pytest.mark.parametrize('minutes,distance,walking,expected', [
    (0,0,True,False), (5,0,True,True), (0,300,True,True),
    (5,300,True,True), (5,300,False,False), (4.9,299,True,False)])
def test_explicit_common_guard_and_disjunctive_limits(minutes,distance,walking,expected):
    policy=c.compile_entries({'entries':[entry('is_walking and (continuous_walk_minutes >= 5 or distance_since_rest_m >= 300)')]},personal(),'ALL')
    facts={'is_walking':walking,'continuous_walk_minutes':minutes,'distance_since_rest_m':distance}
    assert m.truth(policy.rules[0].when,facts) is expected


@pytest.mark.parametrize('text', ['__import__("os").system("touch /tmp/forbidden")',
    'family_present[0]', '1 + 2', 'clock_hour / 2 > 1', '(lambda: True)()',
    'market.__dict__', 'family_present == "False"', 'continuous_walk_minutes < -1'])
def test_expression_is_not_executable_python(text):
    with pytest.raises(ValueError):c.expression(text)


def test_missing_conditions_remain_unknown_and_not_handles_release():
    clauses=[[m.Atom.model_validate(a) for a in row] for row in c.expression('lost_awareness and not family_present')]
    assert m.truth(clauses,{'lost_awareness':True,'family_present':None}) is None
    assert m.truth(clauses,{'lost_awareness':True,'family_present':True}) is False
    assert m.truth(clauses,{'lost_awareness':True,'family_present':False}) is True


@pytest.mark.parametrize('hour,expected', [(7,False),(8,True),(17.9,True),(18,False)])
def test_reversed_and_chained_numeric_comparisons_preserve_boundaries(hour,expected):
    clauses=[[m.Atom.model_validate(a) for a in row] for row in c.expression('8 <= clock_hour < 18')]
    assert m.truth(clauses,{'clock_hour':hour}) is expected


def test_bad_guard_and_non_behavior_command_rejected_without_repair():
    with pytest.raises(ValueError,match='every branch'):
        c.compile_entries({'entries':[entry('(continuous_walk_minutes >= 5 and distance_since_rest_m >= 300) or is_walking')]},personal(),'ALL')
    with pytest.raises(ValueError,match='non-behavior'):
        c.compile_entries({'entries':[entry('target_recognized','seek_0','stated_goal')]},personal(),'ALL')
    with pytest.raises(ValueError,match='source omitted'):
        c.compile_entries({'entries':[]},personal(),'ALL')


def test_quote_and_named_scope_preserved_without_inferring_words():
    item=entry('market.noisy or market.crowded','avoid_market','observed_response')
    item['place_labels']=['장소 A'];policy=c.compile_entries({'entries':[item]},personal(),'ALL')
    assert policy.rules[0].place_labels==['장소 A']
    item['evidence'][0]['quote']='없는 인용문'
    with pytest.raises(ValueError,match='quote not in'):
        c.compile_entries({'entries':[item]},personal(),'ALL')


def test_typed_initial_condition_reused_without_new_freeform_action():
    p=personal();p['prepared_initial']={'scope':{'environment':{'market':{
        'response':'avoid','scope':'conditional_category','note_ids':['N0'],
        'condition_clauses':[[{'signal':'noisy','state':'present'}],[{'signal':'crowded','state':'present'}]]}}}}
    before=deepcopy(p)
    req=c.request(p,'ALL','offline',whole_person=True)
    payload=json.loads(req['messages'][1]['content'])
    assert payload['prepared_initial']==p['prepared_initial'] and payload['original_notes']==p['notes']
    assert 'avoid_market' in payload['commands'] and p==before
    policy=c.compile_entries({'entries':[]},p,'ALL')
    assert policy.rules==m.fixed_rules(p)
    assert ev.decide(policy,p,{'map_distance_m':{'market':20},'noisy':True,'crowded':False})['commands']==['avoid_market']
    p['prepared_initial']['scope']['environment']['market']['scope']='place_specific'
    assert c.fixed(p)==[]  # Missing place binding must not become category-wide.


@pytest.mark.parametrize('condition', ['is_walking and (continuous_walk_minutes >= 12 or distance_since_rest_m >= 750)', 'is_walking and continuous_walk_minutes >= 12'])
def test_compact_contract_binds_whole_source_and_preserves_formula(condition):
    value={'source_assessment':'손으로 작성한 시험용 해석', 'rules':[{'command':'rest','condition':condition,'place_labels':[], 'hold_minutes':0,'note_ids':['N0']}], 'non_action_note_ids':[]}
    p=personal(); policy=c.compile_note(value,p,'ALL')
    assert policy.rules[0].evidence[0].quote == '합성 원문 전체'
    assert policy.rules[0].when == [[m.Atom.model_validate(x) for x in row] for row in c.expression(condition)]
    value['rules'][0]['condition']='continuous_walk_minutes >= 12'
    with pytest.raises(ValueError,match='every branch'): c.compile_note(value,p,'ALL')


def test_compact_contract_keeps_unsupported_information_without_invented_actions():
    p=personal();value={'source_assessment':'관찰되지 않은 시험 정보', 'rules':[], 'non_action_note_ids':['N0']}
    policy=c.compile_note(value,p,'ALL');assert not policy.rules and len(policy.unrepresented)==1
    value['non_action_note_ids']=[]
    with pytest.raises(ValueError,match='source omitted'):c.compile_note(value,p,'ALL')


def test_json_boolean_spelling_is_equivalent_not_semantic_repair():
    assert c.expression('market.noisy == true or market.crowded == false') == c.expression('market.noisy == True or market.crowded == False')
    assert c.expression('true') == [[]]
    with pytest.raises(ValueError):c.expression('false')


def test_fixed_wire_uses_same_boolean_expression_as_compiler():
    p=personal();p['prepared_initial']={'scope':{'environment':{'market':{'response':'avoid','scope':'conditional_category','note_ids':['N0'],'condition_clauses':[[{'signal':'noisy','state':'present'}],[{'signal':'crowded','state':'present'}]]}}}}
    rule=c.fixed(p)[0];wire=c.fixed_wire(rule)
    assert [[m.Atom.model_validate(a) for a in row] for row in c.expression(wire['condition'])] == rule.when
    assert wire['note_ids']==['N0'] and wire['command']=='avoid_market'
