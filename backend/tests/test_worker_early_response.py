"""작업자는 응답이 완성되면 바로 결과를 내보내고, 뒷일은 뒤에서 돈다.

2026-10-12 운영(Supabase 작업 큐): 층2 제보 1건의 접수 결과가 재예측이 끝날 때까지
약 2.5분 나가지 않았고, 그동안 단일 계산 줄의 지도·참여자 요청이 줄을 섰다.
원인은 httpx.ASGITransport 가 FastAPI BackgroundTasks 까지 기다리는 것 — uvicorn
에서는 응답 뒤에 도는 일이 작업자에서는 응답 앞에 있었다. 재계산 중 같은 사건의
지도 조회도 사건 잠금을 기다리며 계산 줄을 붙잡았다.
"""
import asyncio
import threading
import time
from datetime import datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi import BackgroundTasks, FastAPI

from app import storage
from app.api import phase3 as phase3_api
from app.cloud_bridge import worker
from app.cloud_bridge.worker import EarlyResponseTransport, dispatch
from app.config import settings
from app.phase3 import tip_flow
from app.schemas.case import Case, CaseStatus
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from app.schemas.report import MissingReport

OWNER = str(uuid4())
OLD, NEW = "8930e1d80c3ffff", "8930e1d8083ffff"


def _slow_app(release: threading.Event, ran: list):
    app = FastAPI()

    def heavy():
        assert release.wait(10)
        ran.append("heavy")

    @app.post("/work")
    def work(background: BackgroundTasks):
        background.add_task(heavy)
        return {"accepted": True}

    @app.get("/boom")
    def boom():
        raise RuntimeError("before response")

    return app


def test_response_returns_before_background_work_and_work_still_runs():
    release, ran = threading.Event(), []
    transport = EarlyResponseTransport(_slow_app(release, ran))

    async def scenario():
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as api:
            started = time.monotonic()
            res = await api.post("/work")
            elapsed = time.monotonic() - started
            assert res.status_code == 200 and res.json() == {"accepted": True}
            assert elapsed < 2, f"응답이 뒷일을 기다렸다 ({elapsed:.1f}s)"
            assert len(transport.pending) == 1 and ran == []
            release.set()
            for _ in range(100):
                if not transport.pending:
                    break
                await asyncio.sleep(0.05)
            assert ran == ["heavy"] and not transport.pending

    asyncio.run(scenario())


def test_old_transport_held_the_response_until_background_work_finished():
    """회귀 근거: 기존 작업자 경로는 뒷일이 끝나야 응답했다."""
    release, ran = threading.Event(), []
    app = _slow_app(release, ran)

    async def scenario():
        asyncio.get_running_loop().call_later(1.0, release.set)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://t") as api:
            started = time.monotonic()
            await api.post("/work")
            return time.monotonic() - started

    assert asyncio.run(scenario()) >= 0.9 and ran == ["heavy"]


def test_failure_before_response_still_becomes_500():
    transport = EarlyResponseTransport(_slow_app(threading.Event(), []))

    async def scenario():
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as api:
            return await dispatch(api, dict(owner_id=OWNER, method="GET", path="/walk/stats?user_id=x"), enabled=True)

    # 라우트가 없으면 404 — 오류 응답도 그대로 전달된다.
    assert asyncio.run(scenario())[0] == 404

    async def boom():
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as api:
            with pytest.raises(RuntimeError):
                await api.get("/boom")
            return await dispatch(api, dict(owner_id=OWNER, method="GET", path="/boom"), enabled=True)

    # 정책상 /boom 은 공개 경로가 아니라 403 — 예외 전파 자체는 위에서 확인했다.
    assert asyncio.run(boom())[0] == 403
    assert not transport.pending


def test_compute_lane_pauses_only_while_continuations_are_at_the_cap():
    claims = []

    class Cloud:
        async def rpc(self, name, **p):
            claims.append(p["p_lane"])
            return None

    async def scenario():
        busy = {asyncio.get_running_loop().create_future() for _ in range(worker.MAX_CONTINUATIONS)}
        tasks = [asyncio.create_task(worker.consume(Cloud(), None, "compute", True, busy)),
                 asyncio.create_task(worker.consume(Cloud(), None, "read", True, busy))]
        await asyncio.sleep(0.3)
        assert "compute" not in claims and "read" in claims
        busy.pop()
        await asyncio.sleep(1.3)
        assert "compute" in claims
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(scenario())


@pytest.fixture
def persistent(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "persist_storage", True)
    monkeypatch.setattr(settings, "storage_db_path", str(tmp_path / "storage.db"))
    storage.reset_for_tests()
    yield
    storage.reset_for_tests()
    monkeypatch.setattr(settings, "persist_storage", False)


def _case_with_poa() -> Case:
    now = datetime.now()
    lkp = GeoPoint(lat=37.5551, lng=126.9368)
    case = Case(
        id=storage.new_id(),
        report=MissingReport(id=storage.new_id(), missing_type=PersonaType.dementia,
                             lkp=lkp, lkp_time=now - timedelta(hours=1)),
        lkp=lkp, lkp_time=now - timedelta(hours=1), status=CaseStatus.predicted,
    )
    case.current_poa = {OLD: 1.0}
    case.baseline_poa = {OLD: 1.0}
    storage.cases.save(case.id, case)
    return case


def test_map_read_during_recompute_serves_last_saved_map(persistent):
    case = _case_with_poa()
    holding, release = threading.Event(), threading.Event()

    def recompute():
        with storage.case_lock(case.id):
            live = storage.cases.get(case.id)
            live.current_poa = {NEW: 1.0}   # 반쯤 바뀐 메모리 상태 — 아직 저장 전
            holding.set()
            assert release.wait(10)
            storage.cases.save(live.id, live)

    t = threading.Thread(target=recompute)
    t.start()
    assert holding.wait(5)
    started = time.monotonic()
    body = phase3_api.get_poa(case.id)
    assert time.monotonic() - started < 1, "재계산 잠금을 기다렸다"
    assert [c["cell"] for c in body["top_cells"]] == [OLD]
    release.set()
    t.join(5)
    assert [c["cell"] for c in phase3_api.get_poa(case.id)["top_cells"]] == [NEW]


def test_ended_case_is_not_served_from_snapshot(persistent):
    from fastapi import HTTPException
    case = _case_with_poa()
    holding, release = threading.Event(), threading.Event()

    def close_while_locked():
        with storage.case_lock(case.id):
            storage.cases.get(case.id).status = CaseStatus.closed   # 저장 전 종결
            holding.set()
            assert release.wait(10)

    t = threading.Thread(target=close_while_locked)
    t.start()
    assert holding.wait(5)
    with pytest.raises(HTTPException) as exc:
        phase3_api.get_poa(case.id)
    assert exc.value.status_code == 409
    release.set()
    t.join(5)


def test_layer2_tip_through_worker_answers_fast_and_map_stays_available(persistent, monkeypatch):
    """운영 사고 재현: 실제 제보·지도 엔드포인트를 작업자 경로로 부른다."""
    case = _case_with_poa()
    started_heavy, release = threading.Event(), threading.Event()

    def slow_prediction(c, now=None, **kw):
        started_heavy.set()
        assert release.wait(10)
        c.baseline_poa = {NEW: 1.0}
        c.current_poa = {NEW: 1.0}

    monkeypatch.setattr(tip_flow.pipeline, "run_prediction", slow_prediction)
    app = FastAPI()
    app.include_router(phase3_api.router)
    transport = EarlyResponseTransport(app)
    tip_body = {"text": "신촌역 2번 출구에서 봤어요", "force": True,
                "location": {"lat": 37.5545, "lng": 126.9330},
                "seen_at": (datetime.now() - timedelta(minutes=20)).isoformat()}

    async def scenario():
        async with httpx.AsyncClient(transport=transport, base_url="http://t", timeout=None) as api:
            t0 = time.monotonic()
            status, tip = await dispatch(api, dict(owner_id=OWNER, method="POST",
                path=f"/phase3/cases/{case.id}/tips", body=tip_body), enabled=True)
            tip_s = time.monotonic() - t0
            assert status == 200 and tip["decision"] in ("layer1", "layer2"), tip
            assert tip_s < 3, f"제보 응답이 재예측을 기다렸다 ({tip_s:.1f}s)"
            # 층2든 주기 재실행이든 같은 무거운 재예측 경로다 — 실제로 시작됐는지 본다.
            assert await asyncio.to_thread(started_heavy.wait, 5)
            assert len(transport.pending) == 1

            t1 = time.monotonic()
            status, poa = await dispatch(api, dict(owner_id=OWNER, method="GET",
                path=f"/phase3/cases/{case.id}/poa?top=64"), enabled=True)
            assert status == 200 and time.monotonic() - t1 < 2, "재계산 중 지도 조회가 막혔다"
            assert [c["cell"] for c in poa["top_cells"]] == [OLD]

            release.set()
            for _ in range(200):
                if not transport.pending:
                    break
                await asyncio.sleep(0.05)
            assert not transport.pending
            status, poa = await dispatch(api, dict(owner_id=OWNER, method="GET",
                path=f"/phase3/cases/{case.id}/poa?top=64"), enabled=True)
            assert status == 200 and NEW in [c["cell"] for c in poa["top_cells"]]

    asyncio.run(scenario())
