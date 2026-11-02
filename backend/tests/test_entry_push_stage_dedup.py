"""2차(예측 구역)·3차(제보 후 새 구역) 알림이 한꺼번에 오던 문제의 시각 재현.

운영 설정(area_budget·res9)으로 사건 하나를 시간 순서대로 흘린다. 기기 두 대:
  A — 처음 예측 구역(2차) 안. 제보 재예측 뒤 구역에도 남는다.
  B — 처음엔 밖. 제보 재예측 뒤 새로 생긴 구역(3차) 안.

시민 앱은 화면이 켜져 있으면 15초마다 위치를 올리고, 서버가 준 대상 구역 안이면
`/phase3/webpush/enter` 를 부른다(frontend/src/hooks/useWebPush.ts). 이 진입 경로가
제보로 바뀐 구역을 새 `poa`(2차 문구) 알림으로 다시 보내, 3차 `new_region` 과 같은
15초 안에 2차 문구 알림이 한 번 더 도착했다.

시계는 가짜다. 푸시마다 (시각, 기기, 종류)를 남기고 그 목록 전체를 단언한다.
"""
import base64
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import h3
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient

from app import storage
from app.config import settings
from app.main import app
from app.phase3 import alerts, devices, triggers, webpush
from app.phase3 import webpush_entry as entry
from app.phase3.area_budget import cell_area_km2
from app.schemas.case import Case, CaseStatus
from app.schemas.common import GeoPoint
from app.schemas.report import MissingReport

LKP = GeoPoint(lat=37.6688, lng=126.7457)            # KINTEX 제2전시장 부근
A = h3.latlng_to_cell(LKP.lat, LKP.lng, 9)           # 2차부터 계속 예측 구역
A2 = min(h3.grid_ring(A, 1))                         # 2차에만 있던 칸
B = min(h3.grid_ring(A, 3))                          # 제보 재예측 뒤 새로 생긴 칸

P_PREDICTED = {A: .6, A2: .3, B: .1}                 # 예측 완료 → 2차 구역 {A, A2}
P_TIP_LAYER1 = {A: .55, A2: .33, B: .12}             # 제보 접수 직후 층1 갱신, 구역 그대로
P_TIP_LAYER1_SHIFT = {A: .5, A2: .2, B: .3}          # 층1 갱신만으로 구역이 {A, B} 로 바뀌는 경우
P_REPREDICTED = {A: .35, A2: .05, B: .6}             # 제보 재예측 → {B, A}, 새 구역 {B}

T_INTAKE = datetime.fromisoformat('2026-11-03T13:55:00')  # 신고 접수(1차 발송)
T0 = T_INTAKE + timedelta(minutes=5)                 # 예측 완료(2차 발송)
T_TIP = T0 + timedelta(minutes=8)                    # 제보 접수·층1 갱신
T1 = T0 + timedelta(minutes=10)                      # 제보 재예측 완료(3차 발송)
TICK = timedelta(seconds=15)                         # 시민 앱 위치 확인 주기(useWebPush.ts)


class World:
    """가짜 시계 + 화면을 켜 둔 시민 앱들의 15초 확인 루프."""

    def __init__(self, start):
        self.t = start
        self.phones = []
        self.rows = []                     # (시각, 기기, kind) — 실제로 나간 푸시
        self.endpoints = {}
        self._next_tick = start + timedelta(seconds=5)

    def run_until(self, until):
        """until 까지 15초마다 모든 앱의 위치 확인을 돌리고 시계를 until 에 둔다."""
        while self._next_tick <= until:
            self.t = self._next_tick
            for phone in self.phones:
                if phone.awake:
                    phone.tick()
            self._next_tick += TICK
        self.t = until


@pytest.fixture
def world(monkeypatch):
    w = World(T_INTAKE - timedelta(minutes=1))

    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return w.t if tz is None else w.t.astimezone(tz)

    # 발송 판정에 쓰이는 "지금"(위치 신선도·쿨다운·연속 시도)을 모두 같은 시계로 맞춘다.
    monkeypatch.setattr(entry, 'datetime', FakeDateTime)
    monkeypatch.setattr(devices, 'datetime', FakeDateTime)
    monkeypatch.setattr(entry, 'time', SimpleNamespace(
        monotonic=lambda: 1e6 + (w.t - T0).total_seconds()))

    def send_one(subscription, title, body, data):
        w.rows.append((w.t, w.endpoints[subscription['endpoint']], data['kind']))
        return True
    monkeypatch.setattr(webpush, 'send_one', send_one)
    return w


@pytest.fixture(autouse=True)
def production_targeting(monkeypatch):
    storage.reset_for_tests(); devices.reset(); entry._recent_attempts.clear()
    monkeypatch.setattr(webpush, 'enabled', lambda: True)
    monkeypatch.setattr(settings, 'alert_selection_policy', 'area_budget')
    monkeypatch.setattr(settings, 'push_target_res', 9)
    # 칸 두 개만 들어가는 예산 — 위 분포들의 선택 구역을 손으로 따라갈 수 있게.
    monkeypatch.setattr(settings, 'max_alert_area_km2',
                        2.5 * max(cell_area_km2(c) for c in (A, A2, B)))
    yield
    storage.reset_for_tests(); devices.reset(); entry._recent_attempts.clear()


def _subscription(endpoint):
    key = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        Encoding.X962, PublicFormat.UncompressedPoint)
    enc = lambda b: base64.urlsafe_b64encode(b).decode().rstrip('=')
    return {'endpoint': endpoint, 'keys': {'p256dh': enc(key), 'auth': enc(b'a' * 16)}}


class Phone:
    """시민 앱 한 대 — useWebPush.ts 의 확인 루프와 webPushEntry.enteredTargets 판정."""

    def __init__(self, world, name, cell, awake=True):
        self.name, self.cell, self.owner, self.awake = name, cell, str(uuid4()), awake
        endpoint = f'https://web.push.apple.com/{name}'
        world.endpoints[endpoint] = name
        self.token = entry.register(self.owner, _subscription(endpoint), cell, 'normal')['device_id']
        world.phones.append(self)

    def tick(self):
        out = entry.update_location(self.owner, self.token, self.cell)
        for target in out['targets']:
            if self.cell in target['cells']:       # 내 칸이 대상 칸 목록에 있으면 진입
                entry.enter(self.owner, self.token, target['case_id'])


def _case(poa=P_PREDICTED, status=CaseStatus.predicted):
    """사건은 그 단계가 일어난 순간에 만든다 — 먼저 만들면 첫 위치 확인이 미리 받아 간다."""
    report = MissingReport(id='stage-r', missing_type='dementia', lkp=LKP,
                           lkp_time=T_INTAKE - timedelta(minutes=30))
    case = Case(id='stage-c', report=report, lkp=LKP, lkp_time=report.lkp_time,
                status=status, current_poa=dict(poa) or None)
    storage.cases.save(case.id, case)
    return case


def _set_poa(case, poa):
    case.current_poa = dict(poa)
    case.status = CaseStatus.predicted
    storage.cases.save(case.id, case)


def test_scenario_selects_the_areas_described_above():
    """시나리오 자체가 의도한 구역·D3 판정을 만드는지 먼저 고정한다."""
    area = lambda p: alerts.target_parent_cells(alerts.select_alert_cells(p))
    assert area(P_PREDICTED) == {A, A2}
    assert area(P_TIP_LAYER1) == {A, A2}
    assert area(P_TIP_LAYER1_SHIFT) == {A, B}
    assert area(P_REPREDICTED) == {A, B}
    assert alerts.select_new_region_cells(P_REPREDICTED, P_PREDICTED) == [B]
    assert (triggers.jensen_shannon_divergence(P_REPREDICTED, P_PREDICTED)
            >= settings.js_divergence_threshold)


def test_second_and_third_alerts_arrive_at_their_own_times(world):
    """보고된 증상: 3차를 받은 B 에 15초 안에 2차 문구가 따라붙고, A 도 2차를 또 받았다."""
    Phone(world, 'A', A); Phone(world, 'B', B)

    world.run_until(T_INTAKE)                             # 신고 접수 — 1차(안전반경) 발송
    case = _case(poa={}, status=CaseStatus.intake)
    assert alerts.notify_prediction(case, reflex=True, now=T_INTAKE)['kind'] == 'reflex'
    world.run_until(T0)                                   # 예측 완료 — 2차 발송
    _set_poa(case, P_PREDICTED)
    assert alerts.notify_prediction(case, now=T0)['kind'] == 'poa'
    world.run_until(T_TIP)                                # 제보 접수 — 층1 갱신만
    _set_poa(case, P_TIP_LAYER1)
    world.run_until(T1)                                   # 제보 재예측 완료 — 3차 발송
    _set_poa(case, P_REPREDICTED)
    assert alerts.notify_prediction(case, now=T1)['kind'] == 'new_region'
    world.run_until(T1 + timedelta(minutes=2))

    assert world.rows == [
        (T_INTAKE, 'A', 'reflex'),                        # 1차: 신고 즉시, 안전반경(B 는 밖)
        (T0, 'A', 'poa'),                                 # 2차: 예측 완료 시점
        (T1, 'B', 'new_region'),                          # 3차: 재예측 시점, 새 구역만
    ]


def test_tip_layer1_update_alone_sends_no_second_stage_push(world):
    """제보 접수 직후 층1 갱신은 알림 단계가 아니다 — 새로 덮인 B 에 2차 문구를 먼저 보내지 않는다."""
    Phone(world, 'A', A); Phone(world, 'B', B)
    world.run_until(T0)
    case = _case()
    alerts.notify_prediction(case, now=T0)
    world.run_until(T_TIP)
    _set_poa(case, P_TIP_LAYER1_SHIFT)
    world.run_until(T1)
    _set_poa(case, P_REPREDICTED)
    alerts.notify_prediction(case, now=T1)
    world.run_until(T1 + timedelta(minutes=2))

    assert world.rows == [(T0, 'A', 'poa'), (T1, 'B', 'new_region')]


def test_entry_still_covers_devices_the_fanout_missed(world):
    """진입 경로의 본래 일 — 발송 순간 위치가 5분 넘게 묵어 빠진 기기는 앱을 열면 받는다."""
    a = Phone(world, 'A', A, awake=False)
    world.run_until(T0 + timedelta(minutes=5))            # 화면 꺼짐: 위치를 안 올린다
    case = _case()
    alerts.notify_prediction(case, now=world.t)
    assert world.rows == []
    a.awake = True                                        # 앱을 다시 열었다
    world.run_until(T0 + timedelta(minutes=7))
    assert world.rows == [(T0 + timedelta(minutes=5, seconds=5), 'A', 'poa')]


def test_first_alert_does_not_hide_the_predicted_area(world):
    """1차(안전반경)만 받은 기기는 2차 구역에 들어오면 2차를 받는다 — 단계가 다르다."""
    a = Phone(world, 'A', A)
    world.run_until(T0 - timedelta(seconds=50))
    case = _case(poa={}, status=CaseStatus.intake)
    assert alerts.notify_prediction(case, reflex=True, now=world.t)['kind'] == 'reflex'
    a.awake = False
    world.run_until(T0 + timedelta(minutes=6))            # 예측 완료 시점엔 위치가 묵었다
    _set_poa(case, P_PREDICTED)
    alerts.notify_prediction(case, now=world.t)
    a.awake = True
    world.run_until(T0 + timedelta(minutes=7))
    assert [(t, kind) for t, _, kind in world.rows] == [
        (T0 - timedelta(seconds=50), 'reflex'),
        (T0 + timedelta(minutes=6, seconds=5), 'poa'),
    ]


def test_same_stage_reminder_after_an_hour_is_unchanged(world):
    """같은 단계 재알림 간격은 기존 ENTRY_COOLDOWN(1시간) 그대로 — 구역이 바뀌어도 앞당기지 않는다."""
    Phone(world, 'A', A)
    world.run_until(T0)
    case = _case()
    alerts.notify_prediction(case, now=T0)
    _set_poa(case, P_TIP_LAYER1_SHIFT)
    world.run_until(T0 + entry.ENTRY_COOLDOWN + timedelta(minutes=1))
    assert [(t, kind) for t, _, kind in world.rows] == [
        (T0, 'poa'), (T0 + entry.ENTRY_COOLDOWN + timedelta(seconds=5), 'poa')]


def test_in_app_list_has_one_row_per_case_at_each_stage(world):
    """앱 안 긴급 알림 목록(15초 폴링)은 사건당 한 줄 — 두 단계가 두 줄로 겹칠 수 없다."""
    Phone(world, 'A', A); Phone(world, 'B', B)
    client = TestClient(app)
    world.run_until(T0)
    case = _case()
    alerts.notify_prediction(case, now=T0)
    assert [(r['case_id'], r['kind']) for r in
            client.get('/phase3/alerts', params={'target_cell': A}).json()] == [(case.id, 'poa')]
    world.run_until(T1)
    _set_poa(case, P_REPREDICTED)
    alerts.notify_prediction(case, now=T1)
    rows = client.get('/phase3/alerts', params={'target_cell': B}).json()
    assert [(r['case_id'], r['kind']) for r in rows] == [(case.id, 'poa')]
    assert rows[0]['issued_at'] == T1.isoformat()          # 마지막 발송(3차) 시각 하나
