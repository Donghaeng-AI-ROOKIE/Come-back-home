import copy,json
from pathlib import Path
import pytest
import unique_command_contract as c
D=Path(__file__).resolve().parent

def context():return json.loads((D/'dataset/development.jsonl').read_text().splitlines()[0])['context']

def test_same_target_has_one_maintenance_command():
    x=context();old=copy.deepcopy(x)
    choices=c.options(x)
    assert 'continue' in choices and 'seek_0' not in choices and 'seek_1' in choices
    assert x==old
    for arm in ('observation_v2','concise_person_scene'):
        body=c.payload(x,arm,'local-only')
        assert set(body['response_format']['json_schema']['schema']['properties']['next_command_id']['enum'])==set(choices)
        assert {r['next_command_id'] for r in json.loads(body['messages'][1]['content'])['available_commands']}==set(choices)
    with pytest.raises(ValueError,match='command_not_available'):
        c.validate(dict(next_command_id='seek_0',source_ids=['N1'],reason='같은 목표 유지'),x)

@pytest.mark.parametrize('action',['rest','stay'])
def test_resume_to_remembered_target_preserved(action):
    x=context();x['state']['current_action']=action
    assert 'seek_0' in c.options(x) and 'continue' not in c.options(x)

def test_changing_target_and_avoid_to_seek_remain_available():
    x=context();x['state']['current_action']='avoid'
    assert 'seek_0' in c.options(x) and 'seek_1' in c.options(x)

def test_guardian_words_do_not_choose_a_command():
    x=context();before=c.options(x)
    x['person']['evidence_notes']=[dict(id='N1',text='피곤해도 계속 걷고 소리가 커지면 멈추기도 합니다.')]
    assert c.options(x)==before
