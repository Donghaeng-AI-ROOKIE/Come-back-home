"""신고 상황 ↔ 등록 장소 — 모델이 잇고, 코드는 등록 이름·원문 구절만 확인한다. 모델 호출 없음.

v49 보류: "출근하셔야 한다며"(옛 직장, H3)·"늘 하던 산책"(H7)을 SAR 가 가르지 못해 세 장소가
모두 '상'이었다. K 는 사건 전에 준비돼 이 문장을 못 읽는다.
"""
import copy

import pytest

from app import storage
from app.config import settings
from app.phase0 import person_preparation as prep
from app.phase0 import persona_events, prompts
from app.phase2 import situation_link
from app.schemas.case import Case
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


def _ready(sample):
    p = sample[0]
    core = copy.deepcopy(sample[-2])
    core['goals']['공원'].update(value='repeated_statement', note_ids=['N2'])
    key = prep.fingerprint(p)
    p.initial_preparation_status = {'state': 'ready', 'fingerprint': key}
    p.prepared_initial = {'fingerprint': key, 'core': core, 'scope': copy.deepcopy(sample[-1]),
                          'profile_snapshot_at': '2026-01-01T12:00:00'}
    return p


def test_parse_keeps_only_registered_places_and_known_relations():
    raw = ('{"links":[{"place":"공원","relation":"stated_destination","quote":"공원 간다고"},'
           '{"place":"없는 곳","relation":"stated_destination","quote":"x"},'
           '{"place":"시장","relation":"guess","quote":"시장"},'
           '{"place":"시장","relation":"usual_outing","quote":""}]}')
    assert prompts.parse_situation_link(raw, ['공원', '시장']) == [
        {'place': '공원', 'relation': 'stated_destination', 'quote': '공원 간다고'}]
    assert prompts.parse_situation_link('설명만', ['공원']) is None


def test_places_context_uses_notes_k_cited(sample):
    p = _ready(sample)
    context = {c['label']: c['context'] for c in situation_link.places_context(p)}
    assert context['공원'] == ['새 동네 공원에 가고 싶으나 가 본 적 없다.']
    assert context['시장'] == []


def test_quote_must_be_in_the_situation(sample, monkeypatch):
    p = _ready(sample)
    report = sample[1].model_copy(update={'situation': '아침에 공원 산책 간다고 나가셨어요'})
    monkeypatch.setattr(situation_link.midm, 'link_situation', lambda situation, places: [
        {'place': '공원', 'relation': 'stated_destination', 'quote': '공원 산책 간다고'},
        {'place': '시장', 'relation': 'stated_destination', 'quote': '시장 간다고'}])
    monkeypatch.setattr(situation_link.midm, 'check_claim', lambda notes, statement: True)
    out = situation_link.link(p, report)
    assert out['status'] == 'linked'
    assert [x['place'] for x in out['links']] == ['공원']
    assert [x['place'] for x in out['rejected']] == ['시장']


def test_link_must_pass_a_second_question(sample, monkeypatch):
    """원문 구절이 있어도 뜻이 이어지는지 다시 묻는다 — S10 '비 오는 오후, 우산을 두고 나가셨음'."""
    p = _ready(sample)
    report = sample[1].model_copy(update={'situation': '비 오는 오후, 우산을 두고 나가셨음.'})
    monkeypatch.setattr(situation_link.midm, 'link_situation', lambda situation, places: [
        {'place': '공원', 'relation': 'usual_outing', 'quote': '비 오는 오후, 우산을 두고 나가셨음.'}])
    asked = []
    monkeypatch.setattr(situation_link.midm, 'check_claim',
                        lambda notes, statement: asked.append((notes[0], statement)) or False)
    out = situation_link.link(p, report)
    assert out['links'] == [] and out['status'] == 'none'
    assert out['unconfirmed'][0]['check'] is False
    assert asked[0][0] == '신고 상황: 비 오는 오후, 우산을 두고 나가셨음.'
    assert "평소 하던 외출" in asked[0][1]


def test_link_is_cached_per_situation_and_failures_are_retried(sample, monkeypatch):
    p = _ready(sample)
    case = Case(id='c-link', report=sample[1].model_copy(update={'situation': '공원 간다고 하셨어요'}),
                lkp=sample[1].lkp, lkp_time=sample[1].lkp_time)
    calls = []
    answers = iter([None, [{'place': '공원', 'relation': 'stated_destination', 'quote': '공원 간다고'}]])
    monkeypatch.setattr(situation_link.midm, 'link_situation',
                        lambda situation, places: calls.append(1) or next(answers))
    monkeypatch.setattr(situation_link.midm, 'check_claim', lambda notes, statement: True)
    assert situation_link.cached(case, p) == []              # 판정 실패 — 캐시하지 않는다
    assert case.situation_links['status'] == 'unavailable'
    first = situation_link.cached(case, p)
    again = situation_link.cached(case, p)
    assert first == again == [{'place': '공원', 'relation': 'stated_destination', 'quote': '공원 간다고', 'check': True}]
    assert len(calls) == 2


def test_linked_place_is_the_incident_destination(sample):
    """사전 등록 뒤 몇 달이 지나도, 신고 상황에 적힌 오늘의 목적지는 사건 시점 목적지다."""
    from datetime import timedelta
    p = _ready(sample)
    p.created_at = sample[1].lkp_time - timedelta(days=60)   # 사건 두 달 전 사전 등록
    core = p.prepared_initial['core']
    core['goals']['시장'].update(value='current_statement', note_ids=['N2'])   # 등록 당시 한 번 말함
    p.prepared_initial['core'] = core
    links = [{'place': '시장', 'relation': 'stated_destination', 'quote': '시장 간다고'}]
    out = prep.apply_prepared(p, sample[1], sample[2], sample[3], links)
    goals = out.initial_interpretation['semantic_contract']['goals']
    assert goals['시장']['value'] == 'current_statement'
    assert '시장 간다고' in goals['시장']['explanation']
    assert out.initial_interpretation['situation_links'] == links
    without = prep.apply_prepared(p, sample[1], sample[2], sample[3])
    assert without.initial_interpretation['semantic_contract']['goals']['시장']['value'] == 'historical_only'


def test_usual_outing_marks_the_place_as_acted_on(sample):
    p = _ready(sample)
    links = [{'place': '시장', 'relation': 'usual_outing', 'quote': '늘 하던 산책'}]
    out = prep.apply_prepared(p, sample[1], sample[2], sample[3], links)
    assert out.initial_interpretation['semantic_contract']['goals']['시장']['value'] == 'recent_action'
