"""제3 판독 — 엔진에 들어갈 K 해석 값을 다른 모델에게 좁은 예/아니오로 확인한다. 모델 호출 없음.

4회차 개발 세트: 두 판독이 함께 틀린 값이 통과했고(H6 물가 회피), 재검토가 맞는 초안을 근거 없이
되돌렸으며(S4 과거 발견지), 엇갈린 두 판독 때문에 맞는 값이 막혔다(S2 숲, H8 대처).
"""
import copy

import pytest

from app.llm import initial_behavior
from app.phase2 import claim_check
from tests.test_person_evidence_projection import sample  # noqa: F401 — pytest fixture


def _parsed(sample, **audit):
    return {'core': copy.deepcopy(sample[-2]), 'context': copy.deepcopy(sample[-1]), 'audit': dict(audit)}


def _payload(sample):
    return initial_behavior.build_payload(sample[0], None, [], None)


def _answers(monkeypatch, table):
    """문장 → 답. 표에 없는 문장은 판정 없음(None)."""
    asked = []

    def check(notes, statement):
        asked.append(statement)
        return next((v for k, v in table.items() if k in statement), None)

    monkeypatch.setattr(claim_check.midm, 'check_claim', check)
    return asked


def test_unconfirmed_persistence_is_held(sample, monkeypatch):
    parsed = _parsed(sample)
    parsed['context']['persistence'].update(evidence='supported', pattern='consistent', value='keep_moving', note_ids=['N0'])
    _answers(monkeypatch, {'계속 걷는다': False})
    out = claim_check.verify(parsed, _payload(sample))
    assert out['context']['persistence']['value'] == 'unknown'
    assert out['audit']['claim_checks'][0]['answer'] is False


@pytest.mark.parametrize('answer', [True, None])
def test_confirmed_or_unchecked_persistence_stays(sample, monkeypatch, answer):
    """'예'면 그대로, 확인 호출이 실패하면(None) K 결과를 지우지 않는다."""
    parsed = _parsed(sample)
    parsed['context']['persistence'].update(evidence='supported', pattern='consistent', value='wait_for_help', note_ids=['N0'])
    _answers(monkeypatch, {'도움을 기다린다': answer})
    assert claim_check.verify(parsed, _payload(sample))['context']['persistence']['value'] == 'wait_for_help'


def test_category_reaction_both_readings_shared_is_checked(sample, monkeypatch):
    """H6: 두 판독이 함께 '물가 전체 회피'로 읽어도 제3 판독이 아니라면 내린다. 한 곳 반응은 묻지 않는다."""
    parsed = _parsed(sample)
    env = parsed['context']['environment']
    env['water'].update(response='avoid', scope='explicit_category', condition='추가 조건 없음', note_ids=['N0'])
    env['park'].update(response='approach', scope='place_specific', condition='추가 조건 없음', note_ids=['N0'])
    asked = _answers(monkeypatch, {'물가': False})
    out = claim_check.verify(parsed, _payload(sample))
    assert out['context']['environment']['water']['response'] == 'unknown'
    assert out['context']['environment']['park']['response'] == 'approach'
    assert len(asked) == 1 and '그런 곳 전반' in asked[0]


def test_conditional_reaction_question_carries_the_condition(sample, monkeypatch):
    parsed = _parsed(sample)
    parsed['context']['environment']['market'].update(
        response='avoid', scope='conditional_category', condition='추가 조건 필요', note_ids=['N0'],
        condition_clauses=[[{'signal': 'crowded', 'state': 'present'}, {'signal': 'noisy', 'state': 'present'}]])
    asked = _answers(monkeypatch, {'시장': True})
    claim_check.verify(parsed, _payload(sample))
    assert '(사람이 많음 그리고 시끄러움)일 때만' in asked[0]


def test_unconfirmed_clock_rule_is_removed(sample, monkeypatch):
    parsed = _parsed(sample)
    parsed['context']['behavior_rules'] = [
        {'period': 'clock_night', 'dimension': 'persistence', 'value': 'keep_moving', 'note_ids': ['N0']},
        {'period': 'clock_day', 'dimension': 'direction', 'value': 'retrace', 'note_ids': ['N0']}]
    _answers(monkeypatch, {'밤(': True, '낮(': False})
    out = claim_check.verify(parsed, _payload(sample))
    assert [r['value'] for r in out['context']['behavior_rules']] == ['keep_moving']


def test_disagreement_is_resolved_only_when_one_candidate_is_confirmed(sample, monkeypatch):
    """S2·H8: 엇갈린 두 판독 중 제3 판독이 하나만 인정하면 그 값을 살린다. 둘 다 인정하면 보류."""
    parsed = _parsed(sample, context_disagreements=[
        {'field': 'persistence', 'draft': 'keep_moving', 'review': 'wait_for_help'},
        {'field': 'environment.forest', 'draft': ['unknown', 'unknown'], 'review': ['approach', 'explicit_category']}])
    _answers(monkeypatch, {'계속 걷는다': True, '도움을 기다린다': False, '숲이나 산': True})
    out = claim_check.verify(parsed, _payload(sample))
    assert out['context']['persistence']['value'] == 'keep_moving'
    assert out['context']['environment']['forest']['response'] == 'approach'
    assert out['context']['environment']['forest']['scope'] == 'explicit_category'

    both = _parsed(sample, context_disagreements=[{'field': 'persistence', 'draft': 'keep_moving', 'review': 'wait_for_help'}])
    _answers(monkeypatch, {'계속 걷는다': True, '도움을 기다린다': True})
    assert claim_check.verify(both, _payload(sample))['context']['persistence']['value'] == 'unknown'


def test_found_place_is_checked_and_a_review_reversal_can_be_restored(sample, monkeypatch):
    """S4: 재검토가 인용된 발견지를 근거 없이 되돌렸다 — 제3 판독이 '예'면 초안 값을 되살린다."""
    parsed = _parsed(sample, core_review_changes=[
        {'field': 'found_history.시장', 'draft': 'found_here', 'review': 'not_reported', 'draft_note_ids': ['N1']}])
    parsed['core']['found_history']['공원'].update(value='found_here', note_ids=['N2'])
    _answers(monkeypatch, {"'공원'에서 발견": False, "'시장'에서 발견": True})
    out = claim_check.verify(parsed, _payload(sample))
    assert out['core']['found_history']['공원']['value'] == 'not_reported'
    assert out['core']['found_history']['시장'] == {**sample[-2]['found_history']['시장'],
                                                    'value': 'found_here', 'note_ids': ['N1']}


def test_preparation_job_runs_the_check(sample, monkeypatch):
    """운영 준비 작업(run_job)도 해석 뒤 제3 판독을 거친다."""
    from app import storage
    from app.config import settings
    from app.phase0 import person_preparation as prep
    from app.phase0 import persona_events
    from app.phase2 import initial_person

    storage.reset_for_tests()
    for name in ('kexaone_api_key', 'kexaone_base_url', 'kexaone_model'):
        monkeypatch.setattr(settings, name, 'offline-test')
    monkeypatch.setattr(prep, '_dispatch', lambda *args: None)
    monkeypatch.setattr(persona_events, 'notify_persona_updated', lambda *args: None)
    context = copy.deepcopy(sample[-1])
    context['persistence'].update(evidence='supported', pattern='consistent', value='keep_moving', note_ids=['N0'])
    monkeypatch.setattr(initial_person, 'cached_research', lambda persona, report: [])
    monkeypatch.setattr(initial_person, 'interpret',
                        lambda payload: {'core': copy.deepcopy(sample[-2]), 'context': context, 'audit': {}})
    _answers(monkeypatch, {'계속 걷는다': False})
    p = sample[0]
    storage.personas.save(p.id, p)
    queued = prep.enqueue(p.id)
    prep.run_job(p.id, queued.initial_preparation_status['job_id'])
    saved = storage.personas.get(p.id)
    assert saved.initial_preparation_status['state'] == 'ready'
    assert saved.prepared_initial['scope']['persistence']['value'] == 'unknown'
    assert saved.prepared_initial['audit']['claim_checks'][0]['field'] == 'persistence'
    storage.reset_for_tests()
