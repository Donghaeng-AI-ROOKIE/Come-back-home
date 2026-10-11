import copy
import itertools
import json
from pathlib import Path

import pytest

from build import (HERE, PEOPLE, SOURCE, audit, build, contract, digest, export,
                   policy_results, read_rows, revise, rows_bytes, source_checks)
from regression import check_response, context_for, fixtures


@pytest.fixture(scope='module')
def data():
    old = read_rows(SOURCE / 'train.jsonl')
    new, changes = revise(old, json.loads((HERE / 'replacements.json').read_text()))
    return old, new, changes


def test_exact_81_text_only_changes_and_all_nine_states(data):
    old, new, changes = data
    assert len(old) == len(new) == 2160
    assert len(changes) == 81
    assert source_checks()
    for before, after in zip(old, new):
        if before['person_id'] not in PEOPLE:
            assert before == after
            continue
        restored = copy.deepcopy(after)
        text = restored['context']['person']['evidence_notes'][0]['text']
        assert text != before['context']['person']['evidence_notes'][0]['text']
        assert all(token not in text for token in ('때만', '겹쳐야', '같은 반응이라고 말한 건 아니'))
        assert '부탁' in text and '다른 사람' in text and '관찰한 반응' in text
        restored['context']['person']['evidence_notes'] = before['context']['person']['evidence_notes']
        assert restored == before
        assert after['expected_output']['next_command_id'] == 'continue'
    for person, variant in itertools.product(PEOPLE, range(3)):
        selected = [r for r in new if r['person_id'] == person and r['variant'] == variant]
        assert {tuple(r['authoring_oracle']['values']) for r in selected} == set(itertools.product((False, True, None), repeat=2))


# Literal tables authored independently of the enumerating policy implementation.
# Order: FF, FT, FU, TF, TT, TU, UF, UT, UU. U is unknown, never false.
TABLES = {
    'single': ['continue', 'continue', 'continue', 'rest', 'rest', 'rest', 'defer', 'defer', 'defer'],
    'and': ['continue', 'continue', 'continue', 'continue', 'rest', 'defer', 'continue', 'defer', 'defer'],
    'or': ['continue', 'rest', 'defer', 'rest', 'rest', 'rest', 'defer', 'rest', 'defer'],
    'unless': ['continue', 'continue', 'continue', 'rest', 'continue', 'defer', 'defer', 'continue', 'defer'],
    'priority': ['continue', 'stay', 'defer', 'rest', 'rest', 'rest', 'defer', 'defer', 'defer'],
}
TABLES['correction'] = TABLES['single']
TABLES['latest_observation'] = TABLES['single']


@pytest.mark.parametrize('kind', TABLES)
@pytest.mark.parametrize('index,values', list(enumerate(itertools.product((False, True, None), repeat=2))))
def test_three_valued_truth_table(kind, index, values):
    assert policy_results(kind, values, 'rest', 'stay')[1] == TABLES[kind][index]


@pytest.mark.parametrize('values', list(itertools.product((False, True, None), repeat=2)))
def test_invariant_profile_does_not_turn_unknown_into_false(values):
    assert policy_results('and', values, 'continue', 'stay') == (['continue'], 'continue')
    if values == (True, None):
        assert policy_results('and', values, 'rest', 'stay')[1] == 'defer'


@pytest.mark.parametrize('case', fixtures(), ids=lambda case: case['id'])
def test_source_subject_and_knowledge_preserved_through_real_payload(case):
    context = context_for(case)
    saved = copy.deepcopy(context)
    payload = contract.payload(context, 'separate_motion_and_goal', 'no-model-call')
    user = json.loads(payload['messages'][1]['content'])
    assert context == saved
    assert user['person']['evidence_notes'] == case['notes']
    facts = [x for x in user['observation_knowledge_states'] if x['path'] == '/environment/observed_signals/market/noisy']
    assert len(facts) == 1
    fact = facts[0]
    assert fact['original_value'] is case['value']
    assert fact['knowledge_state'] == ('참으로 확인' if case['value'] is True else '거짓으로 확인' if case['value'] is False else '참인지 거짓인지 미확인')
    assert fact['possible_values_not_new_observations'] == ([False, True] if case['value'] is None else [case['value']])
    assert 'authoring_oracle' not in json.dumps(payload)
    assert 'expected_command' not in json.dumps(payload)
    assert 'route' not in user['current_scene']['environment']
    response = dict(next_command_id=case['expected_command'], source_ids=case['expected_source_ids'], reason='독립 작성한 회귀 기대값. 실제 모델 출력이 아님.')
    check_response(case, response)
    # Negative controls reproduce the failure classes; the response checker
    # rejects these commands instead of claiming the model itself was repaired.
    bad = copy.deepcopy(response)
    bad['next_command_id'] = 'continue' if case['expected_command'] != 'continue' else 'avoid_market'
    with pytest.raises(ValueError, match='semantic_command_mismatch'):
        check_response(case, bad)
    if len(case['notes']) == 2:
        bad = copy.deepcopy(response)
        bad['source_ids'] = ['N2']
        with pytest.raises(ValueError, match='source_attribution_mismatch'):
            check_response(case, bad)


def test_requests_and_other_subjects_do_not_become_personal_observations():
    cases = {c['id']: c for c in fixtures()}
    for suffix in ('true', 'false', 'unknown'):
        assert cases['guardian_request_only_' + suffix]['expected_command'] == 'defer'
        assert cases['observed_other_only_' + suffix]['expected_command'] == 'defer'
    assert cases['observed_subject_true']['expected_command'] == 'avoid_market'
    assert cases['observed_subject_false']['expected_command'] == 'continue'
    assert cases['observed_subject_unknown']['expected_command'] == 'defer'


def test_goal_memory_does_not_cancel_avoidance_or_duplicate_seek(data):
    context = context_for(next(c for c in fixtures() if c['id'] == 'route_unspecified_A'))
    commands = {c['next_command_id']: c for c in json.loads(contract.payload(context, 'separate_motion_and_goal', 'offline')['messages'][1]['content'])['available_commands']}
    assert commands['continue']['goal_operation'] == 'keep'
    assert commands['avoid_market']['goal_operation'] == 'keep'
    assert commands['avoid_market']['action'] == 'avoid'
    assert 'seek_0' not in commands  # Already moving toward registered place A.
    assert commands['seek_1']['goal_operation'] == 'set'
    context['state']['current_action'] = 'rest'
    restarted = {c['next_command_id'] for c in json.loads(contract.payload(context, 'separate_motion_and_goal', 'offline')['messages'][1]['content'])['available_commands']}
    assert 'seek_0' in restarted  # Starting again is seek, not redundant continue.
    assert {c['expected_command'] for c in fixtures() if c['category'] == 'no_invented_route'} == {'avoid_market'}


def test_sft_export_has_corrected_notes_without_oracle_leakage(data):
    rows = [r for r in data[1] if r['person_id'] in PEOPLE]
    converted = export(rows)
    assert len(converted) == 81
    for row, sft in zip(rows, converted):
        assert [m['role'] for m in sft['messages']] == ['system', 'user', 'assistant']
        user = json.loads(sft['messages'][1]['content'])
        assert user['person'] == row['context']['person']
        assert json.loads(sft['messages'][2]['content']) == row['expected_output']
        assert sft['source_sha256'] == digest(json.dumps(row, ensure_ascii=False, sort_keys=True).encode())
        assert not {'authoring_oracle', 'expected_output', 'possible_commands'} & set(user)


def test_wrong_source_wording_and_relabel_fail_closed(data):
    replacements = json.loads((HERE / 'replacements.json').read_text())
    bad = copy.deepcopy(data[0])
    row = next(r for r in bad if r['person_id'] in PEOPLE)
    row['context']['person']['evidence_notes'][0]['text'] += ' changed'
    with pytest.raises(ValueError, match='old_wording_mismatch'):
        revise(bad, replacements)
    row['context']['person']['evidence_notes'][0]['text'] = replacements[0]['before']
    row['expected_output']['next_command_id'] = 'seek_1'
    with pytest.raises(ValueError, match='unexpected_affected_label'):
        revise(bad, replacements)


def test_mechanical_audit_rejects_injected_label_observation_and_leakage(data):
    bad = copy.deepcopy(data[1])
    bad[0]['expected_output']['next_command_id'] = 'rest'
    bad[1]['authoring_oracle']['values'][0] = True
    development = read_rows(SOURCE / 'development.jsonl')
    development[0]['group_id'] = bad[0]['group_id']
    report = audit(data[0], bad, development, read_rows(SOURCE / 'evaluation.jsonl'))
    assert report['status'] == 'FAIL'
    assert any('out_of_scope_change' in e for e in report['errors'])
    assert any('oracle_mismatch' in e for e in report['errors'])
    assert 'split_leakage:group_id' in report['errors']


def test_reproducible_complete_build_and_no_frozen_overwrites(tmp_path, data):
    out = tmp_path / 'v6'
    report = build(out)
    assert report['status'] == 'PASS'
    assert report['development_byte_identical'] and report['evaluation_byte_identical']
    assert (out / 'personal_contrasts_v6/train.jsonl').read_bytes() == rows_bytes(data[1])
    assert len(read_rows(out / 'training_export_v3/train.jsonl')) == 2160
    assert len(read_rows(out / 'training_export_v3/train_base.jsonl')) == 720
    assert len(read_rows(out / 'training_export_v3/development.jsonl')) == 180
    assert not (out / 'training_export_v3/evaluation.jsonl').exists()
    with pytest.raises(ValueError, match='refusing_overwrite'):
        build(out)
    with pytest.raises(ValueError, match='output_must_not_overlap_frozen_archive'):
        build(SOURCE / 'new')
