"""조건 과업의 근거 상황 유형 — K 가 근거마다 상황을 적고, 코드는 그 유형이 값의 정의에 맞는지만 본다.

v49 개발 세트: 두 판독이 함께 버스 이동을 '계속 이동·같은 방위'로, "공원을 특별히 좋아하시진
않는다"를 공원 회피로 읽어 일치 게이트를 통과했다. 대처·방향은 길 잃은 상황의 기록, 환경 반응은
그 환경을 마주친 반응만 근거가 된다(person_scope.ADMISSIBLE). 모델 호출 없음.
"""
import copy
import json

import pytest

from app import storage
from app.config import settings
from app.llm import initial_behavior, person_scope
from app.phase0 import person_preparation as prep
from app.phase0 import persona_events
from app.phase2 import initial_person
from tests.test_person_evidence_projection import sample  # noqa: F401 — pytest fixture


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    storage.reset_for_tests()
    for name in ('kexaone_api_key', 'kexaone_base_url', 'kexaone_model'):
        monkeypatch.setattr(settings, name, 'offline-test')
    monkeypatch.setattr(prep, '_dispatch', lambda *args: None)
    monkeypatch.setattr(persona_events, 'notify_persona_updated', lambda *args: None)
    yield
    storage.reset_for_tests()


def respond(obj, finish='stop'):
    return {'choices': [{'finish_reason': finish,
                         'message': {'content': json.dumps(obj) if finish == 'stop' else ' ' * 50}}]}


def _unknown_env(**overrides):
    env = {f: {'response': 'unknown', 'condition': 'unknown', 'note_ids': [], 'condition_clauses': [],
               'spatial_scope': 'unknown', 'basis_situations': []}
           for f in ('water', 'forest', 'park', 'market')}
    for feature, leaf in overrides.items():
        env[feature].update(leaf)
    return env


def test_request_asks_for_situation_of_every_claim(sample):
    payload = initial_behavior.build_payload(sample[0], None, [], None)
    body = person_scope.request(payload, 'm')
    schema = body['response_format']['json_schema']['schema']['properties']
    assert 'basis_situations' in schema['persistence']['properties']
    assert all('basis_situations' in e['properties'] for e in schema['environment']['properties'].values())
    assert 'basis_situations' in schema['baseline_direction']['properties']
    assert 'basis_situations' in schema['behavior_rules']['items']['properties']
    assert 'lost_or_confused' in body['messages'][0]['content']


def test_inadmissible_situations_do_not_reach_the_contract(sample):
    payload = initial_behavior.build_payload(sample[0], None, [], None)
    z = {'persistence': {'evidence': 'supported', 'pattern': 'consistent', 'value': 'keep_moving',
                         'note_ids': ['N0'], 'basis_situations': [{'note_id': 'N0', 'situation': 'destination_trip'}]},
         'environment': _unknown_env(
             park={'response': 'avoid', 'spatial_scope': 'category', 'condition': 'none', 'note_ids': ['N1'],
                   'basis_situations': [{'note_id': 'N1', 'situation': 'preference_or_neutral'}]},
             water={'response': 'approach', 'spatial_scope': 'category', 'condition': 'none', 'note_ids': ['N2'],
                    'basis_situations': [{'note_id': 'N2', 'situation': 'encounter_reaction'}]}),
         'baseline_direction': {'value': 'same_heading', 'note_ids': ['N0'],
                                'basis_situations': [{'note_id': 'N0', 'situation': 'routine_outing'}]},
         'behavior_rules': [
             {'period': 'clock_night', 'dimension': 'persistence', 'value': 'keep_moving', 'note_ids': ['N0'],
              'basis_situations': [{'note_id': 'N0', 'situation': 'lost_or_confused'}]},
             {'period': 'clock_day', 'dimension': 'direction', 'value': 'same_heading', 'note_ids': ['N1'],
              'basis_situations': [{'note_id': 'N1', 'situation': 'routine_outing'}]}]}
    cleaned, events = person_scope.soft_clean(z, payload)
    parsed = person_scope.validate(respond(cleaned), payload)
    assert parsed['persistence']['value'] == 'unknown'
    assert parsed['environment']['park']['response'] == 'unknown'
    assert parsed['environment']['water']['response'] == 'approach'
    assert parsed['baseline_direction']['value'] == 'unknown'
    assert parsed['behavior_rules'] == [{'period': 'clock_night', 'dimension': 'persistence',
                                         'value': 'keep_moving', 'note_ids': ['N0']}]
    refused = {(e['field'], e['value']) for e in events if e['reason'] == 'basis_not_admissible'}
    assert refused == {('persistence', 'keep_moving'), ('environment.park', 'avoid'),
                       ('baseline_direction', 'same_heading'), ('behavior_rules', 'same_heading')}
    kept = {(e['field'], e['value']) for e in events if e['reason'] == 'basis'}
    assert kept == {('environment.water', 'approach'), ('behavior_rules', 'keep_moving')}


def test_situation_must_belong_to_a_cited_note(sample):
    """근거 목록에 없는 노트의 상황 유형은 세지 않는다 — 모델이 인용과 유형을 따로 꾸며낼 수 없다."""
    payload = initial_behavior.build_payload(sample[0], None, [], None)
    z = {'persistence': {'evidence': 'supported', 'pattern': 'consistent', 'value': 'wait_for_help',
                         'note_ids': ['N1'], 'basis_situations': [{'note_id': 'N0', 'situation': 'lost_or_confused'}]},
         'environment': _unknown_env(), 'baseline_direction': {'value': 'unknown', 'note_ids': [], 'basis_situations': []},
         'behavior_rules': []}
    cleaned, _ = person_scope.soft_clean(z, payload)
    assert person_scope.validate(respond(cleaned), payload)['persistence']['value'] == 'unknown'


def test_failed_context_draft_is_judged_once_more_from_the_notes(sample, monkeypatch):
    """조건 초안이 실패하면 네 번째 요청이 원문에서 다시 판단하고, 그 단독 판독을 쓴다(감사 기록)."""
    payload = initial_behavior.build_payload(sample[0], None, [], None)
    single = copy.deepcopy(sample[-1])
    single['environment']['water'].update(response='approach', scope='explicit_category',
                                          condition='추가 조건 없음', note_ids=['N1'])
    seen = []

    def fake(url, body, **kwargs):
        seen.append(kwargs['role'])
        if kwargs['role'] == 'initial_person_context':
            return respond(None, finish='length')
        if kwargs['role'] == 'initial_person_context_review':
            draft = json.loads(body['messages'][1]['content'])['draft']['content']
            assert draft['persistence']['value'] == 'unknown'
            return respond(single)
        return respond(sample[-2])

    monkeypatch.setattr(initial_person, 'logged_json_request', fake)
    result = initial_person.interpret(payload)
    assert sorted(seen) == sorted(['initial_person_core', 'initial_person_context',
                                   'initial_person_semantic_audit', 'initial_person_context_review'])
    assert result['context']['environment']['water']['response'] == 'approach'
    assert result['audit']['fallbacks'] == ['context_draft_failed:ValueError', 'context_single_reading']


def test_both_context_readings_failing_leaves_context_unknown(sample, monkeypatch):
    payload = initial_behavior.build_payload(sample[0], None, [], None)

    def fake(url, body, **kwargs):
        if 'context' in kwargs['role']:
            return respond(None, finish='length')
        return respond(sample[-2])

    monkeypatch.setattr(initial_person, 'logged_json_request', fake)
    result = initial_person.interpret(payload)
    assert result['context']['persistence']['value'] == 'unknown'
    assert 'context_review_failed:ValueError' in result['audit']['fallbacks']


# ── 사건 적용: 사건 당시 발언의 근거 등급, SAR 기울기 완화 ──────────────

def _ready_three(sample, goal_value, *, after_incident=False):
    """장소 셋(공원·시장·복지관) — 둘이면 독식 상한(0.6)에 걸려 가중치 차이가 안 보인다."""
    from datetime import timedelta

    from app.schemas.common import GeoPoint
    from app.schemas.persona import AttractionPoint
    p = sample[0].model_copy(deep=True)
    p.attraction_points.append(AttractionPoint(label='복지관', location=GeoPoint(lat=37.63, lng=127.03)))
    if after_incident:
        lkp = sample[1].lkp_time
        p.created_at = (lkp.replace(tzinfo=None) if lkp.tzinfo else lkp) + timedelta(minutes=30)
    core = copy.deepcopy(sample[-2])
    for section, value in (('goals', 'unknown'), ('routes', 'unknown'), ('found_history', 'not_reported')):
        core[section]['복지관'] = copy.deepcopy(core[section]['시장'])
    core['goals']['공원'].update(value=goal_value, note_ids=['N2'])
    key = prep.fingerprint(p)
    p.initial_preparation_status = {'state': 'ready', 'fingerprint': key}
    p.prepared_initial = {'fingerprint': key, 'core': core, 'scope': copy.deepcopy(sample[-1]),
                          'profile_snapshot_at': '2026-01-01T12:00:00'}
    return p


def test_statement_at_incident_counts_as_strong_evidence(sample):
    """사건 당일 한 발언(current_statement)은 반복 목적지와 같은 근거 등급 — 언급만 된 곳에 밀리지 않는다.

    v49 보류 H5: "오늘 옛집에 가신다고"라고 한 옛집이 언급만 된 시장보다 약했다.
    상(3)×관찰(0.5)=1.5 대 중(2)×언급(0.3)=0.6 두 곳 → 1.5/2.7. 예전(언급 0.3)이면 0.9/2.1.
    """
    p = _ready_three(sample, 'current_statement', after_incident=True)
    out = prep.apply_prepared(p, sample[1], sample[2], sample[3])
    assert out.initial_interpretation['semantic_contract']['goals']['공원']['value'] == 'current_statement'
    assert out.attraction_weights['공원'] == pytest.approx(1.5 / 2.7)


def test_sar_tilt_is_damped(sample):
    """SAR 등급 기울기는 제곱근으로 줄인다 — 상:하 = 1.22:0.71(약 1.73배, 예전 3배)."""
    p = _ready_three(sample, 'unknown')
    sar = sample[2].model_copy(update={'attraction_levels': {'공원': '상', '시장': '하'}})
    out = prep.apply_prepared(p, sample[1], sar, sample[3])
    ratio = out.attraction_weights['공원'] / out.attraction_weights['시장']
    assert ratio == pytest.approx((1.5 / .5) ** .5, rel=1e-6)
