"""웹 푸시 — 구독 등록·발송 분기·키 없음 처리."""
from fastapi.testclient import TestClient

from app import storage
from app.config import settings
from app.main import app
from app.phase3 import devices, push, webpush

c = TestClient(app)

SUB = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/TESTENDPOINT",
    "keys": {"p256dh": "BPub", "auth": "AuthSecret"},
}


def _clear():
    for d in list(devices.all_devices()):
        storage.devices.delete(d.token)


def test_public_key_endpoint_reports_disabled_without_keys(monkeypatch):
    monkeypatch.setattr(settings, "vapid_public_key", "", raising=False)
    monkeypatch.setattr(settings, "vapid_private_key", "", raising=False)
    r = c.get("/phase3/webpush/public-key")
    assert r.status_code == 200
    assert r.json() == {"key": "", "enabled": False}, "키가 없으면 앱이 구독을 시도하면 안 된다"


def test_register_web_subscription_is_stored():
    _clear()
    r = c.post("/phase3/devices", json={
        "token": SUB["endpoint"], "platform": "web",
        "cell_res7": "8730e1d80ffffff", "web_subscription": SUB,
    })
    assert r.status_code == 200 and r.json()["registered"] is True
    saved = storage.devices.get(SUB["endpoint"])
    assert saved.platform.value == "web"
    assert saved.web_subscription == SUB
    assert saved.cell_res7 == "8730e1d80ffffff", "웹도 res7 셀 하나로만 위치를 받는다"


def test_send_routes_web_subscriptions_to_webpush(monkeypatch):
    """웹 구독은 Expo 로 보내지 않는다 — 주소 체계가 다르다."""
    _clear()
    devices.register(SUB["endpoint"], "web", "8730e1d80ffffff", web_subscription=SUB)

    calls = []
    monkeypatch.setattr(webpush, "send_one",
                        lambda sub, t, b, d: calls.append(sub) or True)
    expo_called = []
    monkeypatch.setattr(push.httpx, "post",
                        lambda *a, **k: expo_called.append(a) or (_ for _ in ()).throw(AssertionError))

    out = push.send([SUB["endpoint"]], title="훈련", body="테스트", data={})
    assert calls == [SUB], "웹 구독으로 발송돼야 한다"
    assert not expo_called, "Expo API 를 부르면 안 된다"
    assert out["sent"] == 1 and out["failed"] == 0


def test_webpush_failure_is_counted_not_raised(monkeypatch):
    _clear()
    devices.register(SUB["endpoint"], "web", "8730e1d80ffffff", web_subscription=SUB)
    monkeypatch.setattr(webpush, "send_one", lambda *a, **k: False)
    out = push.send([SUB["endpoint"]], title="훈련", body="테스트", data={})
    assert out["sent"] == 0 and out["failed"] == 1, "한 명 실패가 예외로 터지면 안 된다"


def test_send_one_returns_false_without_keys(monkeypatch):
    monkeypatch.setattr(settings, "vapid_private_key", "", raising=False)
    assert webpush.send_one(SUB, "t", "b", {}) is False
