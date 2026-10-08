import json
from experiments.mind_contract_ab_20261007 import contract_d12,contract_d15,run_compact15


def test_d15_only_changes_instruction_not_input_sampling_schema_or_compiler():
    inputs,scenes,refs,_=run_compact15.selected_dataset()
    assert len(inputs)==8 and len(scenes)==32 and set(refs)==set(run_compact15.IDS)
    a=contract_d12.request(inputs[0]['personal'],'test')
    b=contract_d15.request(inputs[0]['personal'],'test')
    assert a['messages'][1:]==b['messages'][1:]
    assert b['messages'][0]['content'].startswith(a['messages'][0]['content'])
    assert {k:v for k,v in a.items() if k!='messages'}=={k:v for k,v in b.items() if k!='messages'}
    assert contract_d15.compile_d15 is contract_d12.compile_d12
    assert 'expected_commands' not in json.dumps(b)
