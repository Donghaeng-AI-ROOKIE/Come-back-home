"""prior 출처(source) 노출 — 폴백이 조용히 지나가지 않는지 검증.

왜 이 테스트가 있는가: 2026-08-05 시연 준비 중 첫 예측이 EXAONE 30초 타임아웃으로
통계 기본값에 떨어졌는데, POA 는 정상 생성되고 지도도 그려져서 **개인화가 빠진 것을
화면으로는 알 수 없었다.** 수색 인력을 잘못된 확신으로 보내는 실패라 계약 레벨에서
드러나야 한다.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import storage
from app.llm.exaone import ExaoneClient
from app.main import app
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, Persona, PersonaType
from app.schemas.report import MissingReport

client = TestClient(app)

LKP = GeoPoint(lat=37.6168, lng=126.9973)


def _persona() -> Persona:
    return Persona(
        id="src-test", type=PersonaType.dementia, name="테스트", age=80, home=LKP,
        attraction_points=[
            AttractionPoint(label="옛집", location=GeoPoint(lat=37.60, lng=127.01),
                            weight=1.0, place_type="past_residence"),
        ])


def _report() -> MissingReport:
    return MissingReport(id="src-rep", persona_id="src-test",
                         missing_type=PersonaType.dementia, lkp=LKP,
                         lkp_time=datetime.now(timezone.utc))


def test_stub_mode_marks_source_stub():
    """키가 없으면 애초에 호출하지 않는다 — 'exaone' 으로 위장하면 안 된다."""
    c = ExaoneClient()
    assert c.is_stub, "이 테스트는 스텁 구성(키 없음)을 전제로 한다"
    prior = c.generate_prior(_persona(), _report())
    assert prior.source == "stub"
    assert prior.fallback_reason, "왜 스텁인지 사유가 남아야 진단이 된다"


def test_call_failure_marks_source_fallback(monkeypatch):
    """호출이 실패해도 예측은 계속되지만, source 가 실패를 드러내야 한다."""
    c = ExaoneClient()
    # is_stub 은 키·URL·모델 유무에서 파생되는 property 라 값을 직접 못 넣는다 —
    # 실동작 구성을 흉내 내려면 그 셋을 채운다(실제 호출은 아래 chat 패치로 막는다).
    monkeypatch.setattr(c, "api_key", "test-key")
    monkeypatch.setattr(c, "base_url", "http://localhost:1/v1")
    monkeypatch.setattr(c, "model", "test-model")
    assert not c.is_stub

    def boom(*a, **k):
        raise TimeoutError("read timed out")

    monkeypatch.setattr(c, "chat", boom)
    prior = c.generate_prior(_persona(), _report())

    assert prior.source == "fallback"
    assert "TimeoutError" in prior.fallback_reason
    # 폴백이어도 예측을 계속할 수 있는 값이어야 한다 (조용한 실패의 반대편 요구)
    assert pytest.approx(sum(prior.strategy_probs.values()), abs=1e-6) == 1.0


def test_poa_endpoint_exposes_prior_source():
    """앱이 배너를 띄우려면 POA 응답에 실려 있어야 한다."""
    persona = _persona()
    storage.personas.save(persona.id, persona)
    res = client.post("/phase1/reports", json={
        "persona_id": persona.id,
        "missing_type": "dementia",
        "lkp": {"lat": LKP.lat, "lng": LKP.lng},
        "lkp_time": datetime.now(timezone.utc).isoformat(),
    })
    assert res.status_code == 200
    case_id = res.json()["id"]

    assert client.post(f"/phase2/cases/{case_id}/predict").status_code == 200

    poa = client.get(f"/phase3/cases/{case_id}/poa?top=5")
    assert poa.status_code == 200
    body = poa.json()
    assert "prior_source" in body, "폴백 여부를 앱이 알 수 없으면 통계 평균을 AI 예측으로 보여주게 된다"
    assert body["prior_source"] in ("exaone", "fallback", "stub", "unknown")
