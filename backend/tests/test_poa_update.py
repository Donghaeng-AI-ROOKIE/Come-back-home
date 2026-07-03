"""POA 갱신 2층 설계의 수학 검증 — 설계 문서의 수치 예시 그대로."""

import pytest

from app.phase3.poa_update import classify_tip, mixed_likelihood
from app.phase3.triggers import kl_divergence
from app.schemas.tip import TipDecision


class TestMixedLikelihood:
    """likelihood = p·L + (1−p)·1 — 설계 문서 수치 예시."""

    def test_high_trust_park_cell(self):
        # p=0.9, 공원 셀 L=5 → 4.6
        assert mixed_likelihood(5.0, 0.9) == pytest.approx(4.6)

    def test_high_trust_far_cell(self):
        # p=0.9, 반대편 셀 L=0.1 → 0.19
        assert mixed_likelihood(0.1, 0.9) == pytest.approx(0.19)

    def test_low_trust_park_cell(self):
        # p=0.3, 공원 셀 L=5 → 2.2
        assert mixed_likelihood(5.0, 0.3) == pytest.approx(2.2)

    def test_low_trust_far_cell(self):
        # p=0.3, 반대편 셀 L=0.1 → 0.73
        assert mixed_likelihood(0.1, 0.3) == pytest.approx(0.73)

    def test_zero_trust_is_uninformative(self):
        # p=0 → 모든 셀 1 (곱해도 분포 불변)
        assert mixed_likelihood(5.0, 0.0) == pytest.approx(1.0)
        assert mixed_likelihood(0.1, 0.0) == pytest.approx(1.0)


class TestClassifyTip:
    """제보 판정 — p<0.2 파기 / 0.2~0.8 층1 / p≥0.8+위치·시각 층2."""

    def test_discard(self):
        assert classify_tip(0.1, True) == TipDecision.discard

    def test_layer1(self):
        assert classify_tip(0.5, True) == TipDecision.layer1

    def test_layer2(self):
        assert classify_tip(0.9, True) == TipDecision.layer2

    def test_high_trust_without_location_time_stays_layer1(self):
        # p 높아도 위치·시각 불특정이면 시뮬 앵커 자격 없음 → 층1만
        assert classify_tip(0.9, False) == TipDecision.layer1

    def test_boundaries(self):
        assert classify_tip(0.2, False) == TipDecision.layer1   # 경계: 파기 아님
        assert classify_tip(0.8, True) == TipDecision.layer2    # 경계: 층2


class TestKLDivergence:
    def test_identical_distributions_zero(self):
        d = {"a": 0.5, "b": 0.5}
        assert kl_divergence(d, d) == pytest.approx(0.0, abs=1e-9)

    def test_diverged_distribution_positive(self):
        baseline = {"a": 0.5, "b": 0.5}
        shifted = {"a": 0.99, "b": 0.01}
        assert kl_divergence(shifted, baseline) > 0.5
