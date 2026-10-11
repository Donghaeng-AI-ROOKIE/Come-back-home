import copy,json
from pathlib import Path
import pytest
import observation_contract_v2 as c

D=Path(__file__).resolve().parent
ROWS={r['source_id']:r for r in map(json.loads,(D/'dataset/development.jsonl').read_text().splitlines())}


def test_latest_orientation_is_not_mislabelled_as_earlier_history():
    context=ROWS['X19']['context'];before=copy.deepcopy(context)
    result=c.scene(context)
    assert result['latest_other_observations']['orientation_status_observation']['value']=='lost'
    assert result['latest_other_observations']['orientation_status_observation']['minutes_before_now']==0
    assert not any(e['kind']=='orientation_status_observation' for e in result['event_history'])
    assert context==before


def test_all_event_information_is_retained_with_latest_unknown_separate():
    context=copy.deepcopy(ROWS['X19']['context'])
    context['state']['recent_events'] += [dict(kind='self_lost_awareness_observation',value=True,elapsed_minutes=20),dict(kind='self_lost_awareness_observation',value=None,elapsed_minutes=60)]
    result=c.scene(context)
    assert result['latest_other_observations']['self_lost_awareness_observation']['value'] is None
    assert any(e['kind']=='self_lost_awareness_observation' and e['value'] is True and e['superseded_by_latest_observation'] for e in result['event_history'])
    assert len(result['event_history'])+len(result['latest_other_observations'])+1==len(context['state']['recent_events'])


def test_no_lost_awareness_inferred_from_orientation_or_fatigue():
    result=c.scene(ROWS['X19']['context'])
    assert 'self_lost_awareness_observation' not in result['latest_other_observations']
    context=copy.deepcopy(ROWS['X19']['context'])
    context['state']['recent_events'][-1]['elapsed_minutes']=61
    with pytest.raises(ValueError,match='invalid_event_time'):c.scene(context)


def test_raw_person_and_observation_meanings_are_not_rewritten():
    context=ROWS['X19']['context']
    old=json.loads(c.base.payload(context,'scene_v1','offline')['messages'][1]['content'])
    new=json.loads(c.payload(context,'offline')['messages'][1]['content'])
    assert old['person']==new['person'] and old['research']==new['research']
    assert old['available_commands']==new['available_commands']
    assert new['current_scene']['environment']==context['environment']
