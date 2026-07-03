"""POA 분포 통합 — α-pool + POA×POD.

단순곱 대신 α-pool 을 쓰는 이유 (아키텍처 결정사항):
- 골든타임 초기 = linear pool (넓게 커버)
- 제보 누적 후 = log-linear pool (좁게 집중)
"""

import math


def alpha_pool(
    distributions: list[dict[str, float]],
    alphas: list[float] | None = None,
    mode: str = "linear",
) -> dict[str, float]:
    """여러 POA 분포를 하나로 결합.

    mode="linear":     P = Σ αᵢ·Pᵢ          (넓게 — 어느 한 분포라도 높으면 살림)
    mode="log_linear": P ∝ Π Pᵢ^αᵢ          (좁게 — 모든 분포가 동의하는 곳만 살림)
    """
    if not distributions:
        raise ValueError("결합할 분포가 없음")
    k = len(distributions)
    alphas = alphas or [1.0 / k] * k
    if len(alphas) != k:
        raise ValueError("alphas 길이가 분포 수와 다름")

    all_cells = set()
    for d in distributions:
        all_cells.update(d.keys())

    eps = 1e-12
    out: dict[str, float] = {}
    for cell in all_cells:
        if mode == "linear":
            out[cell] = sum(a * d.get(cell, 0.0) for a, d in zip(alphas, distributions))
        elif mode == "log_linear":
            out[cell] = math.exp(sum(a * math.log(d.get(cell, eps) + eps)
                                     for a, d in zip(alphas, distributions)))
        else:
            raise ValueError(f"알 수 없는 mode: {mode}")
    return normalize(out)


def apply_pod(poa: dict[str, float], pod: dict[str, float] | None = None) -> dict[str, float]:
    """POA × POD — 셀별 발견 확률(탐지 용이성) 가중.

    POD 스텁: 균일 1.0. 실제로는 셀의 토지 이용(도로/공원/하천),
    유동인구, 시간대(주간/야간)로 산출한다.
    """
    if pod is None:
        return dict(poa)
    return normalize({c: v * pod.get(c, 1.0) for c, v in poa.items()})


def normalize(scores: dict[str, float]) -> dict[str, float]:
    total = sum(scores.values())
    if total <= 0:
        n = len(scores) or 1
        return {c: 1.0 / n for c in scores}
    return {c: v / total for c, v in scores.items()}
