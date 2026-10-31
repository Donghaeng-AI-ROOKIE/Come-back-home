"""제보 목격 시각 — 구조화 계약(time_clock 말한 그대로 + time_meridiem)과 제보 흐름 끝까지.

11/01 01:22 KST 운영 실측: "킨텍스 제2전시장 정문 앞에서 1시 15분쯤 봤어요." 가
seen_at 22:15 KST 로 저장됐다(의도 01:15 KST). 원인은 두 겹이었다.
  1) 지시문이 time_clock 을 "24시간(오전/오후 반영)"으로 요구해 모델이 "1시 15분"을 13:15 로 냈다.
  2) time_resolve 가 시계 시각을 서버 시계(UTC)에 그대로 꽂았다.
이제 모델은 말한 숫자("01:15")와 말한 오전/오후(없으면 null)만 내고, 판단은 time_resolve 가 한다.
"""

import json

import pytest

from app.llm.tip_llm import (
    _TIP_STRUCTURE_SYSTEM,
    TipLLMClient,
    _stub_structure_tip,
    _stub_time_kind,
)
from app.phase1 import intake
from app.phase3 import tip_flow
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from tests.test_time_resolve import naive, utc_server  # noqa: F401 — 픽스처 재사용

MEASURED_TEXT = ("킨텍스 제2전시장 정문 앞에서 1시 15분쯤 봤어요. "
                 "할아버지 한 분이 혼자 두리번거리며 서성이고 계셨어요.")
KINTEX_HALL2 = GeoPoint(lat=37.6688, lng=126.7453)
NEAR_HALL2 = GeoPoint(lat=37.6690, lng=126.7458)   # 약 50m


def _client_returning(monkeypatch, payload: dict) -> TipLLMClient:
    client = TipLLMClient()
    monkeypatch.setattr(type(client), "is_stub", property(lambda self: False))
    monkeypatch.setattr(client, "chat", lambda *a, **k: json.dumps(payload, ensure_ascii=False))
    return client


# ── 실모델 응답 검증(스키마) ────────────────────────────────────────────────

@pytest.mark.parametrize(("text", "payload", "clock", "meridiem"), [
    ("1시 15분쯤", {"time_kind": "absolute", "time_clock": "01:15", "time_meridiem": None}, "01:15", None),
    ("오후 1시 15분쯤", {"time_kind": "absolute", "time_clock": "01:15", "time_meridiem": "pm"}, "01:15", "pm"),
    ("새벽 1시 15분", {"time_kind": "absolute", "time_clock": "1:15", "time_meridiem": "am"}, "1:15", "am"),
    ("13시 15분에", {"time_kind": "absolute", "time_clock": "13:15"}, "13:15", None),        # 필드 누락 = null
    ("오후 1시 15분", {"time_kind": "absolute", "time_clock": "01:15", "time_meridiem": "오후"}, "01:15", None),
    ("오후 1시 15분", {"time_kind": "absolute", "time_clock": "01:15", "time_meridiem": "PM"}, "01:15", None),
    ("오후 1시", {"time_kind": "absolute", "time_clock": "25:00", "time_meridiem": "pm"}, None, None),
    ("오후 1시", {"time_kind": "absolute", "time_clock": 115, "time_meridiem": "pm"}, None, None),
    ("5분 전에 오후", {"time_kind": "relative", "time_minutes_ago": 5, "time_clock": "01:15", "time_meridiem": "pm"},
     None, None),
    ("오후 아까", {"time_kind": "vague", "time_meridiem": "pm"}, None, None),
])
def test_structure_tip_validates_clock_and_meridiem(monkeypatch, text, payload, clock, meridiem):
    out = _client_returning(monkeypatch, {"specificity": "상", **payload}).structure_tip(text)
    assert out["time_clock"] == clock
    assert out["time_meridiem"] == meridiem


# ── 원문이 뒷받침하지 않는 시각 주장 지우기 (11-01 Mi:dm Mini 실호출 사례) ──────────────

@pytest.mark.parametrize(("text", "payload", "want"), [
    # 원문에 오후 말이 없는데 모델이 pm 을 붙였다 → null(시점으로 고른다)
    ("4시쯤 호수공원 근처에서 봤어요.", {"time_kind": "absolute", "time_clock": "04:00", "time_meridiem": "pm"},
     ("absolute", "04:00", None, None)),
    ("아까 12시 반쯤 라페스타 앞에서 봤어요.", {"time_kind": "absolute", "time_clock": "12:30", "time_meridiem": "pm"},
     ("absolute", "12:30", None, None)),
    # 원문에 있으면 그대로
    ("낮 12시쯤 라페스타에서 봤어요.", {"time_kind": "absolute", "time_clock": "12:00", "time_meridiem": "pm"},
     ("absolute", "12:00", "pm", None)),
    ("새벽 1시쯤 호수공원에서 봤어요.", {"time_kind": "absolute", "time_clock": "01:00", "time_meridiem": "am"},
     ("absolute", "01:00", "am", None)),
    ("오후 1시 15분쯤 킨텍스역에서 봤어요.", {"time_kind": "absolute", "time_clock": "13:15", "time_meridiem": "pm"},
     ("absolute", "13:15", "pm", None)),
    # 말하지 않은 24시간제 변환은 말한 숫자로 되돌린다
    (MEASURED_TEXT, {"time_kind": "absolute", "time_clock": "13:15", "time_meridiem": None},
     ("absolute", "01:15", None, None)),
    ("13시 20분에 킨텍스역 앞에서 봤어요.", {"time_kind": "absolute", "time_clock": "13:20", "time_meridiem": None},
     ("absolute", "13:20", None, None)),
    # 경과 말이 없는데 relative → vague ("전시장"의 '전'은 근거가 아니다)
    ("밤 11시쯤 일산호수공원 입구에서 봤어요.", {"time_kind": "relative", "time_minutes_ago": 0},
     ("vague", None, None, None)),
    ("킨텍스 제2전시장 앞에서 봤어요.", {"time_kind": "relative", "time_minutes_ago": 10},
     ("vague", None, None, None)),
    ("1시간 전쯤 킨텍스 정문에서 봤어요.", {"time_kind": "relative", "time_minutes_ago": 60},
     ("relative", None, None, 60)),
    ("30분쯤 전에 봤어요.", {"time_kind": "relative", "time_minutes_ago": 30}, ("relative", None, None, 30)),
    ("한 시간 전에 봤어요.", {"time_kind": "relative", "time_minutes_ago": 60}, ("relative", None, None, 60)),
    ("방금 킨텍스역 2번 출구에서 봤어요.", {"time_kind": "relative", "time_minutes_ago": 0},
     ("relative", None, None, 0)),
])
def test_unsupported_time_claims_are_dropped(monkeypatch, text, payload, want):
    out = _client_returning(monkeypatch, {"specificity": "상", **payload}).structure_tip(text)
    assert (out["time_kind"], out["time_clock"], out["time_meridiem"], out["time_minutes_ago"]) == want


def test_structure_tip_failure_has_no_meridiem(monkeypatch):
    client = TipLLMClient()
    monkeypatch.setattr(type(client), "is_stub", property(lambda self: False))

    def _boom(*a, **k):
        raise RuntimeError("HTTP 410 Gone")

    monkeypatch.setattr(client, "chat", _boom)
    out = client.structure_tip(MEASURED_TEXT)
    assert out["time_clock"] is None and out["time_meridiem"] is None


def test_prompt_asks_for_spoken_clock_not_24h_conversion():
    # 예전 지시문 "HH:MM 24시간(오전/오후 반영)"이 "1시 15분" → 13:15 를 만들었다.
    assert "24시간(오전/오후 반영)" not in _TIP_STRUCTURE_SYSTEM
    assert "time_meridiem" in _TIP_STRUCTURE_SYSTEM
    assert "12를 더하거나 빼지 마라" in _TIP_STRUCTURE_SYSTEM


# ── 스텁(키 없는 개발 모드): 실모델과 같은 계약 ────────────────────────────────

@pytest.mark.parametrize(("text", "kind", "clock", "meridiem"), [
    (MEASURED_TEXT, "absolute", "01:15", None),
    ("오후 1시 15분쯤 봤어요", "absolute", "01:15", "pm"),
    ("오전 9시에 봤어요", "absolute", "09:00", "am"),
    ("새벽 2시쯤 역 앞에서", "absolute", "02:00", "am"),
    ("저녁 7시 반쯤", "absolute", "07:30", "pm"),
    ("밤 11시쯤", "absolute", "11:00", None),          # "밤"은 자정 앞뒤로 갈려 null
    ("3시쯤 봤어요", "absolute", "03:00", None),
    ("21시 40분에 봤어요", "absolute", "21:40", None),
    ("2시간 전에 봤어요", "relative", None, None),
    ("2시간쯤 헤매다가 봤어요", "vague", None, None),   # 경과 시간은 시계 시각이 아님
    ("시장 앞에서 봤어요", "vague", None, None),        # "시장"의 '시'는 시각이 아님(예전과 같음)
    ("편의점 앞에서 봤어요", "none", None, None),
])
def test_stub_time_kind(text, kind, clock, meridiem):
    out = _stub_time_kind(text)
    assert (out["time_kind"], out["time_clock"], out["time_meridiem"]) == (kind, clock, meridiem)


def test_stub_relative_unchanged():
    assert _stub_time_kind("방금 봤어요")["time_minutes_ago"] == 0
    assert _stub_time_kind("30분 전에 봤어요")["time_minutes_ago"] == 30
    assert _stub_time_kind("2시간 전에 봤어요")["time_minutes_ago"] == 120


def test_stub_structure_has_full_contract():
    out = _stub_structure_tip(MEASURED_TEXT)
    assert {"time_kind", "time_minutes_ago", "time_clock", "time_meridiem"} <= out.keys()
    assert out["time_kind"] == "absolute"


# ── 제보 흐름 끝까지(UTC 서버, 실측 값) ───────────────────────────────────────

@pytest.fixture()
def kintex_case(monkeypatch):
    from app import llm

    monkeypatch.setattr(type(llm.tip_llm), "is_stub", property(lambda self: True))
    return intake.create_report(
        missing_type=PersonaType.dementia, lkp=KINTEX_HALL2,
        lkp_time=naive("2026-10-31T12:30:00"))   # 21:30 KST 신고 = UTC naive 12:30


@pytest.mark.usefixtures("utc_server")
def test_measured_tip_gets_0115_kst(kintex_case):
    tip = tip_flow.process_tip(
        kintex_case, text=MEASURED_TEXT, location=NEAR_HALL2,
        now=naive("2026-10-31T16:21:58"), defer_heavy=True)
    assert tip.seen_at == naive("2026-10-31T16:15:00")   # 01:15 KST, 예전 13:15(22:15 KST)


@pytest.mark.usefixtures("utc_server")
def test_measured_moment_with_explicit_pm_is_not_anchored(kintex_case):
    # "오후 1시 15분"은 13:15 KST — 실종(21:30 KST) 이전 목격이라 새 앵커가 될 수 없다.
    tip = tip_flow.process_tip(
        kintex_case, text="킨텍스 제2전시장 정문 앞에서 오후 1시 15분쯤 봤어요.",
        location=NEAR_HALL2, now=naive("2026-10-31T16:21:58"), defer_heavy=True, force=True)
    assert tip.seen_at is None
