"""온보딩 집 주소 — 답이 **여러 곳**을 가리키면 그 자리에서 되묻는다 (2026-10-01).

배경: 지오코더는 첫 결과만 준다(size=1). "산남동"은 파주·청주에 있고 "마포구 스타벅스"는
15개 지점인데, 지역 표기가 있다는 이유로 첫 결과가 조용히 집으로 등록됐다(실측:
산남동→파주, 마포구 스타벅스→망원한강공원점). 요약의 "지도 확인:" 한 줄이 유일한
방어였다. 답이 가리키는 후보 집합을 세어 2곳 이상이면 한 번 되묻고, 0곳(첫 결과가
말한 지역 밖)이면 통과시키지 않는다.
"""

from app import storage
from app.geo import geocode
from app.geo.geocode import (
    ChainGeocoder, GazetteerGeocoder, GeoResult, HomeAlternative, KakaoGeocoder,
)
from app.phase0 import interview
from app.phase0.slots import slot_by_key, slots_for
from app.schemas.common import GeoPoint
from app.schemas.persona import InterviewSession, PersonaType
from tests.test_home_validation import _JEONGNEUNG, _FakeGeo, _at_home_question, _fake_extractor


class _FakeGeoAlt(_FakeGeo):
    """locate 표 + 후보 집합 표(걸린 질의 → HomeAlternative 목록 / [] / None)."""

    def __init__(self, table: dict, alts: dict):
        super().__init__(table)
        self.alts = alts

    def home_alternatives(self, res, text):
        return self.alts.get(res.query, None)


def _alt(label, address, lat, lng, precision="address"):
    return HomeAlternative(label=label, address=address, point=GeoPoint(lat=lat, lng=lng),
                           precision=precision)


_SANNAM_PAJU = GeoResult(GeoPoint(lat=37.7022, lng=126.6876), precision="address", source="kakao",
                         matched="경기 파주시 산남동", address="경기 파주시 산남동")
_SANNAM_ALTS = [_alt("경기 파주시", "경기 파주시 산남동", 37.7022, 126.6876),
                _alt("충북 청주시 서원구", "충북 청주시 서원구 산남동", 36.6178, 127.4643)]
_SBUX_MAPO = GeoResult(GeoPoint(lat=37.5546, lng=126.8962), precision="poi", source="kakao",
                       matched="스타벅스 망원한강공원점", address="서울 마포구 망원동 205-8")
_SBUX_MAPO_ALTS = [
    _alt("스타벅스 망원한강공원점", "서울 마포구 망원동 205-8", 37.5546, 126.8962, "poi"),
    _alt("스타벅스 홍대입구역사거리R점", "서울 마포구 서교동 353-5", 37.5567, 126.9236, "poi"),
    _alt("스타벅스 서교동사거리점", "서울 마포구 서교동 374-20", 37.5540, 126.9210, "poi"),
    _alt("스타벅스 홍대역점", "서울 마포구 동교동 159-1", 37.5575, 126.9251, "poi"),
    _alt("스타벅스 상수역점", "서울 마포구 상수동 329-1", 37.5476, 126.9227, "poi"),
    _alt("스타벅스 공덕오거리점", "서울 마포구 도화동 22", 37.5443, 126.9510, "poi"),
]
_SBUX_HAPJEONG_ALTS = [
    _alt("스타벅스 합정점", "서울 마포구 합정동 472", 37.5497, 126.9142, "poi"),
    _alt("스타벅스 합정푸르지오점", "서울 마포구 합정동 473", 37.5490, 126.9135, "poi"),
]


def _alt_session(monkeypatch, table, alts):
    monkeypatch.setattr(interview, "_GEO", _FakeGeoAlt(table, alts))
    _fake_extractor(monkeypatch)
    return _at_home_question()


# ── 인터뷰 왕복 ──────────────────────────────────────────────────────

def test_ambiguous_dong_lists_choices_then_number_picks(monkeypatch):
    s = _alt_session(monkeypatch, {"산남동": _SANNAM_PAJU}, {"산남동": _SANNAM_ALTS})

    out = interview.answer_interview(s.id, "산남동이요")
    last = out.messages[-1]["text"]
    assert "여러 곳이에요" in last and "1. 경기 파주시" in last and "2. 충북 청주시 서원구" in last
    assert "home" not in out.draft_fields and out.prev_target_key == "home"
    assert out.home_check_failures == 0                    # 실패가 아니라 되묻기
    assert out.home_choice_rounds == 1 and len(out.home_choices) == 2

    out = interview.answer_interview(s.id, "2번이요")
    assert out.draft_fields["home"] == "충북 청주시 서원구 산남동" and "home" in out.filled_keys
    assert abs(out.home_geo["lat"] - 36.6178) < 1e-6
    assert out.home_geo["query"] == out.draft_fields["home"]   # finalize 가 재조회하지 않는 조건
    assert out.prev_target_key != "home" and out.home_choices == [] and out.home_choice_rounds == 0
    assert "• 지내시는 곳: 충북 청주시 서원구 산남동" in interview.build_summary(out)


def test_choice_by_region_name_and_sido_alias(monkeypatch):
    for reply in ("청주요", "충청북도예요", "서원구"):
        s = _alt_session(monkeypatch, {"산남동": _SANNAM_PAJU}, {"산남동": _SANNAM_ALTS})
        interview.answer_interview(s.id, "산남동이요")
        out = interview.answer_interview(s.id, reply)
        assert out.draft_fields["home"] == "충북 청주시 서원구 산남동", reply


def test_unique_alternative_passes_without_asking(monkeypatch):
    s = _alt_session(monkeypatch, {"산남동": _SANNAM_PAJU}, {"산남동": _SANNAM_ALTS[:1]})
    out = interview.answer_interview(s.id, "산남동이요")
    assert out.draft_fields["home"] == "산남동" and out.prev_target_key != "home"


def test_backend_without_alternatives_keeps_first_result(monkeypatch):
    """후보 집합을 못 주는 백엔드(_FakeGeo·gazetteer) — 오늘과 똑같이 첫 결과 통과."""
    monkeypatch.setattr(interview, "_GEO", _FakeGeo({"산남동": _SANNAM_PAJU}))
    _fake_extractor(monkeypatch)
    out = interview.answer_interview(_at_home_question().id, "산남동이요")
    assert out.draft_fields["home"] == "산남동" and out.home_choice_rounds == 0


def test_unique_filtered_candidate_replaces_out_of_region_first_hit(monkeypatch):
    original = GeoResult(GeoPoint(lat=37.51, lng=127.10), precision="poi", source="kakao",
                         matched="보배반점 잠실점", address="서울 송파구 잠실동 1")
    valid = _alt("보배반점 길동점", "서울 강동구 길동 1", 37.54, 127.14, "poi")
    s = _alt_session(monkeypatch, {"강동구 보배반점": original}, {"강동구 보배반점": [valid]})
    out = interview.answer_interview(s.id, "강동구 보배반점이요")
    assert out.home_geo["address"] == valid.address
    assert out.home_geo["lat"] == valid.point.lat
    assert out.home_geo["lng"] == valid.point.lng
    assert out.home_geo["query"] == out.draft_fields["home"]
    assert original.address == "서울 송파구 잠실동 1"


def test_many_alternatives_ask_for_district_then_merge_refinement(monkeypatch):
    many = [_alt(f"{sido} 중앙동", f"{sido} 중앙동", 37.0 + i, 127.0) for i, sido in
            enumerate(("서울 관악구", "경기 과천시", "경기 성남시 중원구", "충북 제천시", "대전 동구", "강원 원주시"))]
    center = GeoResult(GeoPoint(lat=37.4842, lng=126.9498), precision="address", source="kakao",
                       matched="서울 관악구 중앙동", address="서울 관악구 중앙동")
    gwacheon = GeoResult(GeoPoint(lat=37.4292, lng=126.9877), precision="address", source="kakao",
                         matched="경기 과천시 중앙동", address="경기 과천시 중앙동")
    s = _alt_session(monkeypatch, {"중앙동": center, "과천시 중앙동": gwacheon},
                     {"중앙동": many, "과천시 중앙동": [many[1]]})

    out = interview.answer_interview(s.id, "중앙동이에요")
    last = out.messages[-1]["text"]
    assert "시·군·구를 함께" in last and "예: 서울 관악구 중앙동, 경기 과천시 중앙동" in last
    assert out.home_choices == [] and out.home_choice_rounds == 1

    out = interview.answer_interview(s.id, "과천시요")          # 보탬 → "과천시 중앙동" 재조회
    assert out.draft_fields["home"] == "과천시 중앙동" and "home" in out.filled_keys
    assert abs(out.home_geo["lat"] - 37.4292) < 1e-6 and out.prev_target_key != "home"


def test_poi_many_then_dong_refinement_lists_branches(monkeypatch):
    hapjeong = GeoResult(GeoPoint(lat=37.5497, lng=126.9142), precision="poi", source="kakao",
                         matched="스타벅스 합정점", address="서울 마포구 합정동 472")
    s = _alt_session(monkeypatch,
                     {"마포구 스타벅스": _SBUX_MAPO, "마포구 합정동 스타벅스": hapjeong},
                     {"마포구 스타벅스": _SBUX_MAPO_ALTS, "마포구 합정동 스타벅스": _SBUX_HAPJEONG_ALTS})

    out = interview.answer_interview(s.id, "마포구 스타벅스요")
    last = out.messages[-1]["text"]
    assert "'마포구'에 '스타벅스'이(가) 여러 곳이에요" in last
    assert "예: 마포구 망원동 스타벅스, 스타벅스 망원한강공원점" in last

    out = interview.answer_interview(s.id, "합정동이요")           # 상호를 잃지 않고 합친다
    last = out.messages[-1]["text"]
    assert "'마포구 합정동 스타벅스'에 해당하는 곳이 여러 곳" in last
    assert "1. 스타벅스 합정점" in last and "2. 스타벅스 합정푸르지오점" in last
    assert out.home_choice_rounds == 2

    out = interview.answer_interview(s.id, "합정점이요")
    assert out.draft_fields["home"] == "스타벅스 합정점" and "home" in out.filled_keys
    assert out.home_geo["address"] == "서울 마포구 합정동 472"
    assert "• 지내시는 곳: 스타벅스 합정점 (지도 확인: 서울 마포구 합정동 472)" \
        in interview.build_summary(out)


def test_poi_outside_stated_region_is_reasked(monkeypatch):
    songpa = GeoResult(GeoPoint(lat=37.51, lng=127.10), precision="poi", source="kakao",
                       matched="보배반점 잠실점", address="서울 송파구 잠실동 1")
    s = _alt_session(monkeypatch, {"강동구 보배반점": songpa}, {"강동구 보배반점": []})
    out = interview.answer_interview(s.id, "강동구 보배반점이요")
    assert "'강동구'에서는 '보배반점'을(를) 찾지 못했어요" in out.messages[-1]["text"]
    assert "home" not in out.draft_fields and out.home_check_failures == 1


def test_unmatched_choice_answer_is_treated_as_new_answer(monkeypatch):
    s = _alt_session(monkeypatch, {"산남동": _SANNAM_PAJU, "아 성북구 정릉동": _JEONGNEUNG},
                     {"산남동": _SANNAM_ALTS})
    interview.answer_interview(s.id, "산남동이요")
    out = interview.answer_interview(s.id, "아 성북구 정릉동이에요")
    assert out.draft_fields["home"] == "아 성북구 정릉동" and out.home_choices == []
    assert "home" in out.filled_keys and out.home_choice_rounds == 0


def test_choice_rounds_cap_then_first_result_is_accepted(monkeypatch):
    s = _alt_session(monkeypatch, {"산남동": _SANNAM_PAJU}, {"산남동": _SANNAM_ALTS})
    interview.answer_interview(s.id, "산남동이요")
    out = interview.answer_interview(s.id, "산남동이요")            # 보기와 안 맞고 보탬도 아님 → 2회째
    assert out.home_choice_rounds == 2 and "여러 곳이에요" in out.messages[-1]["text"]
    out = interview.answer_interview(s.id, "산남동이요")            # 상한 — 첫 결과(파주)로 통과
    assert out.draft_fields["home"] == "산남동" and abs(out.home_geo["lat"] - 37.7022) < 1e-6
    assert "(지도 확인: 경기 파주시 산남동)" in interview.build_summary(out)


def test_correction_to_ambiguous_dong_asks_before_resummary(monkeypatch):
    monkeypatch.setattr(interview, "_GEO", _FakeGeoAlt({"산남동": _SANNAM_PAJU}, {"산남동": _SANNAM_ALTS}))
    _fake_extractor(monkeypatch)

    class _Hit:
        slot = slot_by_key("home")
        similarity = 0.9
    monkeypatch.setattr(interview.retrieval, "rank_next_slots", lambda *a, **k: ([_Hit()], []))

    s = InterviewSession(
        id="home-amb-corr", guardian_name="보호자", persona_type=PersonaType.dementia,
        draft_fields={"name": "김순자", "age": "78세", "home": "성북구 정릉동"},
        home_geo={"query": "성북구 정릉동", "lat": 37.6076, "lng": 127.0133,
                  "precision": "address", "source": "kakao",
                  "matched": "서울 성북구 정릉동", "address": "서울 성북구 정릉동"},
        filled_keys=[sp.key for sp in slots_for(PersonaType.dementia)],
        awaiting_confirmation=True, asked_more_places=True,
    )
    storage.interviews.save(s.id, s)

    # 확인·정정 판정은 Mi:dm — 스텁은 '확인'이라 하므로 정정 결과를 직접 준다
    monkeypatch.setattr(interview.midm, "extract_correction",
                        lambda labels, text: {"intent": "correct", "fields": {"home": "산남동"}, "place_ops": []})
    out = interview.answer_interview(s.id, "집 주소가 틀렸어요, 산남동이에요")
    assert not out.awaiting_confirmation and "1. 경기 파주시" in out.messages[-1]["text"]
    out = interview.answer_interview(s.id, "1번")                 # 정정 뒤 보기 선택 → 요약 재진입
    assert out.draft_fields["home"] == "경기 파주시 산남동" and out.awaiting_confirmation


# ── 카카오 후보 집합: 묶음·필터 ───────────────────────────────────────

def _kakao_with(address_docs=(), keyword_docs=()):
    def _get(self, url, q, extra=None):
        return list(address_docs if url == self.ADDRESS_URL else keyword_docs)
    return _get


def _addr_doc(name, sido, sigungu, y="37.5", x="127.0"):
    return {"address_name": name, "x": x, "y": y,
            "address": {"region_1depth_name": sido, "region_2depth_name": sigungu}}


def _poi_doc(name, addr, y="37.5", x="127.0"):
    return {"place_name": name, "address_name": addr, "road_address_name": "", "x": x, "y": y}


def test_kakao_address_alternatives_group_by_district(monkeypatch):
    """면목동 7건은 전부 중랑구(행정동 변형) → 1묶음. 원시 건수로 세면 유일한 동네도 되묻는다."""
    docs = [_addr_doc(f"서울 중랑구 {n}", "서울", "중랑구") for n in
            ("면목동", "면목본동", "면목2동", "면목3.8동", "면목4동", "면목5동", "면목7동")]
    monkeypatch.setattr(KakaoGeocoder, "_get", _kakao_with(address_docs=docs))
    res = GeoResult(GeoPoint(lat=37.58, lng=127.09), precision="address", source="kakao", query="면목동")
    assert len(KakaoGeocoder("k").home_alternatives(res, "면목동")) == 1

    docs = [_addr_doc("경기 파주시 산남동", "경기", "파주시"),
            _addr_doc("충북 청주시 서원구 산남동", "충북", "청주시 서원구", y="36.6")]
    monkeypatch.setattr(KakaoGeocoder, "_get", _kakao_with(address_docs=docs))
    alts = KakaoGeocoder("k").home_alternatives(res, "산남동")
    assert [a.label for a in alts] == ["경기 파주시", "충북 청주시 서원구"]
    assert alts[1].address == "충북 청주시 서원구 산남동" and abs(alts[1].point.lat - 36.6) < 1e-9


def test_kakao_poi_alternatives_keep_only_stated_region(monkeypatch):
    """카카오는 동 접두어를 퍼지하게 다뤄 이웃 동을 섞는다 — 답의 지역 토큰을 전부 담은 지점만."""
    docs = [_poi_doc("스타벅스 합정점", "서울 마포구 합정동 472"),
            _poi_doc("스타벅스 합정푸르지오점", "서울 마포구 합정동 473"),
            _poi_doc("스타벅스 서교동사거리점", "서울 마포구 서교동 374-20"),
            _poi_doc("스타벅스 합정점", "서울 마포구 합정동 472")]        # 중복 제거
    monkeypatch.setattr(KakaoGeocoder, "_get", _kakao_with(keyword_docs=docs))
    res = GeoResult(GeoPoint(lat=37.55, lng=126.91), precision="poi", source="kakao",
                    query="마포구 합정동 스타벅스")
    alts = KakaoGeocoder("k").home_alternatives(res, "마포구 합정동 스타벅스")
    assert [a.label for a in alts] == ["스타벅스 합정점", "스타벅스 합정푸르지오점"]

    # 첫 결과가 말한 지역 밖(강동구에 없어 송파구가 걸림) → 빈 목록 = 통과 금지
    docs = [_poi_doc("보배반점 잠실점", "서울 송파구 잠실동 1")]
    monkeypatch.setattr(KakaoGeocoder, "_get", _kakao_with(keyword_docs=docs))
    res = GeoResult(GeoPoint(lat=37.51, lng=127.10), precision="poi", source="kakao", query="강동구 보배반점")
    assert KakaoGeocoder("k").home_alternatives(res, "강동구 보배반점") == []


def test_kakao_poi_alternatives_tolerate_hangjeongdong_and_aliases(monkeypatch):
    """'서대문구 신촌동'(행정동)의 지점 주소는 '창천동'(법정동) — 구 단위로 다시 거른다.
    '서울시'·'충청북도'·'정릉2동'도 주소 표기('서울'·'충북'·'정릉동')와 같은 곳으로 본다."""
    docs = [_poi_doc("스타벅스 신촌점", "서울 서대문구 창천동 1"),
            _poi_doc("스타벅스 이대점", "서울 서대문구 대현동 2")]
    monkeypatch.setattr(KakaoGeocoder, "_get", _kakao_with(keyword_docs=docs))
    res = GeoResult(GeoPoint(lat=37.55, lng=126.93), precision="poi", source="kakao",
                    query="서대문구 신촌동 스타벅스")
    assert len(KakaoGeocoder("k").home_alternatives(res, "서대문구 신촌동 스타벅스")) == 2
    # 구 토큰조차 없으면 판단 포기(None) — 오늘처럼 첫 결과 통과
    res.query = "신촌동 스타벅스"
    assert KakaoGeocoder("k").home_alternatives(res, "신촌동 스타벅스") is None
    assert geocode.token_in_text("서울시", "서울 성북구 정릉동")
    assert geocode.token_in_text("충청북도", "충북 청주시 서원구")
    assert geocode.token_in_text("정릉2동", "서울 성북구 정릉동")


def test_chain_delegates_alternatives_to_the_backend_that_answered(monkeypatch):
    monkeypatch.setattr(KakaoGeocoder, "_get", _kakao_with(address_docs=[
        _addr_doc("경기 파주시 산남동", "경기", "파주시"),
        _addr_doc("충북 청주시 서원구 산남동", "충북", "청주시 서원구")]))
    chain = ChainGeocoder(KakaoGeocoder("k"), GazetteerGeocoder())
    kakao_res = GeoResult(GeoPoint(lat=37.7, lng=126.7), precision="address", source="kakao", query="산남동")
    assert len(chain.home_alternatives(kakao_res, "산남동")) == 2
    gaz_res = GeoResult(GeoPoint(lat=37.6, lng=127.0), precision="dong", source="gazetteer", query="정릉동")
    assert chain.home_alternatives(gaz_res, "정릉동") is None      # 사전 백엔드는 판단 못 함


def test_merge_refinement_orders_by_admin_level():
    m = interview._merge_home_refinement
    assert m("마포구 스타벅스", "합정동이요") == "마포구 합정동 스타벅스"
    assert m("중앙동", "대전 동구") == "대전 동구 중앙동"
    assert m("중앙동", "과천시요") == "과천시 중앙동"
    assert m("마포구 스타벅스", "마포구요") == "마포구 스타벅스"        # 보탤 게 없다 → 무변경
    assert m("산남동", "아 성북구 정릉동") == "산남동"                  # 동이 또 왔다 = 새 답 → 무변경
    assert m("마포구 스타벅스", "합정동 이마트") == "마포구 스타벅스"    # 상호가 바뀌었다 → 무변경
