"""되묻기 답변에서 지명만 뽑아 지역 표기로 쓴다 — 라이브 실측 2026-08-07.

  🙋 예전에 가게를 하셨던 곳에 가야 한다는 말을 자주 합니다   → label='예전 가게'
  🤖 '예전 가게'은 어느 동네인가요?
  🙋 망원시장에서 생선가게를 하셨어요
  → area_text='망원시장에서 생선가게를 하셨어' (문장 통째)

라벨('예전 가게')도 지역 표기(문장)도 지오코딩이 안 돼 finalize 가 그 장소를
버렸다 — 요약에는 보이는데 **등록정보에서는 사라진다.** 요약에도 문장이 찍혀 어색했다.
"""

from app.geo.geocode import GazetteerGeocoder, to_attraction_points
from app.phase0 import interview
from app.schemas.persona import GeoPoint, InterviewSession, PersonaType

_ASK = "'예전 가게'은 어느 동네인가요? 동 이름이나 근처 건물·가게 이름이면 됩니다."


def _pending(label: str = "예전 가게", area: str = "") -> InterviewSession:
    return InterviewSession(
        id="pa1", guardian_name="보호자", persona_type=PersonaType.dementia,
        pending_area_label=label,
        draft_attractions=[{"label": label, "area_text": area,
                            "place_type": "workplace", "evidence": "mention_only",
                            "origin_slot": "autobiographical_destination_pull"}],
        messages=[{"role": "assistant", "text": _ASK}])


def _area(s: InterviewSession) -> str:
    return s.draft_attractions[0]["area_text"]


# ── 지명 추출 ────────────────────────────────────────────────────────

def test_place_token_wins_over_whole_sentence():
    s = _pending()
    interview._resolve_pending_area(s, "망원시장에서 생선가게를 하셨어요")
    assert _area(s) == "망원시장"


def test_various_place_suffixes():
    for utterance, expected in [
        ("서강대학교 근처에서 일하셨어요", "서강대학교"),
        ("합정역 바로 앞이었어요", "합정역"),
        ("망원시장 안쪽에서 장사하셨어요", "망원시장"),
    ]:
        s = _pending()
        interview._resolve_pending_area(s, utterance)
        assert _area(s) == expected, utterance


def test_plain_dong_answer_still_works():
    """지명 접미어가 없는 동 이름 답변은 종전 경로 그대로."""
    s = _pending()
    interview._resolve_pending_area(s, "마포구 상암동이에요")
    assert _area(s) == "마포구 상암동"


def test_sentence_without_place_is_rejected():
    s = _pending()
    interview._resolve_pending_area(s, "거기서 오래 일하셨어요")
    assert _area(s) == ""


def test_ignorance_is_rejected():
    s = _pending()
    interview._resolve_pending_area(s, "모르겠어요")
    assert _area(s) == ""


def test_valid_home_text_rejects_past_tense_sentence():
    """과거형 서술어도 문장 — 지역 표기로 받지 않는다."""
    assert not interview._valid_home_text("망원시장에서 생선가게를 하셨어요")
    assert not interview._valid_home_text("거기서 오래 일했어요")
    assert interview._valid_home_text("마포구 상암동")


# ── 이 수정이 실제로 장소를 살리는가 ─────────────────────────────────

def test_place_survives_finalize_geocoding():
    """지명이 지역 표기로 들어가면 라벨이 일반어여도 좌표가 나온다.

    라벨('예전 가게')은 어차피 지오코딩이 안 되므로, area_text 가 지명이어야
    to_attraction_points 의 후보('지역' 단독)가 걸린다. 실서비스 지오코더는
    문장 질의를 못 찾아 그대로 미해결 → finalize 에서 탈락한다.
    """
    geo = GazetteerGeocoder({"망원시장": GeoPoint(lat=37.5561, lng=126.9026)})
    anchor = GeoPoint(lat=37.5498, lng=126.9452)
    fixed = [{"label": "예전 가게", "area_text": "망원시장",
              "place_type": "workplace", "evidence": "mention_only"}]
    points, unresolved = to_attraction_points(fixed, geo, anchor=anchor)
    assert not unresolved
    assert [p.label for p in points] == ["예전 가게"]
    assert points[0].location.lat == 37.5561
