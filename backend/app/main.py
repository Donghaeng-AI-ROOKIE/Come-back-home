"""돌아오길 백엔드 — FastAPI 엔트리포인트.

실행: uvicorn app.main:app --reload
문서: http://localhost:8000/docs
"""

import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api import debug, phase0, phase1, phase2, phase3, privacy, walk
from app.config import settings

log = logging.getLogger(__name__)


def _warm_exaone() -> None:
    """EXAONE 첫 호출 워밍업 — 백그라운드 1회.

    첫 prior 호출이 30초 타임아웃에 걸려 통계 폴백으로 떨어지는 것을 실측했다
    (2026-08-05). 같은 호출을 곧바로 다시 하면 4.2초다 — 어댑터 로딩·연결 수립이
    첫 회에만 붙는다. **시연 첫 실행이 곧 첫 호출**이라 그대로 두면 개인화가 빠진
    지도를 보여주게 되므로, 서버가 뜰 때 짧은 호출로 미리 데운다.

    실패해도 무시한다 — 워밍업은 편의이고, 서버 기동을 막을 이유가 없다.
    """
    from app import llm

    if llm.exaone.is_stub:
        return
    try:
        llm.exaone.chat([{"role": "user", "content": "ok"}], max_tokens=1, temperature=0.0)
        log.info("[warmup] EXAONE 예열 완료")
    except Exception as e:  # noqa: BLE001 — 예열 실패가 기동을 막으면 안 된다
        log.warning("[warmup] EXAONE 예열 실패 (첫 예측이 느릴 수 있음) — %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 데모 시드 — 기본 꺼짐(settings.seed_demo_data 주석 참조). 켜면 정릉동
    # 김순자 케이스를 고정 ID로 만든다.
    if settings.seed_demo_data:
        from app.seed import seed_demo

        seed_demo()
    # 기동을 막지 않도록 별도 스레드에서 예열한다.
    threading.Thread(target=_warm_exaone, name="exaone-warmup", daemon=True).start()
    # 시간이 흐르면 지도도 갱신한다 — 판정 로직은 있었지만 호출하는 쪽이 없었다.
    from app.phase2 import refresher

    refresher.start()
    yield


app = FastAPI(
    title="돌아오길 API",
    description="실종자 동선 예측 + 시민 타겟 알림 백엔드 (백본 — 모델 연동은 스텁)",
    version="0.1.0",
    lifespan=lifespan,
)

# 프론트(Expo 네이티브/웹) → 로컬 백엔드 개발용 CORS 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(phase0.router)
app.include_router(phase1.router)
app.include_router(phase2.router)
app.include_router(phase3.router)
app.include_router(privacy.router)
app.include_router(debug.router)
app.include_router(walk.router)


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    """E2E 시연 대시보드 — 단일 HTML (팀 내부 이해·검증용)."""
    return FileResponse(Path(__file__).parent / "static" / "dashboard.html")


@app.get("/")
def root():
    return {
        "service": "돌아오길 backend",
        "phases": {
            "phase0": "온보딩 — Mi:dm 인터뷰 → 페르소나 DB",
            "phase1": "신고 접수 — 직접 입력 인상착의 색상 추출 + Upstage 파싱 → Case 생성",
            "phase2": "동선 예측 — Top-down/Bottom-up/통계 계산, Bottom-up·통계 2-way α-pool → POA",
            "phase3": "수색 루프 — 타겟 알림, 제보 신뢰도 p, 층1 베이지안 갱신 + 층2 재실행",
            "privacy": "개인정보 — 종결·TTL 자동 파기·명시 삭제요청·감사로그",
        },
        "docs": "/docs",
    }
