"""Mechanical tests with authored outputs; not live model performance."""
import copy
import json
import pytest
from app.llm import mind_policy as m
from experiments.mind_policy_candidates import note_policy as n, note_policy_eval as ev


def personal():
    return {'notes': [{'id': 'N0', 'text': '여덟 분 전에는 걷고 여덟 분부터 쉬어요.'},
                      {'id': 'N1', 'text': '앞 답변은 제 이야기예요. 어머니는 달라요.'}],
            'places': [{'label': '공원 A'}], 'prepared_initial': {}}


def rule(action, fact='continuous_walk_minutes', op='gte', value=8, **kwargs):
    return {'action': action, 'when': [[{'fact': fact, 'op': op, 'value': value}]],
            'goal_label': None, 'feature': None, 'place_labels': [],
            'hold_minutes': None, 'note_ids': ['N0'], **kwargs}


def compiled(*rules):
    return n.compile_note({'rules': list(rules), 'unrepresented_reason': ''}, personal(), 'N0')


def test_source_is_preserved_with_corrections_and_without_scene_or_labels():
    p = personal(); before = copy.deepcopy(p)
    req = n.request(p, 'N0', 'offline')
    data = json.loads(req['messages'][1]['content'])
    assert data['all_original_notes'] == p['notes']
    assert data['focus_note_id'] == 'N0'
    assert set(data) == {'focus_note_id', 'all_original_notes', 'registered_places', 'boolean_facts', 'numeric_facts','commands'}
    assert p == before and not n.RELEASE_QUALIFIED
    with pytest.raises(ValueError, match='input byte cap'):
        n.request({**p, 'notes': [{'id':'N0', 'text':'긴 원문'*20000}]}, 'N0', 'offline')


@pytest.mark.parametrize('value,expected', [(7.9,'walk'), (8.,'rest'), (8.1,'rest')])
def test_strict_boundary_has_one_action_without_rounding(value, expected):
    policy = compiled(rule('walk', op='lt'), rule('rest'))
    result = ev.decide(policy, personal(), {'continuous_walk_minutes': value})
    assert result['commands'] == [expected]
    assert result['possible_commands'] == [expected]


@pytest.mark.parametrize('value', [7.99,8.,8.01])
def test_upper_and_lower_bounds_partition_numeric_domain(value):
    lt = m.Atom(fact='continuous_walk_minutes', op='lt', value=8)
    ge = m.Atom(fact='continuous_walk_minutes', op='gte', value=8)
    gt = m.Atom(fact='continuous_walk_minutes', op='gt', value=8)
    le = m.Atom(fact='continuous_walk_minutes', op='lte', value=8)
    facts = {'continuous_walk_minutes': value}
    assert m.atom_value(lt, facts) != m.atom_value(ge, facts)
    assert m.atom_value(gt, facts) != m.atom_value(le, facts)


def test_unknown_retains_alternatives_without_selecting_an_expected_answer():
    policy = compiled(rule('walk', op='lt'), rule('rest'))
    decision = ev.decide(policy, personal(), {})
    assert decision['status'] == 'unknown'
    assert set(decision['possible_commands']) == {'walk','rest'}
    assert not ev.score(decision, ['rest'])
    assert ev.score(decision, [])


def test_wait_release_is_executed_as_supplied_not_inferred_from_words():
    policy = compiled(rule('wait', fact='family_present', op='eq', value=False))
    assert ev.decide(policy, personal(), {'family_present':False})['commands'] == ['wait']
    assert ev.decide(policy, personal(), {'family_present':True})['commands'] == ['baseline']


def test_wire_literals_preserve_boolean_false_and_numeric_boundary():
    r=rule('wait',fact='family_present',op='eq',value='false',goal_label='',feature='',hold_minutes=0)
    before=copy.deepcopy(r)
    p=compiled(r)
    assert p.rules[0].when[0][0].value is False
    assert p.rules[0].hold_minutes is None and p.rules[0].goal_label is None
    assert r==before
    p=compiled(rule('rest',value='8.5',goal_label='',feature='',hold_minutes=0))
    assert p.rules[0].when[0][0].value==8.5
    with pytest.raises(ValueError):
        compiled(rule('wait',fact='family_present',op='eq',value='yes'))
    with pytest.raises(ValueError):
        compiled(rule('wait',fact='family_present',op='eq',value='0'))


def test_no_partial_policy_or_unrelated_evidence_is_accepted():
    with pytest.raises(ValueError, match='missing or extra'):
        n.merge({'N0': {'rules':[], 'unrepresented_reason':'관찰 없음'}}, personal())
    with pytest.raises(ValueError, match='focus note'):
        compiled(rule('rest', note_ids=['N1']))
    with pytest.raises(ValueError, match='invented place'):
        compiled(rule('seek', goal_label='없는 장소'))
    with pytest.raises(ValueError, match='empty extraction'):
        n.compile_note({'rules':[], 'unrepresented_reason':''}, personal(), 'N0')


def test_whole_person_command_keeps_grounded_scope_and_rejects_invented_source():
    value={'source_summary':'합성 요약이며 실행 근거는 원문 ID다.',
           'rules':[{'command':'avoid_market','when':[[{'fact':'market.noisy','op':'eq','value':'true'}]],
                     'place_labels':['공원 A'],'hold_minutes':0,'note_ids':['N1']}],
           'unrepresented_reason':'N0 내용은 실행 행동으로 표현하지 않음'}
    policy=n.compile_note(value,personal(),'ALL',whole_person=True)
    assert policy.rules[0].feature=='market' and policy.rules[0].goal_label is None
    assert policy.rules[0].place_labels==['공원 A']
    assert policy.rules[0].evidence[0].note_id=='N1'
    assert 'source_summary' not in policy.model_dump()
    value['rules'][0]['note_ids']=['N99']
    with pytest.raises(ValueError,match='unknown evidence'):
        n.compile_note(value,personal(),'ALL',whole_person=True)


def test_no_partial_denominator_and_failures_count_against_ninety_percent():
    rows = [{'id':str(i), 'rep':1, 'pass':i<9, 'label':'rest',
             'error_type':None if i<9 else 'empty_output'} for i in range(10)]
    assert ev.gate(rows, [str(i) for i in range(10)], [1])['advance_to_integration']
    rows[8]['pass'] = False
    assert not ev.gate(rows, [str(i) for i in range(10)], [1])['advance_to_integration']
    with pytest.raises(ValueError, match='denominator'):
        ev.gate(rows[:-1], [str(i) for i in range(10)], [1])
