"""API 로 들어온 tz-aware 시각(브라우저 toISOString 의 'Z' 등) 정규화 회귀.

대시보드에서 신고 접수 → 예측 실행이 `can't subtract offset-naive and
offset-aware datetimes` 로 500 나던 버그: lkp_time 이 aware 로 저장돼
pipeline 의 naive now 와 뺄셈이 불가했다. 스키마 입구에서 로컬 naive 로
통일한다 — 단순 tz 제거가 아니라 로컬 변환 후 제거(UTC 'Z' 를 그냥 떼면
KST 기준 9시간 오차).
"""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from app.schemas.report import MissingReport
from app.schemas.tip import Tip

LKP = GeoPoint(lat=37.6061, lng=127.0106)


def test_aware_utc_lkp_time_becomes_local_naive():
    one_hour_ago_utc = datetime.now(timezone.utc) - timedelta(hours=1)
    report = MissingReport(id="r1", missing_type=PersonaType.dementia,
                           lkp=LKP, lkp_time=one_hour_ago_utc)
    assert report.lkp_time.tzinfo is None
    # 로컬 변환 후 tz 제거 — 실제 경과시간이 보존돼야 한다 (±1분 허용)
    elapsed = datetime.now() - report.lkp_time
    assert timedelta(minutes=59) < elapsed < timedelta(minutes=61)


def test_naive_lkp_time_passes_through():
    t = datetime(2026, 7, 13, 20, 0, 0)
    report = MissingReport(id="r2", missing_type=PersonaType.dementia,
                           lkp=LKP, lkp_time=t)
    assert report.lkp_time == t


def test_aware_tip_seen_at_becomes_local_naive():
    seen_utc = datetime.now(timezone.utc) - timedelta(minutes=30)
    tip = Tip(id="t1", case_id="c1", text="공원에서 봤어요", seen_at=seen_utc)
    assert tip.seen_at.tzinfo is None
    # naive 시각과 비교 가능해야 한다 (poa_update 의 seen_at <= since 경로)
    assert tip.seen_at <= datetime.now()


def test_report_then_predict_with_z_suffix_lkp_time():
    """대시보드 신고 접수 버튼과 동일한 페이로드로 예측까지 E2E."""
    client = TestClient(app)
    lkp_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    r = client.post("/phase1/reports", json={
        "missing_type": "dementia",
        "lkp": {"lat": LKP.lat, "lng": LKP.lng},
        "lkp_time": lkp_time,  # '+00:00' aware — toISOString() 의 'Z' 와 동일
    })
    assert r.status_code == 200
    case_id = r.json()["id"]
    p = client.post(f"/debug/cases/{case_id}/predict?seed=7")
    assert p.status_code == 200
    assert p.json()["walkers"]
