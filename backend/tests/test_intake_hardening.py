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


def test_intake_survives_upstage_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("파서 타임아웃")

    monkeypatch.setattr(llm.upstage, "parse_document", boom)
    case = _create(document_bytes=b"doc")
    assert case.id
    assert case.report.reporter is None
