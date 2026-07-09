"""데모 seed — 정릉동 78세 치매 김순자 케이스를 고정 ID로 미리 생성.

프론트는 `case_id="demo"` 로 `/phase3/cases/demo/poa` 를 바로 조회할 수 있다
(USE_MOCK=false 로 전환 시 실 배선 검증용). 서버 부팅 시 1회 실행(main lifespan),
이미 있으면 건너뛴다(멱등). 실 서비스에서는 제거하고 Phase 0·1 API 로 케이스를 만든다.
"""

from datetime import datetime, timedelta

from app import storage
from app.llm import varco
from app.phase2 import pipeline
from app.schemas.case import Case, CaseStatus
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, Persona, PersonaType
from app.schemas.report import MissingReport

DEMO_CASE_ID = "case-jeongneung-001"  # 프론트 DEMO_CASE_ID(frontend/src/data/missing.ts)와 일치


def seed_demo() -> None:
    if storage.cases.get(DEMO_CASE_ID) is not None:
        return  # 이미 seed 됨

    home = GeoPoint(lat=37.6061, lng=127.0106)  # 프론트 LAST_SEEN 과 일치 (정릉동)
    persona = Persona(
        id="demo-persona",
        type=PersonaType.dementia,
        name="김순자",
        age=78,
        home=home,
        attraction_points=[
            AttractionPoint(label="옛집(아리랑고개)", location=GeoPoint(lat=37.6015, lng=127.0088), weight=0.55),
            AttractionPoint(label="정릉시장", location=GeoPoint(lat=37.6047, lng=127.0121), weight=0.30),
        ],
        behavior_notes=["해질녘 옛집 방향으로 걷는 습관", "중기 치매 — 시간 인식 혼란(time-shift)"],
    )
    storage.personas.save(persona.id, persona)

    report = MissingReport(
        id="demo-report",
        persona_id=persona.id,
        missing_type=PersonaType.dementia,
        lkp=home,
        lkp_time=datetime.now() - timedelta(hours=1),
        appearance=varco.extract_appearance(b"stub"),
    )
    case = Case(
        id=DEMO_CASE_ID,
        report=report,
        status=CaseStatus.intake,
        lkp=report.lkp,
        lkp_time=report.lkp_time,
    )
    storage.cases.save(case.id, case)

    # 예측 실행 → case.current_poa 채움 (프론트 히트맵 조회 가능 상태로)
    pipeline.run_prediction(case, seed=42)
