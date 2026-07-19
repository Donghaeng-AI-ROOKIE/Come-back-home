"""Phase2 파이프라인 결합 — top-down 을 최종 α-pool 에서 제외한 2-way 구조 검증 (작업 3)."""

from datetime import datetime, timedelta

from app import storage
from app.phase2 import combine, pipeline
from app.schemas.case import Case, CaseStatus
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from app.schemas.report import MissingReport

LKP = GeoPoint(lat=37.6061, lng=127.0106)


def _case() -> Case:
    report = MissingReport(id=storage.new_id(), persona_id=None, missing_type=PersonaType.dementia,
                           lkp=LKP, lkp_time=datetime.now() - timedelta(hours=1))
    return Case(id=storage.new_id(), report=report, status=CaseStatus.intake,
               lkp=report.lkp, lkp_time=report.lkp_time)


def test_combine_uses_bottomup_statistical_only(monkeypatch):
    """최종 결합은 bottom-up·statistical 2-way [0.7, 0.3] — top-down 은 안 들어간다."""
    captured = {}
    real_alpha_pool = combine.alpha_pool

    def spy(distributions, alphas=None, mode="linear"):
        captured["n"] = len(distributions)
        captured["alphas"] = alphas
        return real_alpha_pool(distributions, alphas=alphas, mode=mode)

    monkeypatch.setattr(combine, "alpha_pool", spy)
    result = pipeline.run_prediction(_case(), seed=1)

    assert captured["n"] == 2
    assert captured["alphas"] == [0.7, 0.3]


def test_topdown_still_computed_for_debug():
    """top-down 은 최종 결합엔 안 쓰이지만, 디버그·시각화용으로 계속 응답에 노출된다."""
    result = pipeline.run_prediction(_case(), seed=1)
    assert result.poa_topdown is not None
    assert abs(sum(result.poa_topdown.cells.values()) - 1.0) < 1e-6
    # combined 는 topdown 과 독립적으로 정규화된 별도 분포
    assert abs(sum(result.poa_combined.cells.values()) - 1.0) < 1e-6
