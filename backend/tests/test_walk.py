"""안심 산책 API — 세션 생명주기·레벨/배지 규칙·개인정보 경계."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import storage
from app.main import app
from app.schemas.walk import WalkSession
from app.walk import stats as walk_stats

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean():
    """산책 저장소는 테스트마다 비운다 — 집계가 다른 테스트 기록에 오염된다."""
    storage.walk_sessions._items.clear()
    storage.walk_tip_counts._items.clear()
    yield
    storage.walk_sessions._items.clear()
    storage.walk_tip_counts._items.clear()


def _session(user: str, km: float, ended: datetime | None) -> WalkSession:
    s = WalkSession(id=storage.new_id(), user_id=user,
                    started_at=datetime(2026, 8, 1, 9, 0), ended_at=ended,
                    distance_km=km, duration_min=km * 12)
    return storage.walk_sessions.save(s.id, s)


# ── 레벨 규칙 ──────────────────────────────────────────────────────
def test_level_boundaries():
    assert walk_stats.level_for(0.0)[:2] == (1, "새싹 워커")
    assert walk_stats.level_for(2.9)[0] == 1
    assert walk_stats.level_for(3.0)[:2] == (2, "초보 워커")
    assert walk_stats.level_for(30.0)[:2] == (4, "실버 워커")


def test_next_level_remaining():
    """와이어프레임 예시: 48km → 실버 워커, 50km 까지 2km 남음."""
    level, label, remaining = walk_stats.level_for(48.0)
    assert (level, label, remaining) == (4, "실버 워커", 2.0)


def test_top_level_has_no_remaining():
    """최고 레벨에서 남은 거리를 0 으로 둬야 앱이 진행 문구를 감춘다."""
    level, _, remaining = walk_stats.level_for(500.0)
    assert level == 6
    assert remaining == 0.0


# ── 배지 ──────────────────────────────────────────────────────────
def test_unearned_badges_are_returned_too():
    """미획득 배지도 내려줘야 앱이 흐리게 그려 다음 목표를 보여준다."""
    badges = walk_stats.badges_for(total_km=12.0, walk_count=3, tip_count=0)
    by_id = {b.id: b.earned for b in badges}
    assert by_id["km_10"] is True
    assert by_id["km_100"] is False
    assert by_id["first_tip"] is False
    assert len(badges) == 5


def test_first_tip_badge_from_tip_count():
    badges = walk_stats.badges_for(total_km=0.0, walk_count=0, tip_count=1)
    assert next(b for b in badges if b.id == "first_tip").earned is True


# ── 집계 ──────────────────────────────────────────────────────────
def test_in_progress_session_excluded_from_totals():
    """진행 중 산책은 거리가 확정되지 않았으므로 집계에서 뺀다."""
    _session("u1", 5.0, datetime(2026, 8, 1, 10, 0))
    _session("u1", 99.0, None)                      # 진행 중
    st = walk_stats.aggregate("u1", storage.walk_sessions.list(), tip_count=0)
    assert st.total_km == 5.0
    assert st.walk_count == 1


def test_month_km_counts_only_current_month():
    _session("u1", 3.0, datetime(2026, 8, 2, 10, 0))
    _session("u1", 7.0, datetime(2026, 7, 2, 10, 0))   # 지난달
    st = walk_stats.aggregate("u1", storage.walk_sessions.list(), tip_count=0,
                              now=datetime(2026, 8, 5))
    assert st.total_km == 10.0
    assert st.month_km == 3.0


# ── API ───────────────────────────────────────────────────────────
def test_start_is_idempotent_while_active():
    """화면 복귀로 재호출돼도 세션이 중복 생성되면 안 된다."""
    a = client.post("/walk/sessions", json={"user_id": "u2"}).json()
    b = client.post("/walk/sessions", json={"user_id": "u2"}).json()
    assert a["id"] == b["id"]
    assert len(storage.walk_sessions.list()) == 1


def test_end_walk_then_stats():
    sid = client.post("/walk/sessions", json={"user_id": "u3"}).json()["id"]
    r = client.post(f"/walk/sessions/{sid}/end",
                    json={"distance_km": 1.8, "duration_min": 24})
    assert r.status_code == 200
    assert r.json()["ended_at"] is not None

    st = client.get("/walk/stats", params={"user_id": "u3"}).json()
    assert st["total_km"] == 1.8
    assert st["walk_count"] == 1
    assert st["level_label"] == "새싹 워커"


def test_end_twice_is_conflict():
    sid = client.post("/walk/sessions", json={"user_id": "u4"}).json()["id"]
    body = {"distance_km": 1.0, "duration_min": 10}
    assert client.post(f"/walk/sessions/{sid}/end", json=body).status_code == 200
    assert client.post(f"/walk/sessions/{sid}/end", json=body).status_code == 409


def test_active_walk_restores_session():
    sid = client.post("/walk/sessions", json={"user_id": "u5"}).json()["id"]
    assert client.get("/walk/sessions/active", params={"user_id": "u5"}).json()["id"] == sid
    client.post(f"/walk/sessions/{sid}/end", json={"distance_km": 1, "duration_min": 5})
    assert client.get("/walk/sessions/active", params={"user_id": "u5"}).json() is None


def test_stats_are_per_user():
    """남의 기록이 섞이면 안 된다 (인증 없는 현재도 user_id 로는 갈려야 한다)."""
    _session("a", 10.0, datetime(2026, 8, 1, 10, 0))
    _session("b", 40.0, datetime(2026, 8, 1, 10, 0))
    assert client.get("/walk/stats", params={"user_id": "a"}).json()["total_km"] == 10.0
    assert client.get("/walk/stats", params={"user_id": "b"}).json()["total_km"] == 40.0


def test_absurd_distance_rejected():
    """앱이 거리를 보내는 구조라 상한이 유일한 방어선이다."""
    sid = client.post("/walk/sessions", json={"user_id": "u6"}).json()["id"]
    r = client.post(f"/walk/sessions/{sid}/end",
                    json={"distance_km": 5000, "duration_min": 30})
    assert r.status_code == 422


def test_walk_session_stores_no_coordinates():
    """개인정보 경계 — 산책 경로 좌표는 스키마에 존재하면 안 된다."""
    fields = set(WalkSession.model_fields)
    assert not fields & {"path", "coordinates", "points", "location", "lat", "lng"}
