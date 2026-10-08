from experiments.mind_contract_ab_20261007 import run_compact24 as wide, run_repair8, contract_d12


def test_expansion_excludes_all_repair_people_and_keeps_existing_references():
    inputs, scenes, refs, files = wide.expanded_dataset()
    excluded = {key.split('_')[1] for key in run_repair8.IDS}
    assert len(inputs) == 24
    assert len(scenes) == 96
    assert not {x['root_id'] for x in inputs} & excluded
    assert all(x['form'] == 'original' and x['split'] == 'development' for x in inputs)
    assert {x['id'] for x in inputs} == set(refs) == {x['input_id'] for x in scenes}
    assert all('dev128' in str(f) for f in files)


def test_reference_and_scene_sentinels_cannot_enter_model_request():
    inputs, scenes, refs, _ = wide.expanded_dataset()
    scenes[0]['expected_commands'] = ['GOLD_ONLY_SENTINEL']
    refs[inputs[0]['id']] = {'note': 'REFERENCE_ONLY_SENTINEL'}
    import json
    text = json.dumps(contract_d12.request(inputs[0]['personal'], 'test-model'))
    assert 'GOLD_ONLY_SENTINEL' not in text
    assert 'REFERENCE_ONLY_SENTINEL' not in text
