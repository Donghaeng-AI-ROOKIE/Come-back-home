from contextlib import asynccontextmanager
import sys
from types import SimpleNamespace

from fastapi import FastAPI, Request
import pytest
from starlette.testclient import TestClient

from app.web_host import COOKIE, create_app, create_web_app

TOKEN = "synthetic-preview-token-for-offline-tests-only"


@pytest.fixture
def web_files(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>돌아오길</title>", encoding="utf-8")
    (tmp_path / "bundle.js").write_text("var app = 'synthetic';" * 200)
    return tmp_path


def client_for(web_files, *, enabled=True, lifespan=None):
    api = FastAPI()

    @api.get("/identity")
    def identity(request: Request):
        return {"authorization": request.headers.get("authorization"),
                "cookie": request.headers.get("cookie")}

    app = create_web_app(api, dist=web_files, token=TOKEN, api_enabled=enabled, lifespan=lifespan)
    return TestClient(app, base_url="https://demo.example")


def unlock(client):
    response = client.get("/", params={"preview": TOKEN}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    return response


def test_health_does_not_open_api_or_static_files(web_files):
    with client_for(web_files) as client:
        assert client.get("/healthz").status_code == 200
        for path in ["/", "/Auth", "/bundle.js", "/api", "/api/identity"]:
            assert client.get(path).status_code == 401


@pytest.mark.parametrize("bad", ["wrong", "한글입력", ""])
def test_wrong_access_key_fails_closed(web_files, bad):
    with client_for(web_files) as client:
        assert client.get("/", params={"preview": bad}).status_code == 401


def test_cookie_and_token_removal(web_files):
    with client_for(web_files) as client:
        response = unlock(client)
        cookie = response.headers["set-cookie"]
        for flag in [COOKIE, "HttpOnly", "Secure", "SameSite=lax", "Path=/"]:
            assert flag in cookie
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["cache-control"] == "no-store"
        assert client.get("/").status_code == 200


def test_bearer_auth_is_preserved_gateway_cookie_is_not_identity(web_files):
    with client_for(web_files) as client:
        unlock(client)
        response = client.get("/api/identity", headers={"Authorization": "Bearer synthetic-login-token"})
        assert response.json() == {"authorization": "Bearer synthetic-login-token", "cookie": None}


def test_setup_mode_returns_503_instead_of_stub_model_output(web_files):
    with client_for(web_files, enabled=False) as client:
        unlock(client)
        assert client.get("/").status_code == 200
        assert client.get("/api/identity").status_code == 503


def test_spa_routes_work_but_missing_assets_and_api_stay_404(web_files):
    with client_for(web_files) as client:
        unlock(client)
        assert client.get("/Auth", headers={"Accept": "text/html"}).status_code == 200
        for path in ["/missing.js", "/assets/not-found", "/_expo/not-found", "/api/not-found"]:
            assert client.get(path, headers={"Accept": "text/html"}).status_code == 404
        assert client.post("/Auth").status_code == 405


def test_static_assets_are_compressed(web_files):
    with client_for(web_files) as client:
        unlock(client)
        response = client.get("/bundle.js", headers={"Accept-Encoding": "gzip"})
        assert response.status_code == 200
        assert response.headers["content-encoding"] == "gzip"


def test_missing_web_build_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="build is missing"):
        create_web_app(FastAPI(), dist=tmp_path, token=TOKEN)


def test_missing_access_key_is_rejected(web_files):
    app = create_web_app(FastAPI(), dist=web_files, token="")
    with pytest.raises(ValueError, match="CBH_PREVIEW_TOKEN"):
        with TestClient(app):
            pass


def test_real_factory_preserves_backend_startup_and_shutdown(web_files, monkeypatch):
    events = []

    @asynccontextmanager
    async def lifespan(api):
        events.append("start")
        yield
        events.append("stop")

    api = FastAPI(lifespan=lifespan)
    monkeypatch.setitem(sys.modules, "app.main", SimpleNamespace(app=api))
    monkeypatch.setenv("CBH_WEB_DIST", str(web_files))
    monkeypatch.setenv("CBH_PREVIEW_TOKEN", TOKEN)
    monkeypatch.setenv("CBH_API_ENABLED", "false")
    with TestClient(create_app(), base_url="https://demo.example") as client:
        assert events == ["start"]
        assert client.get("/healthz").json() == {"status": "ok", "api_enabled": False}
    assert events == ["start", "stop"]
