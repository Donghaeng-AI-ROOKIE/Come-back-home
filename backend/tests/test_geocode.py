"""지오코딩 — gazetteer 매칭 + draft → AttractionPoint 변환 검증."""

from app.geo.geocode import GazetteerGeocoder, to_attraction_points


def test_gazetteer_prefers_dong_over_gu():
    g = GazetteerGeocoder()
    # '성북구 정릉동'에서 구가 아니라 더 구체적인 동을 잡아야 한다
    loc = g.geocode("성북구 정릉동 정릉초 근처")
    assert loc is not None
    assert abs(loc.lat - 37.6076) < 1e-3 and abs(loc.lng - 127.0133) < 1e-3


def test_gazetteer_substring_match():
    g = GazetteerGeocoder()
    assert g.geocode("면목동에서 방앗간을 오래 하셨어요") is not None
    assert g.geocode("강서구 화곡동 살아요") is not None


def test_gazetteer_miss_returns_none():
    g = GazetteerGeocoder()
    assert g.geocode("전혀 모르는 시골 어딘가") is None
    assert g.geocode("") is None


def test_to_attraction_points_splits_resolved_and_unresolved():
    drafts = [
        {"label": "옛 직장", "area_text": "면목동"},
        {"label": "집 근처", "area_text": "정릉동"},
        {"label": "미상 장소", "area_text": "이름없는곳"},
    ]
    points, unresolved = to_attraction_points(drafts)
    assert len(points) == 2
    assert {p.label for p in points} == {"옛 직장", "집 근처"}
    assert all(p.weight == 1.0 for p in points)
    assert len(unresolved) == 1 and unresolved[0]["label"] == "미상 장소"


def test_to_attraction_points_falls_back_to_label_when_no_area():
    drafts = [{"label": "화곡동"}]  # area_text 없음 → label 로 지오코딩 시도
    points, unresolved = to_attraction_points(drafts)
    assert len(points) == 1 and not unresolved
