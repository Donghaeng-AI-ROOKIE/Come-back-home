from copy import deepcopy
import pytest
from experiments.mind_contract_ab_20261007 import contract_d15, contract_d16, run_compact15
from tests.test_diagnostic_coverage import sample


def test_same_input_schema_sampling_and_no_source_repair():
    personal = run_compact15.selected_dataset()[0][0]['personal']
    a, b = contract_d15.request(personal, 'test'), contract_d16.request(personal, 'test')
    assert a['messages'][1:] == b['messages'][1:]
    assert {k: v for k, v in a.items() if k != 'messages'} == {k: v for k, v in b.items() if k != 'messages'}
    assert b['messages'][0]['content'].startswith(a['messages'][0]['content'])


def test_missing_ids_are_feedback_not_automatic_classification():
    raw, personal = sample()
    original = deepcopy(raw)
    with pytest.raises(ValueError, match='missing note IDs N1'):
        contract_d16.compile_d16(raw, personal)
    assert raw == original
    raw['rules'][0]['note_ids'].append('N1')
    assert contract_d16.compile_d16(raw, personal) == contract_d15.compile_d15(raw, personal)


def test_invalid_conditions_remain_rejected():
    raw, personal = sample()
    raw['rules'][0]['condition'] = 'made_up_fact'
    with pytest.raises(ValueError, match='unknown condition fact'):
        contract_d16.compile_d16(raw, personal)
