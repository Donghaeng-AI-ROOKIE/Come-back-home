"""_load_roadnet 격리 테스트 — 환경레이어 실패가 도로망 MC 를 죽이면 안 된다.

실측 회귀 배경: PIL 미설치 하나로 envlayer.attach 가 ImportError → 기존
코드는 도로망까지 통째로 버리고 연속 공간 폴백 → "실운영 구성" E2E 가
조용히 스텁 경로로 돌았다. 도로망/환경레이어 실패는 분리 격리한다.
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app import storage
from app.config import settings
from app.geo.roadnet import OSMnxNetwork
from app.phase2 import pipeline
from app.schemas.case import Case, CaseStatus
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from app.schemas.report import MissingReport

FIXTURE = Path(__file__).parent / "fixtures" / "jeongneung_walk_800m.graphml"
LKP = GeoPoint(lat=37.6061, lng=127.0106)


def _case() -> Case:
    report = MissingReport(
        id=storage.new_id(), persona_id=None, missing_type=PersonaType.dementia,
        lkp=LKP, lkp_time=datetime.now() - timedelta(hours=1),
    )
    return Case(id=storage.new_id(), report=report, status=CaseStatus.intake,
                lkp=report.lkp, lkp_time=report.lkp_time)


@pytest.fixture()
def dynamic_roads(monkeypatch):
    """동적 도로망 로더 자체를 시험한다. 문헌 거리 통계 채널은 반경 3~6km 지도로는
    늘 범위를 넘으므로 기본 설정에서는 로더를 건너뛴다 — 여기서는 다른 정의로 둔다."""
    monkeypatch.setattr(settings, "statistical_channel_definition", "onboarded_population_prior")


@pytest.fixture()
def roadnet_on(monkeypatch, dynamic_roads):
    """use_roadnet 켜고, get_network 는 fixture 그래프로 대체 (외부 API 안 침)."""
    net = OSMnxNetwork.from_graphml(FIXTURE)
    monkeypatch.setattr(settings, "use_roadnet", True)
    from app.geo import roadnet as roadnet_mod

    monkeypatch.setattr(roadnet_mod, "get_network", lambda center, radius_m=None: net)
    return net


def test_envlayer_failure_keeps_roadnet(roadnet_on, monkeypatch):
    """envlayer.attach 가 어떤 예외를 던져도 도로망 그래프는 반환돼야 한다."""
    from app.geo import envlayer

    def boom(net, center, radius_m=None):
        raise ImportError("No module named 'PIL'")  # 실측 재현

    monkeypatch.setattr(envlayer, "attach", boom)
    net, reason = pipeline._load_roadnet(_case())
    assert net is roadnet_on          # 도로망 유지
    assert net.env(next(iter(net.graph.nodes))) == {}  # env 는 빈 dict 로 동작
    # 환경레이어만 죽은 것이라 '도로망 폴백'으로 보고하면 안 된다 — 앱이 잘못된
    # 배너를 띄우게 된다.
    assert reason == ""


def test_roadnet_failure_falls_back_to_none(monkeypatch, dynamic_roads):
    """도로망 자체가 실패하면 연속 공간 폴백 — 사유를 함께 돌려준다.

    use_roadnet 기본값이 True 가 된 뒤로(PR #122) 이 폴백은 실서비스 경로다.
    사유가 없으면 "도로 제약 없는 예측"이 조용히 나간다.
    """
    monkeypatch.setattr(settings, "use_roadnet", True)
    from app.geo import roadnet as roadnet_mod

    def boom(center, radius_m=None):
        raise RuntimeError("Overpass 다운")

    monkeypatch.setattr(roadnet_mod, "get_network", boom)
    net, reason = pipeline._load_roadnet(_case())
    assert net is None
    assert "RuntimeError" in reason and "Overpass" in reason


def test_roadnet_off_returns_none():
    """설정으로 끈 것과 로딩 실패는 사유로 구분된다 — 앱 배너 문구가 갈린다."""
    assert settings.use_roadnet is False  # 테스트 기본 구성 (conftest 강제)
    net, reason = pipeline._load_roadnet(_case())
    assert net is None
    assert reason == "off"


@pytest.mark.parametrize('regional_state', ['outside', 'unsnappable', 'missing'])
def test_regional_cache_miss_loads_report_local_roads(monkeypatch, dynamic_roads, regional_state):
    """A configured KINTEX fixture must not disable dynamic roads elsewhere."""
    from types import SimpleNamespace
    from app.geo import roadnet, envlayer, road_anchors

    monkeypatch.setattr(settings, 'use_roadnet', True)
    monkeypatch.setattr(settings, 'personal_walk_cache_path', '/verified/kintex.graphml')
    case = _case()
    bbox = [37.66, 126.73, 37.69, 126.77] if regional_state == 'outside' else [37, 126, 38, 128]
    regional = SimpleNamespace(coverage_bbox=bbox, road_distance_km=lambda *_: None)
    def verified(_):
        if regional_state == 'missing':
            raise FileNotFoundError('configured region unavailable')
        return regional
    monkeypatch.setattr(roadnet, 'verified_network', verified)
    monkeypatch.setattr(road_anchors, 'connect_anchors', lambda net, points: net)
    loaded = object()
    calls = []
    monkeypatch.setattr(roadnet, 'get_network', lambda center, radius_m=None: calls.append(center) or loaded)
    monkeypatch.setattr(envlayer, 'attach', lambda *args, **kwargs: None)
    net, reason = pipeline._load_roadnet(case)
    assert net is loaded
    assert reason == ''
    assert calls == [case.lkp]


def test_covered_verified_region_does_not_download(monkeypatch):
    from types import SimpleNamespace
    from app.geo import roadnet, road_anchors
    monkeypatch.setattr(settings, 'use_roadnet', True)
    monkeypatch.setattr(settings, 'personal_walk_cache_path', '/verified/region.graphml')
    regional = SimpleNamespace(coverage_bbox=[37, 126, 38, 128], road_distance_km=lambda *_: 0.)
    monkeypatch.setattr(roadnet, 'verified_network', lambda _: regional)
    monkeypatch.setattr(road_anchors, 'connect_anchors', lambda net, points: net)
    monkeypatch.setattr(roadnet, 'get_network', lambda *a, **kw: pytest.fail('covered region must not download'))
    net, reason = pipeline._load_roadnet(_case())
    assert net is regional
    assert reason == ''


def test_outside_region_download_failure_is_reported(monkeypatch, dynamic_roads):
    from types import SimpleNamespace
    from app.geo import roadnet
    monkeypatch.setattr(settings, 'use_roadnet', True)
    monkeypatch.setattr(settings, 'personal_walk_cache_path', '/verified/kintex.graphml')
    monkeypatch.setattr(roadnet, 'verified_network', lambda _: SimpleNamespace(coverage_bbox=[37.66,126.73,37.69,126.77]))
    def unavailable(*a, **kw):
        raise TimeoutError('regional download unavailable')
    monkeypatch.setattr(roadnet, 'get_network', unavailable)
    net, reason = pipeline._load_roadnet(_case())
    assert net is None
    assert 'TimeoutError' in reason


def test_preloaded_region_skips_external_road_and_environment_queries(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from app.geo import road_bundles, roadnet, road_anchors, envlayer
    monkeypatch.setattr(settings, 'use_roadnet', True)
    monkeypatch.setattr(settings, 'personal_walk_cache_path', '')
    bundle=SimpleNamespace(road_distance_km=lambda *_: 0, bundle_source='supabase_storage', bundle_sha256='a'*64,
                           coverage_bbox=[37.4, 126.8, 37.8, 127.2])
    monkeypatch.setattr(road_bundles,'get_preloaded_network',lambda *args:bundle)
    monkeypatch.setattr(road_anchors,'connect_anchors',lambda net,points:net)
    monkeypatch.setattr(roadnet,'get_network',lambda *a,**kw:pytest.fail('unexpected Overpass request'))
    monkeypatch.setattr(envlayer,'attach',lambda *a,**kw:pytest.fail('unexpected environment request'))
    net,reason=pipeline._load_roadnet(_case())
    assert net is bundle and reason == ''


@pytest.fixture()
def literature_support(monkeypatch):
    """운영 설정(문헌 거리 통계 채널). conftest 기본값은 onboarded_population_prior 다."""
    monkeypatch.setattr(settings, "statistical_channel_definition", "literature_distance_prior")


def _square(km):
    """LKP 중심 정사각 범위 [south, west, north, east] — 가장자리까지 km."""
    import math
    dlat = km / 111.32
    dlng = km / (111.32 * math.cos(math.radians(LKP.lat)))
    return [LKP.lat - dlat, LKP.lng - dlng, LKP.lat + dlat, LKP.lng + dlng]


# 2026-10-26 #300 이후: 반경 6.5~7km 지역 지도에 들어간 사건은 연속 엔진으로 가고,
# 통계 채널 원(최대 12.55km)이 지도 밖으로 나가는 실종 약 1.5시간 뒤부터 재예측이
# 영구 실패했다(IncompletePredictionError). 그 전처럼 이런 지도는 쓰지 않는다.
def test_small_regional_bundle_routes_to_legacy_without_download(monkeypatch, literature_support):
    from types import SimpleNamespace

    from app.geo import road_anchors, road_bundles, roadnet
    monkeypatch.setattr(settings, 'use_roadnet', True)
    monkeypatch.setattr(settings, 'personal_walk_cache_path', '')
    bundle = SimpleNamespace(road_distance_km=lambda *_: 0, bundle_source='supabase_storage', bundle_sha256='a'*64,
                             coverage_bbox=_square(6.5))
    monkeypatch.setattr(road_bundles, 'get_preloaded_network', lambda *args: bundle)
    monkeypatch.setattr(road_anchors, 'connect_anchors', lambda net, points: net)
    monkeypatch.setattr(roadnet, 'get_network', lambda *a, **kw: pytest.fail('unexpected Overpass request'))
    net, reason = pipeline._load_roadnet(_case())
    assert net is None
    assert 'statistical distance support' in reason


def test_verified_map_without_enough_margin_routes_to_legacy(monkeypatch, literature_support):
    from types import SimpleNamespace

    from app.geo import road_anchors, roadnet
    monkeypatch.setattr(settings, 'use_roadnet', True)
    monkeypatch.setattr(settings, 'personal_walk_cache_path', '/verified/region.graphml')
    regional = SimpleNamespace(coverage_bbox=_square(10), road_distance_km=lambda *_: 0.)
    monkeypatch.setattr(roadnet, 'verified_network', lambda _: regional)
    monkeypatch.setattr(road_anchors, 'connect_anchors', lambda net, points: net)
    monkeypatch.setattr(roadnet, 'get_network', lambda *a, **kw: pytest.fail('unexpected Overpass request'))
    net, reason = pipeline._load_roadnet(_case())
    assert net is None
    assert 'statistical distance support' in reason


def test_verified_map_with_enough_margin_is_used(monkeypatch, literature_support):
    from types import SimpleNamespace

    from app.geo import road_anchors, roadnet
    monkeypatch.setattr(settings, 'use_roadnet', True)
    monkeypatch.setattr(settings, 'personal_walk_cache_path', '/verified/region.graphml')
    regional = SimpleNamespace(coverage_bbox=_square(14), road_distance_km=lambda *_: 0.)
    monkeypatch.setattr(roadnet, 'verified_network', lambda _: regional)
    monkeypatch.setattr(road_anchors, 'connect_anchors', lambda net, points: net)
    net, reason = pipeline._load_roadnet(_case())
    assert net is regional and reason == ''


def test_unprepared_area_skips_dynamic_download_under_literature_support(monkeypatch, literature_support):
    # 동적 지도는 반경 최대 6km라 통계 채널 원을 담을 수 없다. 공개 Overpass를
    # 기다리지 않고(하남 사건: 63초 대기 후 실패) 바로 기존 엔진으로 간다.
    from app.geo import road_bundles, roadnet
    monkeypatch.setattr(settings, 'use_roadnet', True)
    monkeypatch.setattr(settings, 'personal_walk_cache_path', '')
    monkeypatch.setattr(road_bundles, 'get_preloaded_network', lambda *args: None)
    monkeypatch.setattr(roadnet, 'get_network', lambda *a, **kw: pytest.fail('unexpected Overpass request'))
    net, reason = pipeline._load_roadnet(_case())
    assert net is None
    assert 'statistical distance support' in reason
