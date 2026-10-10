"""Structural interpretation checks and the optional K re-read (no real K call)."""
import json
import pytest
from app.config import settings
from app.llm import mind_policy as m, mind_policy_guarded_core as guarded
from app.phase0 import mind_preparation as preparation

SOURCE = {'notes': [{'id': 'N0', 'text': '평소 목적지는 등록 공원이에요.'},
                    {'id': 'N2', 'text': '길을 잃으면 그 자리에서 30분 기다려요. 그래도 가족이 없으면 등록 공원 쪽으로 가요.'}],
          'places': [{'label': '등록 공원'}], 'prepared_initial': {}}


def output(habit='target_recognized', followup='lost_awareness and not family_present'):
    return {'source_assessment': '합성', 'non_action_note_ids': [], 'rules': [
        {'action': 'seek', 'goal_place': '등록 공원', 'applies_only_at': [], 'condition': habit,
         'hold_minutes': 0, 'note_ids': ['N0']},
        {'action': 'wait', 'goal_place': '', 'applies_only_at': [], 'condition': 'lost_awareness',
         'hold_minutes': 30, 'note_ids': ['N2']},
        {'action': 'seek', 'goal_place': '등록 공원', 'applies_only_at': [], 'condition': followup,
         'hold_minutes': 0, 'note_ids': ['N2']}]}


def checks_of(value):
    return preparation._checks(guarded.compile(value, SOURCE))


def test_other_answer_habit_competing_with_a_finite_wait_is_flagged():
    found = checks_of(output())
    assert [(c['check'], c['movement_rule_id'], c['movement_note_ids']) for c in found] == [
        ('other_answer_movement_competes_with_finite_wait', 'a_0', ['N0'])]


def test_habit_scoped_to_the_not_lost_state_is_not_flagged():
    assert checks_of(output(habit='target_recognized and not lost_awareness')) == []


def test_same_answer_followup_without_the_wait_trigger_is_flagged():
    found = checks_of(output(habit='target_recognized and not lost_awareness', followup='not family_present'))
    assert [(c['check'], c['movement_rule_id'], c['note_ids']) for c in found] == [
        ('same_note_followup_missing_wait_trigger', 'a_2', ['N2'])]


def test_ordered_same_answer_pair_is_not_flagged_and_checks_never_edit():
    policy = guarded.compile(output(habit='target_recognized and not lost_awareness'), SOURCE)
    before = policy.model_dump(mode='json')
    assert m.interpretation_checks(m.normalize_sequences(policy)[0]) == []
    m.interpretation_checks(policy)
    assert policy.model_dump(mode='json') == before


def _fake_k(monkeypatch, *contents):
    calls = []

    def invoke(url, body, **kwargs):
        calls.append(body)
        content = contents[min(len(calls), len(contents)) - 1]
        return {'id': f'r{len(calls)}', 'choices': [{'finish_reason': 'stop', 'message': {'content': content}}]}
    monkeypatch.setattr(settings, 'mind_policy_contract', 'guarded_core')
    monkeypatch.setattr(preparation, 'logged_json_request', invoke)
    return calls


def test_reread_is_off_by_default_and_the_warning_is_recorded(monkeypatch):
    assert settings.mind_policy_interpretation_review is False
    calls = _fake_k(monkeypatch, json.dumps(output()))
    policy, audit = preparation.interpret(SOURCE, 'check-unit')
    assert len(calls) == 1 and audit[0]['interpretation_checks'][0]['movement_rule_id'] == 'a_0'
    assert preparation._review_state(audit) == 'warning_recorded_reread_off'


def test_reread_sends_only_rule_and_answer_ids_and_adopts_a_valid_revision(monkeypatch):
    monkeypatch.setattr(settings, 'mind_policy_interpretation_review', True)
    revised = output(habit='target_recognized and not lost_awareness')
    calls = _fake_k(monkeypatch, json.dumps(output()), json.dumps(revised))
    policy, audit = preparation.interpret(SOURCE, 'check-unit')
    assert len(calls) == 2
    payload = json.loads(calls[1]['messages'][1]['content'])
    assert payload['original_notes'] == SOURCE['notes'] and payload['previous_public_output'] == output()
    # Names rules and answers; never the expected condition.
    assert 'lost_awareness' not in json.dumps(payload['structural_checks'], ensure_ascii=False)
    assert audit[-1]['role'] == 'interpretation_check' and audit[-1]['adopted'] and audit[-1]['remaining_checks'] == []
    assert policy == guarded.compile(revised, SOURCE).model_dump(mode='json')
    assert preparation._review_state(audit) == 'K_reread_adopted_not_independent_human_validation'


def test_failed_reread_keeps_the_first_policy_and_discloses_it(monkeypatch):
    monkeypatch.setattr(settings, 'mind_policy_interpretation_review', True)
    calls = _fake_k(monkeypatch, json.dumps(output()), 'not json')
    policy, audit = preparation.interpret(SOURCE, 'check-unit')
    assert len(calls) == 2 and not audit[-1]['adopted'] and audit[-1]['error_type']
    assert policy == guarded.compile(output(), SOURCE).model_dump(mode='json')
    assert preparation._review_state(audit) == 'K_reread_failed_first_policy_kept'


def test_no_third_output_after_a_format_correction(monkeypatch):
    monkeypatch.setattr(settings, 'mind_policy_interpretation_review', True)
    calls = _fake_k(monkeypatch, 'not json', json.dumps(output()))
    policy, audit = preparation.interpret(SOURCE, 'check-unit')
    assert len(calls) == 2 and audit[-1]['role'] == 'review' and audit[-1]['interpretation_checks']
    assert preparation._review_state(audit) == 'warning_recorded_second_output_already_used'


@pytest.mark.parametrize('value,state', [(output(habit='target_recognized and not lost_awareness'), 'no_structural_warning')])
def test_clean_policy_reports_no_warning(monkeypatch, value, state):
    _fake_k(monkeypatch, json.dumps(value))
    _, audit = preparation.interpret(SOURCE, 'check-unit')
    assert preparation._review_state(audit) == state
