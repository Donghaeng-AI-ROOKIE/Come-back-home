"""intake 격리 테스트 — 외부 모델이 죽어도 신고 접수(골든타임)는 계속된다."""

from datetime import datetime

from app import llm
from app.phase1 import intake
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from app.schemas.report import Appearance

LKP = GeoPoint(lat=37.6061, lng=127.0106)


def _create(**kwargs):
    return intake.create_report(
        missing_type=PersonaType.dementia, lkp=LKP, lkp_time=datetime.now(), **kwargs)


def test_intake_uses_guardian_text_and_extracts_colors_without_model():
    case = _create(appearance=Appearance(
        top="파란색 점퍼", bottom="진회색 바지", shoes="흰색 운동화"))
    look = case.report.appearance
    assert look is not None
    assert (look.top_color, look.bottom_color, look.shoes_color) == (
        "blue", "charcoal", "white")
    assert look.summary == "파란색 점퍼, 진회색 바지, 흰색 운동화"


def test_intake_ignores_client_supplied_summary():
    """summary 는 보호자에게 받지 않는다 — 요청에 값을 실어 보내도 서버가 항목별
    입력을 합쳐 항상 덮어쓴다(2026-08-07 결정)."""
    case = _create(appearance=Appearance(
        top="파란색 점퍼", bottom="진회색 바지", shoes="흰색 운동화",
        summary="클라이언트가 보낸 임의의 요약"))
    assert case.report.appearance.summary == "파란색 점퍼, 진회색 바지, 흰색 운동화"


def test_intake_summary_includes_etc_field():
    """소지품·신체특징은 accessories/physical 두 칸이 아니라 etc 한 칸으로
    합쳐 받는다(2026-08-07 결정) — summary 생성에도 그대로 반영된다."""
    case = _create(appearance=Appearance(
        top="파란색 점퍼", bottom="진회색 바지", shoes="흰색 운동화",
        etc="지팡이를 짚으심, 키가 크신 편"))
    assert case.report.appearance.summary == (
        "파란색 점퍼, 진회색 바지, 흰색 운동화, 지팡이를 짚으심, 키가 크신 편")


def test_intake_stores_situation():
    """실종 당시 상황은 그대로 저장만 한다(다른 곳 소비는 후속 결정)."""
    case = _create(situation="산책 나가신다고 하고 안 돌아오셨어요")
    assert case.report.situation == "산책 나가신다고 하고 안 돌아오셨어요"


def test_intake_survives_upstage_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("파서 타임아웃")

    monkeypatch.setattr(llm.upstage, "parse_document", boom)
    case = _create(document_bytes=b"doc")
    assert case.id
    assert case.report.reporter is None
