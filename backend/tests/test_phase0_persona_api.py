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


def test_patch_persona_keeps_models_not_dicts():
    """PATCH 후에도 끌림점·집이 **모델**이어야 한다 — dict 로 바뀌면 예측이 죽는다.

    현장 사고(2026-08-12): 보호자가 이름을 한 번 고치자 그 페르소나의 모든
    신고에서 예측이 500 으로 실패했다. 원인은 `model_copy(update=...)` 가
    검증을 건너뛴다는 점 — 바로 앞의 `model_dump()` 가 AttractionPoint 를
    dict 로 바꿔 놓은 상태라 그대로 박혔고, `_default_prior` 의
    `sum(p.weight for p in persona.attraction_points)` 가 AttributeError 를 냈다.

    디스크에는 dict 든 모델이든 같은 JSON 으로 저장돼 **재시작하면 사라졌다가
    수정할 때마다 되살아나는** 형태라, 저장 데이터만 봐서는 안 잡힌다.
    그래서 검증 지점은 "저장된 JSON"이 아니라 **메모리 객체의 타입**이다.
    """
    from app.schemas.persona import AttractionPoint, GeoPoint

    resp = client.post("/phase0/personas", json={
        "name": "김순자", "age": 78, "type": "dementia",
        "home": {"lat": 37.6061, "lng": 127.0106},
        "attraction_points": [
            {"label": "망원시장", "location": {"lat": 37.5560, "lng": 126.9020}},
        ],
    })
    assert resp.status_code == 200
    persona_id = resp.json()["id"]

    # 이름만 고친다 — 끌림점은 건드리지 않는다.
    patched = client.patch(f"/phase0/personas/{persona_id}", json={"name": "김순지"})
    assert patched.status_code == 200
    assert patched.json()["name"] == "김순지"

    stored = storage.personas.get(persona_id)
    assert isinstance(stored.home, GeoPoint)
    assert stored.attraction_points, "끌림점이 사라지면 안 된다"
    for point in stored.attraction_points:
        assert isinstance(point, AttractionPoint), (
            f"끌림점이 {type(point).__name__} 로 바뀌었다 — 예측이 p.weight 에서 죽는다")
    # 실제로 예측이 읽는 접근 방식 그대로 확인한다.
    assert sum(p.weight for p in stored.attraction_points) > 0


def test_persona_list_is_isolated_by_guardian():
    """가족 목록은 **등록한 계정 것만** 보여야 한다.

    현장 제보(2026-08-12): 계정 1로 보호자 모드에 들어갔더니 계정 2가 등록한
    가족이 목록에 그대로 떴다. 이 목록에는 실종 대상자의 이름·나이·집 위치·
    자주 가는 곳이 담긴다 — 남의 것이 섞이는 건 화면이 지저분한 문제가 아니라
    개인정보가 새는 문제다. 신고 화면도 이 목록에서 대상자를 고르므로 남의
    가족을 실수로 신고할 수 있었다.
    """
    a = client.post("/phase0/personas", json={
        "name": "가족A", "age": 80, "type": "dementia",
        "home": {"lat": 37.5551, "lng": 126.9368}, "guardian_id": "u-aaa",
    }).json()["id"]
    b = client.post("/phase0/personas", json={
        "name": "가족B", "age": 75, "type": "dementia",
        "home": {"lat": 37.5561, "lng": 126.9378}, "guardian_id": "u-bbb",
    }).json()["id"]

    mine = client.get("/phase0/personas", params={"guardian_id": "u-aaa"}).json()
    ids = {p["id"] for p in mine}
    assert a in ids, "내가 등록한 가족은 보여야 한다"
    assert b not in ids, "남이 등록한 가족이 내 목록에 있으면 안 된다"

    other = client.get("/phase0/personas", params={"guardian_id": "u-bbb"}).json()
    assert {p["id"] for p in other} == {b}

    # 소유자를 안 준 페르소나는 아무에게도 안 보인다 — "예전 데이터는 전원 공개"
    # 같은 예외를 두면 필터를 넣으나 마나가 된다. 이전 데이터는 마이그레이션으로
    # 주인을 붙인다(scripts/assign_persona_owner.py).
    orphan = client.post("/phase0/personas", json={
        "name": "주인없음", "age": 70, "type": "dementia",
        "home": {"lat": 37.5, "lng": 127.0},
    }).json()["id"]
    assert orphan not in {p["id"] for p in
                          client.get("/phase0/personas", params={"guardian_id": "u-aaa"}).json()}
