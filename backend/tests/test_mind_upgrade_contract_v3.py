import pytest
from experiments.mind_upgrade.contract_v3 import generation_schema, validate_choice
from experiments.mind_upgrade.contract_v2 import CHOICE


def test_generation_orders_action_first_without_changing_branch_constraints():
    schema = generation_schema()
    assert len(schema['oneOf']) == 6
    for definition in schema['$defs'].values():
        assert next(iter(definition['properties'])) == 'action'
        assert definition['additionalProperties'] is False
        assert definition['properties']['reason']['maxLength'] == 400
    assert 'goal_label' in schema['$defs']['Seek']['required']
    assert 'goal_label' not in schema['$defs']['Rest']['properties']


def test_reason_length_is_still_enforced_after_generation():
    with pytest.raises(ValueError):
        CHOICE.validate_python({'action':'rest','evidence_ids':['state'],
                                'reason':'가'*401,'confusion_level':'unknown'})
    assert CHOICE.json_schema()['$defs']['Rest']['properties']['reason']['maxLength'] == 400
