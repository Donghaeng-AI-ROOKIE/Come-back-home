"""No geography, inference or semantic-performance claims."""
import pytest
from experiments.mind_upgrade.contract_v2 import validate_choice, CHOICE

CONTEXT = {'known_places': [{'label': '등록 목적지'}],
           'person': {'evidence_notes': [{'id': 'N0'}]}, 'research': [],
           'environment': {'map_proximity_m': {'market': 20, 'water': None}}}


def value(action, **extra):
    return {'action': action, 'evidence_ids': ['N0'],
            'reason': '합성 입력에 대한 계약 검증', 'confusion_level': 'unknown', **extra}


@pytest.mark.parametrize('action,expected', [('continue', 'keep'), ('rest', 'keep'),
    ('stay', 'keep'), ('roam', 'clear')])
def test_action_owns_destination_operation(action, expected):
    d = validate_choice(value(action), CONTEXT)
    assert d.goal_operation == expected and d.goal_label is None


@pytest.mark.parametrize('action', ['continue', 'rest', 'stay', 'roam'])
def test_nonseek_cannot_emit_new_destination(action):
    with pytest.raises(ValueError):
        validate_choice(value(action, goal_label='등록 목적지'), CONTEXT)


def test_explicit_seek_and_avoid_have_separate_targets():
    assert validate_choice(value('seek', goal_label='등록 목적지'), CONTEXT).goal_operation == 'set'
    assert validate_choice(value('avoid', avoid_feature='market'), CONTEXT).goal_operation == 'keep'
    with pytest.raises(ValueError):
        validate_choice(value('seek', goal_label='등록 목적지', avoid_feature='market'), CONTEXT)


def test_unknown_sources_and_destinations_are_rejected():
    for invalid in [value('seek', goal_label='미등록'), value('rest', evidence_ids=['N404']),
                    value('avoid', avoid_feature='water')]:
        with pytest.raises(ValueError): validate_choice(invalid, CONTEXT)


def test_schema_exposes_per_action_constraints():
    schema = CHOICE.json_schema()
    assert schema['discriminator']['propertyName'] == 'action'
    assert len(schema['oneOf']) == 6
    assert 'goal_label' not in schema['$defs']['Rest']['properties']
    assert 'goal_label' in schema['$defs']['Seek']['required']
