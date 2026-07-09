"""돌아오길 백엔드 — FastAPI 엔트리포인트.

실행: uvicorn app.main:app --reload
문서: http://localhost:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import phase0, phase1, phase2, phase3


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 데모용 정릉동 김순자 케이스를 미리 생성 → 프론트가 case_id="demo" 로 바로 조회
    from app.seed import seed_demo

    seed_demo()
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


@app.get("/")
def root():
    return {
        "service": "돌아오길 backend",
        "phases": {
            "phase0": "온보딩 — Mi:dm 인터뷰 → 페르소나 DB",
            "phase1": "신고 접수 — VARCO 인상착의 + Upstage 파싱 → Case 생성",
            "phase2": "동선 예측 — Top-down/Bottom-up/통계 3-way → α-pool → POA",
            "phase3": "수색 루프 — 타겟 알림, 제보 신뢰도 p, 층1 베이지안 갱신 + 층2 재실행",
        },
        "docs": "/docs",
    }
