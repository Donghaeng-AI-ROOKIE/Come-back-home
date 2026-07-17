"""Phase0 페르소나 API — axis_quotes(보호자 원발화) 응답 제외 검증.

셀프리뷰 발견(2026-07-17): GET/POST 가 response_model=Persona 전체를 반환해
axis_quotes 가 그대로 노출되던 것을 response_model_exclude 로 막음.
"""

from fastapi.testclient import TestClient

from app import storage
from app.main import app

client = TestClient(app)


def test_get_persona_excludes_axis_quotes_but_keeps_axis_evidence():
    resp = client.post("/phase0/personas", json={
        "name": "김순자", "age": 78, "type": "dementia",
        "home": {"lat": 37.6061, "lng": 127.0106},
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "axis_quotes" not in body
    assert "axis_evidence" in body   # 다른 축 필드는 그대로 노출

    persona_id = body["id"]
    persona = storage.personas.get(persona_id)
    persona.axis_quotes = {"mobility_transport_capacity": ["쉬지 않고 30분 걸으세요"]}
    storage.personas.save(persona_id, persona)

    resp2 = client.get(f"/phase0/personas/{persona_id}")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert "axis_quotes" not in body2
    # 저장소 자체에는 원문이 그대로 남아있음(응답만 필터링, 저장·채점 로직엔 영향 없음)
    assert storage.personas.get(persona_id).axis_quotes["mobility_transport_capacity"]
