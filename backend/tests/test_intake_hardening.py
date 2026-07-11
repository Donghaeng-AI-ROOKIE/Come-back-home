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


def test_intake_survives_varco_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("VLM 서버 다운")

    monkeypatch.setattr(llm.varco, "extract_appearance", boom)
    case = _create(photo_bytes=b"img")
    assert case.id                             # 접수는 성공
    assert case.report.appearance is None      # 실패 필드만 비움


def test_intake_survives_upstage_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("파서 타임아웃")

    monkeypatch.setattr(llm.upstage, "parse_document", boom)
    case = _create(document_bytes=b"doc")
    assert case.id
    assert case.report.reporter is None


def test_compare_photo_degrades_without_reference():
    """대조 기준 없는 사진은 스텁 유사도를 낮게 — 신뢰도 p 과대평가 방지."""
    with_ref = llm.varco.compare_photo(b"img", Appearance(summary="파란 점퍼"))
    without_ref = llm.varco.compare_photo(b"img", None)
    assert without_ref < with_ref
    assert llm.varco.compare_photo(None, None) == 0.0
