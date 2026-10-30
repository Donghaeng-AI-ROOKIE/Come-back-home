"""시연(부스) 진입점 — 로컬에서 온보딩 템플릿 라우터를 켠 채 띄운다.

실행: uvicorn app.demo_main:app --host 0.0.0.0 --port 8000

배포 worker 는 compose 의 DEMO_ONBOARDING=true 로 같은 라우터를 켠다(app.main 참조).
이 모듈은 그 환경변수를 미리 켜고 app.main 을 불러오되, app.main 이 이미 다른 곳에서
먼저 import 된 경우(테스트 스위트)에는 라우터가 빠져 있으므로 그때만 직접 얹는다.
"""

import os

os.environ.setdefault("DEMO_ONBOARDING", "true")

from app.api import demo_onboarding  # noqa: E402
from app.main import app  # noqa: E402  — 환경변수를 먼저 켜야 라우터가 포함된다

if not any(getattr(r, "path", "").startswith(demo_onboarding.router.prefix) for r in app.routes):
    app.include_router(demo_onboarding.router)

__all__ = ["app"]
