"""Same-origin Expo + FastAPI host for a protected exhibition deployment.

This wrapper does not alter model selection, inference or storage. The API stays
closed during hosting setup so an unconfigured model cannot silently act as a
successful live demo. Disable uvicorn access logs: the initial URL is a credential.
"""
from contextlib import asynccontextmanager
import hmac
import os
from pathlib import Path

from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

COOKIE = "__Host-cbh_preview"


class SPAFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            # Missing scripts/fonts must be 404, not HTML with a 200 status.
            # Expo navigation routes are extensionless HTML document requests.
            if (exc.status_code == 404 and scope["method"] in {"GET", "HEAD"}
                    and "." not in Path(path).name
                    and not path.startswith(("assets/", "_expo/", "."))
                    and "text/html" in Headers(scope=scope).get("accept", "")):
                return await super().get_response("index.html", scope)
            raise


class PreviewAccess:
    def __init__(self, app, *, token, api_enabled):
        if len(token.encode()) < 32:
            raise ValueError("CBH_PREVIEW_TOKEN must contain at least 32 bytes")
        self.app, self.token, self.api_enabled = app, token, api_enabled

    def matches(self, value):
        return hmac.compare_digest(value.encode(), self.token.encode())

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope, receive)
        path = scope["path"]

        async def safe_send(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                message["headers"] = list(message.get("headers", [])) + [
                    (b"cache-control", b"no-store"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"x-content-type-options", b"nosniff"),
                ]
            await send(message)

        if path == "/healthz":
            return await self.app(scope, receive, safe_send)
        if (path == "/" and scope["method"] == "GET"
                and self.matches(request.query_params.get("preview", ""))):
            response = RedirectResponse("/", status_code=303)
            response.set_cookie(COOKIE, self.token, max_age=86400,
                                secure=True, httponly=True, samesite="lax", path="/")
            return await response(scope, receive, safe_send)
        if not self.matches(request.cookies.get(COOKIE, "")):
            return await PlainTextResponse("검증용 접속 링크로 열어 주세요.", 401)(
                scope, receive, safe_send)
        if path == "/api" or path.startswith("/api/"):
            if not self.api_enabled:
                return await JSONResponse({"detail": "시연 API 연결 준비 중입니다."}, 503)(
                    scope, receive, safe_send)
            # The gateway cookie is not backend identity; preserve Bearer auth.
            scope = dict(scope)
            scope["headers"] = [(k, v) for k, v in scope["headers"] if k.lower() != b"cookie"]
        return await self.app(scope, receive, safe_send)


def create_web_app(api, *, dist, token, api_enabled=False, lifespan=None):
    dist = Path(dist)
    if not (dist / "index.html").is_file():
        raise ValueError("Expo web build is missing")

    async def health(request):
        # Process liveness only. This is deliberately not an AI-quality signal.
        return JSONResponse({"status": "ok", "api_enabled": api_enabled})

    app = Starlette(routes=[
        Route("/healthz", health),
        Mount("/api", app=api),
        Mount("/", app=GZipMiddleware(SPAFiles(directory=dist, html=True), minimum_size=1024)),
    ], lifespan=lifespan)
    app.add_middleware(PreviewAccess, token=token, api_enabled=api_enabled)
    return app


def create_app():
    from app.main import app as api

    @asynccontextmanager
    async def lifespan(app):
        # Mounted apps do not receive lifespan events automatically.
        async with api.router.lifespan_context(api):
            yield

    return create_web_app(api, dist=os.environ.get("CBH_WEB_DIST", "/app/web"),
                          token=os.environ.get("CBH_PREVIEW_TOKEN", ""),
                          api_enabled=os.environ.get("CBH_API_ENABLED", "false").lower() == "true",
                          lifespan=lifespan)
