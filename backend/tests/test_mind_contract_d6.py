"""Preparation checks, not model-quality evidence."""
import json
from experiments.mind_contract_ab_20261007 import contract_d6 as d6, run_repair8, run_v2
from tests.test_mind_contract_ab import D_CORRECT, to_d3
from experiments.mind_contract_ab_20261007 import scoring


def test_same_compiler_preserves_existing_behavior_fixtures():
    from experiments.mind_contract_ab_20261007 import contract_d4
    people, _, _ = scoring.load()
    for key, value in D_CORRECT.items():
        value = to_d3(value)
        personal = people[key]['personal']
        assert d6.compile_d6(value, personal) == contract_d4.compile_d4(value, personal)


def test_no_role_matrix_and_question_context_is_present():
    inputs, _, _, _ = run_repair8.repair_dataset()
    body = d6.request(inputs[0]['personal'], 'test-model')
    value = json.loads(body['messages'][-1]['content'])
    assert value['answers_by_turn'][1]['chatbot_question']
    assert set(value['output_schema']['properties']) == {'behaviors', 'other_sentences'}
    assert 'sentence_roles' not in value['output_schema']['properties']
    assert body['temperature'] == 1.0 and body['max_tokens'] == 16384


def test_repair_selection_is_exactly_eight_frozen_inputs_and_32_scenes():
    inputs, scenes, refs, _ = run_repair8.repair_dataset()
    assert tuple(r['id'] for r in inputs) == run_repair8.IDS
    assert len(inputs) == 8 and len(scenes) == 32 and set(refs) == set(run_repair8.IDS)
    assert all(sum(s['input_id'] == r['id'] for s in scenes) == 4 for r in inputs)
    original = {json.loads(x)['id']: json.loads(x) for x in
                (run_v2.DEV128 / 'dev128_inputs.jsonl').read_text().splitlines()}
    assert all(r['personal'] == original[r['id']]['personal'] for r in inputs)
