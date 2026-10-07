import copy
import json
from pathlib import Path
import motion_goal_candidate as candidate
import unique_command_contract as contract

D = Path(__file__).resolve().parent

def test_payload_preserves_facts_and_exact_executable_goal_operations():
    row = json.loads((D / 'contrast_pilot3/dataset.jsonl').read_text().splitlines()[0])
    context = row['context']; saved = copy.deepcopy(context)
    body = candidate.payload(context, 'separate_motion_and_goal', 'no-api')
    data = json.loads(body['messages'][1]['content'])
    options = contract.options(context)
    assert context == saved
    assert data['person'] == context['person']
    for entry in data['available_commands']:
        assert all(entry[key] == value for key, value in options[entry['next_command_id']].items())
    assert options['rest']['goal_operation'] == options['stay']['goal_operation'] == 'keep'
    assert '이미 향하던 같은 목적지를 유지하는 명령은 continue다.' not in body['messages'][0]['content']
    assert 'authoring_oracle' not in json.dumps(body)

def test_altered_person_words_do_not_change_available_commands():
    context = json.loads((D / 'contrast_pilot3/dataset.jsonl').read_text().splitlines()[0])['context']
    before = json.loads(candidate.payload(context, 'separate_motion_and_goal', 'no-api')['messages'][1]['content'])
    context['person']['evidence_notes'] = [{'id': 'N1', 'text': '동일 환경에서 이 사람은 다르게 반응한다.'}]
    after = json.loads(candidate.payload(context, 'separate_motion_and_goal', 'no-api')['messages'][1]['content'])
    assert before['available_commands'] == after['available_commands']
    assert before['observation_knowledge_states'] == after['observation_knowledge_states']
