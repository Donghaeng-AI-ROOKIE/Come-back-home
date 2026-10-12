import copy,json
from pathlib import Path
import pytest
import state_contract as c

D=Path(__file__).resolve().parent
ROWS={r['source_id']:r for r in map(json.loads,(D/'dataset/development.jsonl').read_text().splitlines())}


def test_person_and_research_preserved_no_expected_input():
    for row in ROWS.values():
        context=row['context']; before=copy.deepcopy(context)
        data=json.loads(c.payload(context,'scene_v1','offline')['messages'][1]['content'])
        assert data['person']==context['person'] and data['research']==context['research']
        assert context==before
        assert 'rubric' not in data and 'expected' not in data


def test_companion_false_unknown_and_family_not_conflated():
    for case_id,value,relation in [('H3_D04-1',False,'none'),('H3_D04-2',True,'family'),('H3_D04-4',None,'unknown')]:
        s=c.scene(ROWS[case_id]['context'])
        assert s['latest_companion_observation']['value'] is value
        assert s['latest_companion_observation']['relation']==relation
        assert s['latest_companion_observation']['minutes_before_now']==1
    ctx=copy.deepcopy(ROWS['H3_D04-2']['context'])
    del ctx['state']['recent_events'][-1]['relation']
    assert c.scene(ctx)['latest_companion_observation']['relation']=='unknown'


def test_latest_unknown_supersedes_older_present_without_false_conversion():
    ctx=copy.deepcopy(ROWS['H3_D04-2']['context'])
    ctx['state']['recent_events'].append(dict(kind='companion_observation',value=None,elapsed_minutes=60,relation='unknown'))
    s=c.scene(ctx)
    assert s['latest_companion_observation']['value'] is None
    assert any(e.get('superseded_by_latest_observation') for e in s['earlier_event_history'])
    ctx['state']['recent_events'][-1]['elapsed_minutes']=61
    with pytest.raises(ValueError,match='invalid_event_time'):c.scene(ctx)


def test_rest_end_does_not_imply_fatigue_recovery_or_future_observation():
    ctx=copy.deepcopy(ROWS['X21']['context']);ctx['state']['fatigue']=.9
    s=c.scene(ctx)
    assert s['state']['fatigue_band']=='high' and s['state']['minutes_since_rest_end']==0
    ctx['state']['last_rest_end_minutes']=61
    with pytest.raises(ValueError,match='invalid_rest_time'):c.scene(ctx)


def test_invalid_relation_rejected_without_repair():
    ctx=copy.deepcopy(ROWS['H3_D04-1']['context'])
    ctx['state']['recent_events'][-1]['relation']='family'
    with pytest.raises(ValueError,match='conflicting_companion'):c.scene(ctx)


def test_data_split_keeps_people_separate():
    dev=[json.loads(x) for x in (D/'dataset/development.jsonl').read_text().splitlines()]
    ev=[json.loads(x) for x in (D/'dataset/evaluation.jsonl').read_text().splitlines()]
    assert (len(dev),len(ev))==(16,32)
    assert not ({r['context']['person_id'] for r in dev}&{r['context']['person_id'] for r in ev})
