import copy
import json
from pathlib import Path
import pytest
import single_world_v4 as c

D = Path(__file__).resolve().parent
ROWS = {r['id']: r for r in map(json.loads, (D/'dataset/development.jsonl').read_text().splitlines())}


@pytest.mark.parametrize('case_id', ['H3_D04-1', 'H3_D04-4'])
def test_each_world_is_identical_to_the_corresponding_v3_world(case_id):
    context = ROWS[case_id]['context']
    before = copy.deepcopy(context)
    old = c.previous.payload(context, 'branch_json_completion_v3', 'offline')
    data = json.loads(old['messages'][1]['content'])
    for key in data['가정_분기']:
        expected = copy.deepcopy(old)
        one = copy.deepcopy(data)
        for field in ['가정_분기', '가정_분기_읽기']:
            one[field] = {key: data[field][key]}
        expected['messages'][1]['content'] = json.dumps(one, ensure_ascii=False)
        schema = expected['response_format']['json_schema']['schema']
        schema['required'] = [key]
        schema['properties'] = {key: schema['properties'][key]}
        assert c.payload(context, key, 'offline') == expected
    assert context == before


def test_aggregation_preserves_uncertainty_and_requires_all_worlds_once():
    context = ROWS['H3_D04-4']['context']
    values = [{key: dict(next_command_id='continue' if world['/state/recent_events/1/value'] else 'avoid_market', source_ids=['N1'], reason='가정별 검증 응답')} for key,world in c.branches.worlds(context).items()]
    assert c.aggregate(values, context)['status'] == 'insufficient_information'
    with pytest.raises(ValueError, match='branch_coverage'):
        c.aggregate(values[:-1], context)
    with pytest.raises(ValueError, match='duplicate_world'):
        c.aggregate(values+[values[0]], context)
    invalid = copy.deepcopy(values)
    invalid[0][next(iter(invalid[0]))]['next_command_id'] = 'seek_0'
    with pytest.raises(ValueError, match='command_not_available'):
        c.aggregate(invalid, context)
