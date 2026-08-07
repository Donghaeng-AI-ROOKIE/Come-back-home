"""확인 요약의 보호자 발화를 짧게 줄여 보여준다 (표시 전용).

보호자 발화가 통째로 나열되면 확인 화면이 읽히지 않는다는 피드백(2026-08-07):
  "약을 거르시면 많이 어지러워 하세요"  →  "거르면 어지럼증"

**저장은 그대로다** — draft_behaviors·slot_quotes 는 축 채점 근거와 발화 인용
검증이 쓰므로 손대면 안 된다. 화면 문자열만 바꾼다.
"""

from app.phase0 import interview, prompts
from app.phase0.slots import slot_by_key
from app.schemas.persona import InterviewSession, PersonaType

_MED = slot_by_key("medication")
_LOST = slot_by_key("lost_behavior")
_RAW_MED = "약을 거르시면 많이 어지러워 하세요"
_RAW_LOST = "그 자리에 가만히 서계세요"


def _session(**kw) -> InterviewSession:
    base = dict(
        id="dg1", guardian_name="보호자", persona_type=PersonaType.dementia,
        draft_fields={"name": "김순자", "age": "82세", "home": "마포구 백범로 35"},
        draft_behaviors=[f"{_MED.label}: {_RAW_MED}", f"{_LOST.label}: {_RAW_LOST}"],
        slot_notes={"medication": [_RAW_MED], "lost_behavior": [_RAW_LOST]},
        slot_quotes={"medication": [_RAW_MED]},
        filled_keys=["identity", "home", "medication", "lost_behavior"],
    )
    return InterviewSession(**{**base, **kw})


def _fake(mapping: dict[str, str]):
    return lambda notes: [mapping.get(n, "") for n in notes]


# ── 표시 ─────────────────────────────────────────────────────────────

def test_summary_shows_digest_not_raw(monkeypatch):
    s = _session()
    monkeypatch.setattr(interview.midm, "condense_notes",
                        _fake({_RAW_MED: "거르면 어지럼증", _RAW_LOST: "제자리에 머무름"}))
    text = interview.build_summary(s)
    assert "거르면 어지럼증" in text
    assert "제자리에 머무름" in text
    assert _RAW_MED not in text
    assert _RAW_LOST not in text


def test_storage_is_untouched(monkeypatch):
    """압축은 화면 전용 — 저장된 근거는 원문 그대로 남아야 한다."""
    s = _session()
    monkeypatch.setattr(interview.midm, "condense_notes",
                        _fake({_RAW_MED: "거르면 어지럼증", _RAW_LOST: "제자리에 머무름"}))
    interview.build_summary(s)
    assert s.draft_behaviors == [f"{_MED.label}: {_RAW_MED}", f"{_LOST.label}: {_RAW_LOST}"]
    assert s.slot_notes["medication"] == [_RAW_MED]
    assert s.slot_quotes["medication"] == [_RAW_MED]


def test_falls_back_to_raw_when_llm_silent(monkeypatch):
    """스텁·실패면 원문을 그대로 보여준다(빈칸이 되면 안 된다)."""
    s = _session()
    monkeypatch.setattr(interview.midm, "condense_notes", lambda notes: [])
    text = interview.build_summary(s)
    assert _RAW_MED in text


def test_rejects_digest_that_is_not_shorter(monkeypatch):
    """길이가 안 줄었거나 너무 길면 압축이 아니다 — 원문 유지."""
    s = _session()
    monkeypatch.setattr(interview.midm, "condense_notes",
                        _fake({_RAW_MED: _RAW_MED + " (정리)", _RAW_LOST: "가" * 40}))
    text = interview.build_summary(s)
    assert _RAW_MED in text
    assert _RAW_LOST in text


def test_digest_is_cached_and_stable(monkeypatch):
    """재렌더에서 다시 부르지 않고 문구도 안 흔들린다(정정 왕복 대비)."""
    s = _session()
    calls: list = []

    def _once(notes):
        calls.append(list(notes))
        return ["거르면 어지럼증", "제자리에 머무름"]

    monkeypatch.setattr(interview.midm, "condense_notes", _once)
    first = interview.build_summary(s)
    second = interview.build_summary(s)
    assert first == second
    assert len(calls) == 1                       # 두 번째 렌더는 캐시 사용
    assert s.note_digests[_RAW_MED] == "거르면 어지럼증"


# ── 파서 ─────────────────────────────────────────────────────────────

def test_parse_digest_pairs_by_index():
    """순서가 아니라 번호로 짝을 맞춘다 — 밀린 줄이 엉뚱한 노트에 붙으면 안 된다."""
    raw = '{"digests":[{"i":2,"text":"나"},{"i":1,"text":"가"}]}'
    assert prompts.parse_digest(raw, 2) == ["가", "나"]


def test_parse_digest_rejoins_split_lines():
    """모델이 두 문장짜리 노트를 두 줄로 쪼개도 도로 합친다(실측 8줄 → 9줄)."""
    raw = ('{"digests":[{"i":1,"text":"동네 안 혼자 1시간"},'
           '{"i":1,"text":"버스 못 탐"},{"i":2,"text":"제자리에 머무름"}]}')
    assert prompts.parse_digest(raw, 2) == ["동네 안 혼자 1시간·버스 못 탐", "제자리에 머무름"]


def test_parse_digest_missing_index_stays_empty():
    """빠진 자리는 "" — 호출자가 원문을 그대로 보여준다."""
    assert prompts.parse_digest('{"digests":[{"i":1,"text":"가"}]}', 2) == ["가", ""]
    assert prompts.parse_digest("설명만 돌려줌", 2) == []
    assert prompts.parse_digest('{"digests":[{"i":9,"text":"가"}]}', 2) == ["", ""]
