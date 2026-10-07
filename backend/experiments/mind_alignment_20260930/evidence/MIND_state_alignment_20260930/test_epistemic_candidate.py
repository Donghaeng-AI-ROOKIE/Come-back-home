import json
from pathlib import Path
import epistemic_candidate as candidate
import unique_command_contract as original
D=Path(__file__).resolve().parent

def test_observation_table_preserves_truth_and_no_oracle():
    rows=list(map(json.loads,(D/'contrast_pilot2/dataset.jsonl').read_text().splitlines()))
    for r in rows:
        before=original.payload(r['context'],'concise_person_scene','local-only')
        after=candidate.payload(r['context'],'explicit_knowledge_state','local-only')
        a,b=map(lambda x:json.loads(x['messages'][1]['content']),(before,after))
        assert b['current_scene']==a['current_scene'] and b['person']==a['person']
        assert 'authoring_oracle' not in after['messages'][1]['content']
        assert 'expected_command' not in after['messages'][1]['content']
        assert len(json.dumps(after,ensure_ascii=False).encode())+256<=16384
        for f in b['observation_knowledge_states']:
            assert f['possible_values_not_new_observations']==([False,True] if f['original_value'] is None else [f['original_value']])

def test_no_action_selection_in_knowledge_state_table():
    rows=list(map(json.loads,(D/'contrast_pilot2/dataset.jsonl').read_text().splitlines()))
    a,b=rows[:2]
    assert a['contrast_id']==b['contrast_id']
    render=lambda r:json.loads(candidate.payload(r['context'],'explicit_knowledge_state','local-only')['messages'][1]['content'])
    assert render(a)['observation_knowledge_states']==render(b)['observation_knowledge_states']
