"""α-pool 결합 검증."""

import pytest

from app.phase2.combine import alpha_pool, apply_pod


P1 = {"a": 0.7, "b": 0.3}
P2 = {"a": 0.2, "b": 0.5, "c": 0.3}


def test_linear_pool_sums_to_one():
    out = alpha_pool([P1, P2], mode="linear")
    assert sum(out.values()) == pytest.approx(1.0)


def test_log_linear_pool_sums_to_one():
    out = alpha_pool([P1, P2], mode="log_linear")
    assert sum(out.values()) == pytest.approx(1.0)


def test_linear_keeps_disagreement_wide():
    # linear: 한 분포에서만 확률 있는 셀(c)도 살아남는다 (넓게)
    out = alpha_pool([P1, P2], mode="linear")
    assert out["c"] > 0.1


def test_log_linear_narrows_to_agreement():
    # log-linear: 두 분포가 모두 동의하는 셀로 집중, c는 거의 죽는다 (좁게)
    out = alpha_pool([P1, P2], mode="log_linear")
    assert out["c"] < 0.01


def test_apply_pod_reweights():
    poa = {"a": 0.5, "b": 0.5}
    out = apply_pod(poa, pod={"a": 1.0, "b": 0.5})
    assert out["a"] > out["b"]
    assert sum(out.values()) == pytest.approx(1.0)
