"""P1-3 도로망 로딩 반경 p90 스케일 — 순수 계산 검증 (네트워크 무접촉).

sim_testset 실측 근거: 고정 3km 로딩은 치매 6h Koester 중앙값(3.9km)이
그래프 밖이라 3h/6h dist_ratio 가 체계적으로 저하됐다.
"""

from app.config import settings
from app.phase2 import radius
from app.schemas.prediction import LognormalParams

# 치매 Urban (radius.py 문서 기준: p95=12.55km, Koester 12.6km 일치)
DEMENTIA = LognormalParams(mu=0.095, sigma=1.48)
VMAX = 4.5  # reach_vmax_dementia_kmh 기본값


def test_p90_below_p95():
    assert radius.p90_km(DEMENTIA, 6.0, VMAX) < radius.p95_km(DEMENTIA, 6.0, VMAX)


def test_radius_grows_with_elapsed_and_covers_6h_median():
    r1 = radius.roadnet_radius_m(DEMENTIA, 1.0, VMAX)
    r6 = radius.roadnet_radius_m(DEMENTIA, 6.0, VMAX)
    assert r1 <= r6
    # 실측 근거였던 "치매 6h 중앙값 3.9km 가 그래프 밖" 이 해소되는가
    assert r6 >= 3900


def test_radius_clamped_to_floor_and_cap():
    tiny = LognormalParams(mu=-2.0, sigma=0.1)   # 지원이 매우 좁아도
    assert radius.roadnet_radius_m(tiny, 0.1, VMAX) == settings.roadnet_radius_m
    wide = LognormalParams(mu=3.0, sigma=2.0)    # 지원이 아무리 넓어도
    assert radius.roadnet_radius_m(wide, 48.0, VMAX) == settings.roadnet_radius_max_m


def test_radius_quantized_to_1km():
    for h in (0.5, 1.0, 2.0, 3.0, 6.0):
        assert radius.roadnet_radius_m(DEMENTIA, h, VMAX) % 1000 == 0
