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
def roadnet_on(monkeypatch):
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


def test_roadnet_failure_falls_back_to_none(monkeypatch):
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
