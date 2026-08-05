"""마음 호출 예산의 층화 배분 + 문맥거리 가중 재사용 (2026-08-05).

## 무엇을 고쳤나

구버전 `_MindPool` 은 예산을 **도착 순서대로** 내줬다. 실측(정릉·500워커·
seed 42/43/44, LLM 스텁)에서 드러난 결함 셋:

  D1 구조적 배제 — 1회차 전환만 예산을 쓸 수 있어 **실호출의 100% 가 1회차**인데
     소비의 38~42% 는 2회차다. 2회차는 정의상 게이지가 더 찬 문맥이라, 실호출
     문맥의 혼란 등급이 체계적으로 낮았다(18런 중 "높음" 1건, 전체는 13~24%).
  D2 꼬리 층 누락 — 5표본이 편향된 주변분포에서 뽑혀 "불안"이 한 건도 안 들어가는
     seed 가 나온다.
  D3 매칭 부재 — 균등 표집이라 불안으로 발동한 워커가 귀소 문맥의 답을 받는다.

효과 귀속 (적대검증 2026-08-06, n12 재측정): 미커버(회차×혼란) 축의 개선은 거의
전부 D1 게이트 제거 몫이고(45.6%→27.9%, 층화를 더해도 27.8% 로 순증 노이즈 안),
**층화 고유 기여는 D2 꼬리 층 보장**이다 — "불안 층 실호출 0건" seed 비율이
42% → 0% 인데, 게이트만 제거하면 오히려 67% 로 악화한다(2회차가 예산 경쟁에
들어와 희소 층을 밀어낸다). D3 효과는 미측정 — 스텁이 층과 무관하게 같은
MindState 를 반환하므로 배달되는 마음이 상수다.

## 여기서 고정하는 계약

  1) 총량 불변 — 층화해도 실호출은 예산을 넘지 않는다
  2) 회차는 층 축 — 2회차도 자기 층의 예산을 쓴다 (D1 제거)
  3) λ=0 이면 구버전과 완전히 동일 (ablation 끔 상태이자 회귀 기준선)
  4) λ>0 이면 같은 층 엔트리가 더 자주 뽑힌다 (D3 제거)
  5) 하드 매칭이 아니다 — 가중이 걸려도 다른 층이 뽑힐 수 있다
     (결정론적 마음 캐시 금지 원칙)
  6) 미사용 쿼터는 회수된다 — 예산을 남기지 않는다
"""

import random
from collections import Counter

from app.config import settings
from app.phase2 import simulation
from app.phase2.simulation import _MindPool, _stratum_distance, stratum_key
from app.schemas.prediction import MindState

_HOME_LO = ("귀소", 0)
_HOME_HI = ("귀소", 1)
_ANX_LO = ("불안", 0)
_LATER = ("later",)


# ── 층 키 ───────────────────────────────────────────────────────────

def test_stratum_key_second_transition_is_its_own_stratum():
    """2회차 이상은 사유·혼란과 무관하게 한 층 — 층 수가 예산을 넘지 않게."""
    assert stratum_key(0.1, "귀소", 2) == _LATER
    assert stratum_key(0.9, "불안", 3) == _LATER


def test_stratum_key_uses_report_threshold():
    """혼란 고/저 경계는 Gauges.report 의 0.7 과 같아야 한다.

    층 키가 프롬프트 문장("혼란도: 높음")과 어긋나면, 모델이 같은 질문으로 본
    문맥을 다른 층으로 가르게 된다.
    """
    assert stratum_key(0.69, "귀소", 1) == _HOME_LO
    assert stratum_key(0.70, "귀소", 1) == _HOME_HI
    assert stratum_key(0.70, "불안", 1) == ("불안", 1)


def test_stratum_count_matches_default_budget():
    """층 수 = 기본 예산 — 층당 실사례 1건 보장의 전제."""
    assert len(simulation._STRATA) == 5


# ── 층 거리 ─────────────────────────────────────────────────────────

def test_distance_ordering():
    """거리 서열: 자기 자신 < 혼란만 다름 < 사유 다름 = 회차 다름."""
    assert _stratum_distance(_HOME_LO, _HOME_LO) == 0.0
    assert _stratum_distance(_HOME_LO, _HOME_HI) == 1.0
    assert _stratum_distance(_HOME_LO, _ANX_LO) == 2.0
    assert _stratum_distance(_HOME_LO, _LATER) == 2.0
    assert _stratum_distance(_HOME_LO, _HOME_HI) < _stratum_distance(_HOME_LO, _ANX_LO)


def test_distance_symmetric():
    for a in (_HOME_LO, _HOME_HI, _ANX_LO, _LATER):
        for b in (_HOME_LO, _HOME_HI, _ANX_LO, _LATER):
            assert _stratum_distance(a, b) == _stratum_distance(b, a)


# ── 예산 총량 ───────────────────────────────────────────────────────

def _filled(budget: int, keys: list[tuple]) -> _MindPool:
    """지정한 층들의 엔트리를 직접 심은 풀 (LLM 없이 재사용 로직만 검사)."""
    pool = _MindPool(budget, n_walkers=1)
    for i, k in enumerate(keys):
        pool.entries.append((k, MindState(status=f"s{i}", confusion=0.5, changed=True), f"g{i}"))
    return pool


def test_quota_sums_to_budget():
    assert sum(_MindPool(5, 500).quota.values()) == 5
    assert sum(_MindPool(3, 500).quota.values()) == 3
    assert sum(_MindPool(12, 500).quota.values()) == 12


def test_default_budget_gives_every_stratum_one_slot():
    """예산 5 = 층당 정확히 1 — 어느 층도 구조적으로 배제되지 않는다."""
    assert set(_MindPool(5, 500).quota.values()) == {1}


def test_reduced_budget_keeps_slot_for_later_stratum():
    """예산을 조여도 2회차(later) 층은 쿼터를 잃지 않는다.

    적대검증 2026-08-06 회귀: 층 선언 순서가 정의 순(귀소·불안·later)이던 동안
    budget 3·4 에서 later 가 맨 뒤로 밀려 쿼터 0 이 됐다. later 는 트리거의 40%
    를 차지하는 **두 번째로 흔한 층**이고, 쿼터 0 이면 앞 층들이 초반에 쿼터를
    소진해 free 가 영구 0 이라 실호출을 한 번도 못 받는다 — 이 배분이 없애려던
    D1(2회차 구조적 배제)의 재발이다. 실측: budget 3 에서 12 seed 중 8개가
    2회차 실호출 0건. config.py 가 budget 3 을 예비 카드로 명시하므로 실사용 구간.
    """
    for budget in (2, 3, 4, 5):
        quota = _MindPool(budget, 500).quota
        assert quota[_LATER] >= 1, f"budget {budget} 에서 later 층 쿼터 0 (구버전 회귀)"


def test_strata_declared_in_observed_frequency_order():
    """층 선언 순서 = 관측 빈도 내림차순 — divmod 가 순서대로 쿼터를 나누기 때문.

    빈도(정릉·500워커·seed 42~53): 귀소저 .441 > later .405 > 불안저 .110
    > 귀소고 .030 > 불안고 .005. 이 순서가 곧 예산 부족 시의 우선순위다.
    """
    assert simulation._STRATA == (("귀소", 0), _LATER, ("불안", 0), ("귀소", 1), ("불안", 1))


def test_zero_budget_grants_nothing():
    pool = _MindPool(0, 500)
    assert pool.remaining == 0
    assert not pool._grant(_HOME_LO, 0.0)
    assert not pool._grant(_LATER, 0.99)


def test_remaining_counts_quota_and_reserve():
    """remaining 은 기존 계측이 읽는 이름 — 전용 쿼터 + 공용 예비의 합."""
    pool = _MindPool(5, 500)
    assert pool.remaining == 5
    pool._grant(_HOME_LO, 0.0)
    assert pool.remaining == 4


# ── 쿼터 회수 ───────────────────────────────────────────────────────

def test_unused_quota_reclaimed_after_release_point():
    """나타나지 않은 층의 쿼터는 진행률 임계 이후 다른 층이 쓸 수 있다.

    회수가 없으면 드문 층을 기다리다 예산을 남긴 채 예측이 끝난다.
    """
    pool = _MindPool(5, 500)
    # 진행률 0 에서는 자기 층 쿼터 1개만 (2번째는 거부)
    assert pool._grant(_HOME_LO, 0.0)
    assert not pool._grant(_HOME_LO, 0.0)
    pool.entries.append((_HOME_LO, MindState(), None))
    # 임계 이후: 미사용 4개가 예비로 회수되고, 이미 커버된 층도 widen 이후 허용
    assert pool._grant(_HOME_LO, settings.mind_pool_widen_p)
    assert pool.remaining == 3


def test_reserve_prefers_uncovered_stratum_before_widen_point():
    """회수 직후~widen 사이에는 예비를 '아직 대표가 없는 층'에만 준다."""
    pool = _MindPool(5, 500)
    pool._grant(_HOME_LO, 0.0)
    pool.entries.append((_HOME_LO, MindState(), None))
    p = (settings.mind_pool_release_p + settings.mind_pool_widen_p) / 2
    assert not pool._grant(_HOME_LO, p)      # 이미 대표 있음 → 거부
    assert pool._grant(_ANX_LO, p)           # 미커버 층 → 허용


# ── 재사용 매칭 ─────────────────────────────────────────────────────

def _sample_counts(pool: _MindPool, key, n: int = 4000, seed: int = 1) -> Counter:
    rng = random.Random(seed)
    return Counter(pool.sample_only(rng, key=key)[0].status for _ in range(n))


def test_lambda_zero_is_uniform_legacy_behavior(monkeypatch):
    """λ=0 → 구버전(문맥 무관 균등). ablation 끔 상태이자 회귀 기준선."""
    monkeypatch.setattr(settings, "mind_pool_match_strength", 0.0)
    pool = _filled(5, [_HOME_LO, _ANX_LO, _LATER, _HOME_HI])
    counts = _sample_counts(pool, _HOME_LO)
    for v in counts.values():
        assert abs(v / 4000 - 0.25) < 0.03      # 균등


def test_matching_favors_same_stratum(monkeypatch):
    """λ>0 → 현재 문맥과 같은 층 엔트리가 가장 자주 뽑힌다 (D3 제거)."""
    monkeypatch.setattr(settings, "mind_pool_match_strength", 1.0)
    pool = _filled(5, [_HOME_LO, _ANX_LO, _LATER, _HOME_HI])
    counts = _sample_counts(pool, _ANX_LO)
    top = counts.most_common(1)[0][0]
    assert top == "s1"                          # _ANX_LO 로 심은 엔트리
    # 같은 사유(불안)가 다른 사유(귀소)보다, 가까운 층이 먼 층보다 자주
    assert counts["s1"] > counts["s3"]          # 정확일치 > 혼란만 다름
    assert counts["s3"] > counts["s2"] or counts["s0"] > counts["s2"]


def test_matching_is_not_a_deterministic_cache(monkeypatch):
    """가중을 걸어도 다른 층이 뽑힌다 — 결정론적 마음 캐시 금지 원칙.

    λ 를 무한대(하드 매칭)로 두면 층당 엔트리 1개일 때 사실상 캐시가 된다.
    """
    monkeypatch.setattr(settings, "mind_pool_match_strength", 1.0)
    pool = _filled(5, [_HOME_LO, _ANX_LO, _LATER, _HOME_HI])
    counts = _sample_counts(pool, _ANX_LO)
    assert len(counts) == 4                     # 네 층 모두 등장
    assert counts.most_common(1)[0][1] / 4000 < 0.95


def test_sampled_state_is_a_copy(monkeypatch):
    """표집된 상태는 워커별 사본 — 한 워커의 변형이 풀을 오염시키지 않는다."""
    monkeypatch.setattr(settings, "mind_pool_match_strength", 1.0)
    pool = _filled(5, [_HOME_LO])
    mind, _, src = pool.sample_only(random.Random(0), key=_HOME_LO)
    assert src == "pool"
    mind.confusion = 0.99
    assert pool.entries[0][1].confusion == 0.5


def test_empty_pool_returns_none():
    """풀이 비어 있으면 None — 호출자가 휴리스틱으로 폴백한다."""
    assert _MindPool(0, 1).sample_only(random.Random(0), key=_HOME_LO) is None


def test_key_none_falls_back_to_uniform(monkeypatch):
    """key 미전달(구 호출부·실험 스크립트)이면 균등 표집으로 안전 폴백."""
    monkeypatch.setattr(settings, "mind_pool_match_strength", 1.0)
    pool = _filled(5, [_HOME_LO, _ANX_LO, _LATER, _HOME_HI])
    counts = Counter(pool.sample_only(random.Random(s))[0].status for s in range(4000))
    for v in counts.values():
        assert abs(v / 4000 - 0.25) < 0.05
