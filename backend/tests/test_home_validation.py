"""온보딩 집 주소 — 답을 받은 **그 턴에** 지도로 확인한다 (2026-09-26).

배경: "포켓몬랜드"처럼 지도에 없는 곳을 답해도 표면 검사(_valid_home_text)만 통과하면
다음 질문으로 넘어갔고, 10여 개 질문을 다 끝낸 요약 확인 뒤 finalize 에서야 "집 위치
미확보"가 떴다. 카카오 키워드 검색이 퍼지해서 "우리집"→강남 식당처럼 **엉뚱한 좌표가
조용히** 잡히는 경우도 실측됐다 — 상호만 적은 답은 지역을 함께 물어야 한다.
"""

from app import storage
from app.geo import geocode
from app.geo.geocode import GazetteerGeocoder, GeoResult, KakaoGeocoder
from app.phase0 import interview
from app.phase0.slots import slot_by_key, slots_for
from app.schemas.common import GeoPoint
from app.schemas.persona import InterviewSession, PersonaType


class _FakeGeo:
    """질의 → 결과 표. 호출 기록으로 finalize 가 재조회하지 않는지도 본다."""

    def __init__(self, table: dict):
        self.table = table
        self.calls: list[str] = []

    def locate(self, query, anchor=None):
        self.calls.append(query)
        return self.table.get(query)


_JEONGNEUNG = GeoResult(GeoPoint(lat=37.6076, lng=127.0133), precision="address",
                        source="kakao", matched="서울 성북구 정릉동", address="서울 성북구 정릉동")
_FUZZY_POI = GeoResult(GeoPoint(lat=37.5030, lng=127.0373), precision="poi", source="kakao",
                       matched="우리집", address="서울 강남구 역삼동 12-3")
_CENTER_POI = GeoResult(GeoPoint(lat=37.6047, lng=127.0106), precision="poi", source="kakao",
                        matched="정릉2동주민센터", address="서울 성북구 보국문로 12")


def _fake_extractor(monkeypatch):
    """스텁 Mi:dm 은 규칙(_HOME_RE)으로만 home 을 뽑아 '포켓몬랜드'를 못 만든다 —
    실제 Mi:dm 이 그러듯 마지막 발화(조사 제거)를 home 으로 돌려주는 추출기."""
    original = interview._extract_tracked

    def _extract(session, slot):
        if slot.key != "home":
            return original(session, slot)          # 이름·나이 등은 스텁(규칙 폴백) 그대로
        text = interview._strip_tail_particles(session.messages[-1]["text"])
        return {"fields": {"home": text}, "attraction_points": [],
                "behavior_notes": [], "slot_filled": True}
    monkeypatch.setattr(interview, "_extract_tracked", _extract)


def _at_home_question() -> InterviewSession:
    """이름·나이 답변 직후 — 다음 질문이 집(고정 Q2)인 상태."""
    s = interview.start_interview("보호자", PersonaType.dementia)
    out = interview.answer_interview(s.id, "김순자님이고 78세예요")
    assert out.prev_target_key == "home"
    return out


# ── 지도에 없는 곳 → 그 자리에서 되묻기 ─────────────────────────────

def test_unknown_place_is_reasked_immediately(monkeypatch):
    geo = _FakeGeo({"성북구 정릉동": _JEONGNEUNG})
    monkeypatch.setattr(interview, "_GEO", geo)
    _fake_extractor(monkeypatch)
    s = _at_home_question()

    out = interview.answer_interview(s.id, "포켓몬랜드요")
    assert "home" not in out.draft_fields and "home" not in out.filled_keys
    assert out.prev_target_key == "home"                       # 다음 답도 집으로 추출
    assert out.asked_counts["home"] < interview.MAX_ASKS_PER_SLOT   # 소진 아님
    assert out.home_check_failures == 1
    last = out.messages[-1]["text"]
    assert "포켓몬랜드" in last and "지도에서 찾지 못했어요" in last

    # 제대로 답하면 통과 — 좌표가 세션에 남고 다음 질문으로 넘어간다
    out = interview.answer_interview(s.id, "성북구 정릉동이에요")
    assert out.draft_fields["home"] == "성북구 정릉동" and "home" in out.filled_keys
    assert out.home_geo["query"] == "성북구 정릉동"
    assert abs(out.home_geo["lat"] - 37.6076) < 1e-6
    assert out.prev_target_key != "home"


def test_fuzzy_poi_without_region_asks_for_region(monkeypatch):
    """'우리집'이 강남 식당 POI 로 걸려도 받지 않는다 — 지역 표기가 없으면 되묻는다."""
    geo = _FakeGeo({"우리집": _FUZZY_POI, "강남구 역삼동": _JEONGNEUNG})
    monkeypatch.setattr(interview, "_GEO", geo)
    _fake_extractor(monkeypatch)
    s = _at_home_question()

    out = interview.answer_interview(s.id, "우리집이요")
    assert "home" not in out.draft_fields
    assert "위치를 특정하기 어려워요" in out.messages[-1]["text"]

    out = interview.answer_interview(s.id, "강남구 역삼동 우리집이요")   # 사다리가 '강남구 역삼동'으로 내려간다
    assert out.draft_fields["home"] == "강남구 역삼동 우리집"
    assert out.home_geo["precision"] == "address"


def test_poi_with_region_token_is_accepted_and_echoed_in_summary(monkeypatch):
    geo = _FakeGeo({"정릉2동 주민센터": _CENTER_POI})
    monkeypatch.setattr(interview, "_GEO", geo)
    _fake_extractor(monkeypatch)
    s = _at_home_question()

    out = interview.answer_interview(s.id, "정릉2동 주민센터 근처요")
    assert out.draft_fields["home"] == "정릉2동 주민센터 근처"
    assert out.home_geo["address"] == "서울 성북구 보국문로 12"
    assert "• 지내시는 곳: 정릉2동 주민센터 근처 (지도 확인: 서울 성북구 보국문로 12)" \
        in interview.build_summary(out)


def test_geocoder_outage_does_not_trap_guardian(monkeypatch):
    """지오코더가 전부 미탐이면 상한 뒤 미확인 상태로 통과 — 요약이 그 사실을 알린다."""
    monkeypatch.setattr(interview, "_GEO", _FakeGeo({}))
    _fake_extractor(monkeypatch)
    s = _at_home_question()

    for _ in range(interview._HOME_CHECK_MAX_FAILURES):
        out = interview.answer_interview(s.id, "성북구 정릉동이에요")
        assert "home" not in out.draft_fields and out.prev_target_key == "home"
    out = interview.answer_interview(s.id, "성북구 정릉동이에요")
    assert out.draft_fields["home"] == "성북구 정릉동" and "home" in out.filled_keys
    assert out.home_geo is None
    assert "(지도에서 아직 확인되지 않음)" in interview.build_summary(out)


# ── 확인 게이트 정정 ─────────────────────────────────────────────────

def test_correction_to_unknown_place_reasks_instead_of_resummarizing(monkeypatch):
    geo = _FakeGeo({"성북구 정릉동": _JEONGNEUNG})
    monkeypatch.setattr(interview, "_GEO", geo)
    _fake_extractor(monkeypatch)

    class _Hit:
        slot = slot_by_key("home")
        similarity = 0.9
    monkeypatch.setattr(interview.retrieval, "rank_next_slots", lambda *a, **k: ([_Hit()], []))

    s = InterviewSession(
        id="home-corr", guardian_name="보호자", persona_type=PersonaType.dementia,
        draft_fields={"name": "김순자", "age": "78세", "home": "성북구 정릉동"},
        home_geo={"query": "성북구 정릉동", "lat": 37.6076, "lng": 127.0133,
                  "precision": "address", "source": "kakao",
                  "matched": "서울 성북구 정릉동", "address": "서울 성북구 정릉동"},
        filled_keys=[sp.key for sp in slots_for(PersonaType.dementia)],
        awaiting_confirmation=True, asked_more_places=True,
    )
    storage.interviews.save(s.id, s)

    out = interview.answer_interview(s.id, "포켓몬랜드예요")
    assert not out.done and not out.awaiting_confirmation
    assert "home" not in out.draft_fields and out.prev_target_key == "home"
    assert "지도에서 찾지 못했어요" in out.messages[-1]["text"]

    out = interview.answer_interview(s.id, "성북구 정릉동이에요")
    assert out.awaiting_confirmation                       # 요약 확인 재진입
    out = interview.answer_interview(s.id, "네 맞아요")
    assert out.done and out.persona_id


# ── finalize 는 확인된 좌표를 그대로 쓴다 ──────────────────────────────

def test_finalize_reuses_checked_coordinate_without_requery():
    geo = _FakeGeo({})
    s = InterviewSession(
        id="home-fin", guardian_name="보호자", persona_type=PersonaType.dementia,
        draft_fields={"name": "김순자", "age": "78세", "home": "성북구 정릉동"},
        home_geo={"query": "성북구 정릉동", "lat": 37.6076, "lng": 127.0133,
                  "precision": "address", "source": "kakao",
                  "matched": "서울 성북구 정릉동", "address": "서울 성북구 정릉동"},
    )
    p = interview.finalize_persona(s, geocoder=geo)
    assert abs(p.home.lat - 37.6076) < 1e-6 and abs(p.home.lng - 127.0133) < 1e-6
    assert geo.calls == []                                  # 재조회 없음


def test_finalize_ignores_stale_home_geo_after_text_changed():
    """정정으로 텍스트가 바뀌었는데 옛 좌표가 남아 있으면 무시하고 다시 찾는다."""
    s = InterviewSession(
        id="home-stale", guardian_name="보호자", persona_type=PersonaType.dementia,
        draft_fields={"name": "김순자", "age": "78세", "home": "화곡동"},
        home_geo={"query": "성북구 정릉동", "lat": 37.6076, "lng": 127.0133,
                  "precision": "address", "source": "kakao", "matched": None, "address": None},
    )
    p = interview.finalize_persona(s, geocoder=GazetteerGeocoder())
    assert abs(p.home.lat - 37.5417) < 1e-3                  # 화곡동 (gazetteer)


# ── 지역 표기 판정 ───────────────────────────────────────────────────

def test_region_token_detection():
    yes = ["하남시 더샵센트럴뷰", "정릉동이요", "서울 중랑구 면목동", "면목로 12에 살아요",
           "정릉2동 주민센터 근처", "대전 중구", "서울특별시 성북구"]
    no = ["우리집", "포켓몬랜드", "잠시 머무는 곳", "친구네", "101동 1203호", "바로 옆 운동장"]
    assert all(interview._has_region_token(t) for t in yes), \
        [t for t in yes if not interview._has_region_token(t)]
    assert not any(interview._has_region_token(t) for t in no), \
        [t for t in no if interview._has_region_token(t)]


def test_kakao_keyword_result_carries_address(monkeypatch):
    """되비추기용 주소 — 키워드 검색은 상호만 돌려주면 엉뚱한 곳에 걸려도 알 길이 없다."""
    docs = [{"x": "127.0373", "y": "37.5030", "place_name": "우리집",
             "address_name": "서울 강남구 역삼동 12-3", "road_address_name": "서울 강남구 테헤란로 1"}]
    monkeypatch.setattr(KakaoGeocoder, "_get", lambda self, url, q, extra=None: docs)
    r = KakaoGeocoder("k").locate("우리집")
    assert r.precision == "poi" and r.matched == "우리집"
    assert r.address == "서울 강남구 테헤란로 1"
    assert geocode.has_region_token("서울 강남구 테헤란로 1")


# ── 추출기가 빈손일 때 — 발화 자체를 후보로 (라이브 실측 2026-09-26) ─────────

def test_empty_extraction_still_reasks_for_unknown_place(monkeypatch):
    """Mi:dm 2.5 는 '포켓몬랜드'를 아예 추출하지 않는다 — 그래도 다음 슬롯으로 넘어가면 안 된다.

    스텁 추출은 빈손이고 규칙(_HOME_RE)도 안 걸리므로 이 테스트는 라이브와 같은 조건이다.
    """
    monkeypatch.setattr(interview, "_GEO", _FakeGeo({"성북구 정릉동": _JEONGNEUNG}))
    s = _at_home_question()

    out = interview.answer_interview(s.id, "포켓몬랜드")
    assert out.prev_target_key == "home"                       # 구버전: routine_destinations
    assert "'포켓몬랜드'은(는) 지도에서 찾지 못했어요" in out.messages[-1]["text"]
    assert "home" not in out.draft_fields

    out = interview.answer_interview(s.id, "성북구 정릉동이에요")
    assert out.draft_fields["home"] == "성북구 정릉동" and out.prev_target_key != "home"


def test_empty_extraction_fills_home_when_utterance_geocodes(monkeypatch):
    """추출기·규칙이 다 놓친 답이라도 지도에 잡히면 그 발화로 채운다(규칙 폴백과 같은 자격)."""
    poi = GeoResult(GeoPoint(lat=37.5440, lng=127.2033), precision="poi", source="kakao",
                    matched="하남더샵센트럴뷰", address="경기 하남시 하남대로 856")
    monkeypatch.setattr(interview, "_GEO", _FakeGeo({"하남시 하남더샵센트럴뷰": poi}))
    s = _at_home_question()
    out = interview.answer_interview(s.id, "하남시 하남더샵센트럴뷰요")
    assert out.draft_fields["home"] == "하남시 하남더샵센트럴뷰" and "home" in out.filled_keys
    assert out.home_geo["address"] == "경기 하남시 하남대로 856"
    assert out.prev_target_key != "home"


def test_sentence_answer_is_reasked_without_quoting(monkeypatch):
    monkeypatch.setattr(interview, "_GEO", _FakeGeo({}))
    s = _at_home_question()
    out = interview.answer_interview(s.id, "집에 주로 계세요")
    assert out.prev_target_key == "home"
    assert out.messages[-1]["text"].startswith("주소를 알아듣지 못했어요")


def test_ignorance_and_yes_are_not_treated_as_address_attempts(monkeypatch):
    geo = _FakeGeo({})
    monkeypatch.setattr(interview, "_GEO", geo)
    s = _at_home_question()
    out = interview.answer_interview(s.id, "잘 모르겠어요")
    assert geo.calls == []                                     # 지도 조회조차 안 한다
    assert "지도에서 찾지 못했어요" not in out.messages[-1]["text"]


def test_rule_extract_does_not_clip_word_ending_in_admin_suffix():
    """'우리집이요' → 규칙이 '우리'(…리)를 집으로 잡던 실측. 낱말 경계를 본다."""
    assert interview._rule_extract_fields("home", "우리집이요") == {}
    assert interview._rule_extract_fields("home", "우리 동네요") == {}
    assert interview._rule_extract_fields("home", "정릉동이에요")["home"] == "정릉동"
    assert interview._rule_extract_fields("home", "서울 성북구 정릉동에 살아요")["home"] == "성북구 정릉동"  # '서울'은 시/도 접미사가 없어 원래부터 빠진다
    assert interview._rule_extract_fields("home", "면목동 12")["home"] == "면목동 12"


# ── 끌림점 과다추출 가드 (run_eval 2.5 추적, 2026-09-26) ──────────────────

def _apply(session, slot_key, labels, utterance):
    interview._apply_extraction(
        session, slot_by_key(slot_key),
        {"fields": {}, "attraction_points": [{"label": lb, "area_text": ""} for lb in labels],
         "behavior_notes": [], "slot_filled": True},
        utterance=utterance)
    return [a["label"] for a in session.draft_attractions]


def _blank_session(sid):
    return InterviewSession(id=sid, guardian_name="보호자", persona_type=PersonaType.dementia,
                            draft_fields={"name": "김순자", "age": "78세", "home": "성북구 정릉동"})


def test_home_turn_locator_landmark_is_not_an_attraction():
    """'정릉초등학교 근처예요' — 학교는 집의 기준점이지 가는 곳이 아니다."""
    s = _blank_session("over-1")
    assert _apply(s, "home", ["정릉초등학교"], "성북구 정릉동이요. 정릉초등학교 근처예요.") == []


def test_home_turn_daycare_is_kept():
    """집 턴이라도 '주간보호센터에 계십니다'는 실제로 머무는 곳 — 슬롯 probes 가 묻는 것."""
    s = _blank_session("over-2")
    assert _apply(s, "home", ["주간보호센터"],
                  "면목동 ○○아파트에 살고, 주중 낮에는 주간보호센터에 계십니다.") == ["주간보호센터"]


def test_label_absent_from_utterance_is_dropped():
    """복약 답변에 '면목동 방앗간'이 붙어 오면 이전 대화 재추출 — 버린다."""
    s = _blank_session("over-3")
    assert _apply(s, "medication", ["면목동 방앗간"],
                  "혈압약이랑 치매약을 아침저녁으로 드세요. 거르면 어지러워하세요.") == []


def test_paraphrased_label_with_shared_token_is_kept():
    """'옛 방앗간'은 발화("방앗간 문 열러…")에 토큰이 있으니 살린다 — 재서술 라벨 허용."""
    s = _blank_session("over-4")
    assert _apply(s, "autobiographical_destination_pull", ["옛 방앗간"],
                  "예전에 면목동에서 방앗간을 오래 하셨는데, 아직도 새벽에 방앗간 문 열러 가야 한다고 나가려 하세요.") == ["옛 방앗간"]


def test_grounding_skipped_without_utterance():
    """발화 없이 직접 주입하는 호출(테스트·마이그레이션)은 그대로 통과."""
    s = _blank_session("over-5")
    assert _apply(s, "medication", ["아무데나"], "") == ["아무데나"]
