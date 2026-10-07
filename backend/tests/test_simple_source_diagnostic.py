from copy import deepcopy
from experiments.mind_contract_ab_20261007 import probe_simple_source as p


def test_missing_trigger_and_reversed_release_are_failures():
    expected = p.CASES[0][2]
    omitted = deepcopy(expected)
    omitted['start_all'] = ['family_absent']
    assert not p.matches(omitted, expected)
    reversed_release = deepcopy(expected)
    reversed_release['end_all'] = ['family_absent']
    assert not p.matches(reversed_release, expected)


def test_order_does_not_change_all_condition_meaning_but_duplicates_fail():
    expected = p.CASES[0][2]
    reordered = deepcopy(expected)
    reordered['start_all'].reverse()
    assert p.matches(reordered, expected)
    reordered['start_all'].append('family_absent')
    assert not p.matches(reordered, expected)


def test_scope_loss_and_invented_behavior_fail():
    expected = p.CASES[2][2]
    broad = dict(expected, only_at=None)
    assert not p.matches(broad, expected)
    unknown = p.CASES[3][2]
    assert not p.matches(dict(unknown, action='wait'), unknown)


def test_request_contains_source_not_reference_or_scene_answers():
    case, source, expected = p.CASES[0]
    body = p.request(source, True)
    assert body['messages'][1]['content'] == source
    assert list(body['messages'][1]) == ['role', 'content']
    assert 'references_NOT_MODEL_INPUT' not in body
    assert body['presence_penalty'] == 0.0
    assert body['repetition_penalty'] == 1.0
