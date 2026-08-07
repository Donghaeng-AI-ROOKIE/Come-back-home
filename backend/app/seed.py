"""데모 seed — 정릉동 78세 치매 김순자 케이스를 고정 ID로 미리 생성.

프론트는 `case_id="demo"` 로 `/phase3/cases/demo/poa` 를 바로 조회할 수 있다
(USE_MOCK=false 로 전환 시 실 배선 검증용). 서버 부팅 시 1회 실행(main lifespan),
이미 있으면 건너뛴다(멱등). 실 서비스에서는 제거하고 Phase 0·1 API 로 케이스를 만든다.
"""

from datetime import datetime, timedelta

from app import storage
from app.phase2 import pipeline
from app.schemas.case import Case, CaseStatus
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, InterviewSession, Persona, PersonaType
from app.schemas.report import Appearance, MissingReport

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

    # 데모 인터뷰 전문 — 대시보드 "챗봇 대화 내역" 표시용. 실제 Mi:dm 엘리시테이션
    # 흐름(유형 확정 → 슬롯 질문 → 요약 확인)을 재현한 고정 대본이며, 위 페르소나
    # 필드와 내용이 일치한다. 라이브 시연은 "새 인터뷰 시작"으로 별도 진행 가능.
    interview = InterviewSession(
        id="demo-interview",
        guardian_name="김민아",
        persona_type=PersonaType.dementia,
        done=True,
        persona_id=persona.id,
        messages=[
            {"role": "assistant", "text": "안녕하세요, 사전 등록을 도와드릴게요. 어떤 분을 등록하시나요? 관계와 상황을 편하게 말씀해 주세요."},
            {"role": "user", "text": "저희 어머니요. 78세이시고 치매 진단을 받으셨어요. 이름은 김순자입니다."},
            {"role": "assistant", "text": "네, 김순자 어르신이시군요. 평소 지내시는 곳(집 주소나 동네)을 알려주시겠어요?"},
            {"role": "user", "text": "성북구 정릉동 집에서 저랑 같이 살아요."},
            {"role": "assistant", "text": "혹시 어르신이 예전에 사셨거나 자주 가려고 하시는 장소가 있을까요? 사소한 곳이라도 좋아요."},
            {"role": "user", "text": "아리랑고개 쪽 옛날 집을 자꾸 찾으세요. 요즘도 그 집에 가야 한다고 하시고요. 정릉시장도 장 보러 자주 다니셨어요."},
            {"role": "assistant", "text": "옛집(아리랑고개)과 정릉시장이군요. 평소 걷는 습관이나 특이한 행동 패턴이 있다면 알려주세요."},
            {"role": "user", "text": "해질녘만 되면 옛집 방향으로 걸어가려고 하세요. 요즘은 시간을 옛날로 착각하실 때가 많아요."},
            {"role": "assistant", "text": "📋 이렇게 등록할게요. 핵심만 정리했어요.\n\n• 대상자: 김순자, 78세, 치매 어르신\n• 지내시는 곳: 성북구 정릉동\n• 가시려 할 만한 곳: 옛집(아리랑고개), 정릉시장\n• 행동 특징: 해질녘 옛집 방향 보행 습관, 시간 인식 혼란(time-shift)\n\n이대로 등록할까요?"},
            {"role": "user", "text": "네 맞아요, 등록해주세요."},
            {"role": "assistant", "text": "등록을 마쳤어요. 어르신이 실종되면 이 정보로 수색 범위를 바로 계산할 수 있습니다."},
        ],
        filled_keys=["identity", "home", "attractions", "behaviors"],
        draft_fields={"name": "김순자", "age": "78", "home": "성북구 정릉동"},
        draft_attractions=[{"label": "옛집(아리랑고개)", "area_text": "아리랑고개"},
                           {"label": "정릉시장", "area_text": "정릉동"}],
        draft_behaviors=["해질녘 옛집 방향으로 걷는 습관", "중기 치매 — 시간 인식 혼란(time-shift)"],
    )
    storage.interviews.save(interview.id, interview)

    report = MissingReport(
        id="demo-report",
        persona_id=persona.id,
        missing_type=PersonaType.dementia,
        lkp=home,
        lkp_time=datetime.now() - timedelta(hours=1),
        situation="산책 나가신다고 하고 안 돌아오셨어요",
        appearance=Appearance(
            top="파란색 점퍼", bottom="회색 바지", shoes="흰색 운동화",
            etc="160cm 마른 체형, 흰머리",
            summary="파란 점퍼에 회색 바지, 흰 운동화 차림의 마른 체형 어르신",
            top_color="blue", bottom_color="gray", shoes_color="white",
        ),
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
