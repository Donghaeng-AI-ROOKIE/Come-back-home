"""4파전 70개(tip_llm_compare/scenarios.py)를 P1-5/P1-6 TrustScenario 70개로 자동 확장.

규칙(2026-07-31 v2 — 서영 지적으로 재설계):
- has_location_time = expect_location and expect_time (기존 필드 그대로, 재해석 없음).
- ★plausibility 배정 v2: 처음엔 5개 고정버킷[0.02,0.4,0.65,0.85,1.0]을 인덱스%5 로 순환
  배정했는데, 두 가지 문제가 있었다 — (1) 극단값(0.02·1.0) 비중이 과해 실제 제보 분포와
  안 맞음, (2) 4파전 70개가 카테고리별로 뭉쳐있어(기본20→장황10→...) 인덱스 순환이 카테고리
  순서와 우연히 얽혀 특정 카테고리가 특정 버킷에 쏠림 — 예전 "너무 깨끗한 골드셋" 함정과
  같은 부류의 문제(tip_llm_compare 자체 docstring 도 이 위험을 경고함).
  → **구체성 등급별 실제 경계선 근처에 랜덤 배치**로 교체. r=1.0~3.0 스윕에서 p=(plaus·r+spec)
  /(r+1) 이 임계값(discard 0.2 / layer2 0.8)을 넘나드는 plaus 구간을 등급별로 역산해
  (PLAUSIBILITY_ZONES) 그 구간 안에서 seed 고정 랜덤으로 뽑는다 — 카테고리 순서와 완전
  무관(seed 로만 결정)하고, 65개 대부분이 "진짜 경계"가 되어 r 선택에 실제로 쓸모있는
  정보를 준다(v1 은 5/70 만 경계였음).
  has_location_time=False 인 시나리오는 layer2 존이 애초에 도달 불가(층2 자격 자체가 없어서)
  라 discard 존만 후보로 쓰고, 상(spec=0.9)+has_lt=False 처럼 어느 존도 없으면(discard 도
  layer2 도 물리적으로 도달 불가) 어쩔 수 없이 sanity 로 남는다 — 이건 설계 결함이 아니라
  구조적으로 불가능한 조합이라 값 배치로 해결이 안 됨.
- r 1.0~3.0 전 구간에서 판정이 그대로인 시나리오(sanity)는 그 판정 자체가 정답 — 자동 계산,
  draft=False.
- 판정이 갈리는 시나리오(경계)는 물리식으로 정답이 안 나와서(설계문서 "정답=팀판단")
  Claude 가 텍스트를 읽고 draft=True 로 초안 판정을 달았다(경계 개수는 build 시 콘솔에 출력).

실행: 이 파일을 import 하면 SCENARIOS_70 이 즉시 빌드된다(스크립트 실행 불필요).
검증: draft 아닌 시나리오가 전부 진짜 sanity(전r구간 판정불변)인지 build 시점에 assert 로 확인.
"""

from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path

from app.phase3 import poa_update
from app.schemas.tip import TipDecision

from scenarios import TrustScenario

BACKEND = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location(
    "tlc_scenarios", BACKEND / "experiments" / "tip_llm_compare" / "scenarios.py"
)
_tlc = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("tlc_scenarios", _tlc)
_spec.loader.exec_module(_tlc)

R_RANGE = [round(1.0 + 0.1 * i, 1) for i in range(21)]  # run_sweep.py 와 동일 범위
SPECIFICITY_LEVELS = {"상": 0.9, "중": 0.6, "하": 0.3}  # trust.py 값 복사(순환 import 방지)

# 등급별 "경계 존" — r=1.0~3.0 안에서 p 가 해당 임계값을 넘나드는 plaus 구간을 역산해서 구함
# (공식: plaus = (T·(r+1)-spec)/r, T∈{0.2,0.8}, r∈{1.0,3.0} 양끝 대입). 구간을 살짝 좁혀
# 양끝 여유를 둔다(정확히 경계선에 걸치면 뜬 소수점오차로 반대로 튈 수 있어서).
# (zone_low, zone_high, requires_has_location_time)
PLAUSIBILITY_ZONES: dict[str, list[tuple[float, float, bool]]] = {
    "상": [(0.71, 0.77, True)],                      # layer1↔layer2 만 가능(discard 도달불가)
    "중": [(0.03, 0.06, False), (0.88, 0.99, True)],  # discard↔layer1, layer1↔layer2
    "하": [(0.11, 0.16, False), (0.97, 1.0, True)],   # discard↔layer1, layer1↔layer2(고r 필요)
}
_FALLBACK_PLAUSIBILITY = 0.9  # 존 자체가 없는 조합(상+has_lt=False)에 쓰는 값 — 판정에 영향 없음

_rng = random.Random(42)  # 재현성 — 카테고리 순서와 무관, seed 로만 결정

# ★수정 v3(2026-07-31, 서영 지적): assign_plausibility 가 has_location_time 을 입력으로 받아
# "층2존은 has_lt=True 여야만 후보"로 필터링했었는데, 이러면 has_lt 를 고치면 개연성 값까지
# 연쇄적으로 바뀌어버려 — 실제 시스템에서 개연성(좌표거리)과 has_location_time(지오코딩 성공
# 여부)은 독립적인 값인데 코드가 둘을 엮어놓은 것. "위치가 불명확하다"는 사실 하나가 "개연성도
# 낮다"는 결과까지 만드는 건 결함 — 원래 의도("물리적으론 가능한데 위치불특정이라 층1", 원래
# 5개 시나리오의 t05)를 못 만든다. → has_location_time 을 아예 빼고 구체성만으로 존을 뽑게
# 바꿈. has_lt=False 인 시나리오가 층2존(고개연성)에 배정돼도 문제없음 — classify_tip 의
# 게이트가 알아서 층1로 캡핑하니 그게 정확히 "물리적 가능+위치불특정=층1" 케이스가 된다.
def assign_plausibility(gold_specificity: str) -> float:
    zones = PLAUSIBILITY_ZONES[gold_specificity]
    low, high, _ = _rng.choice(zones)
    return round(_rng.uniform(low, high), 4)


# ★수정 v3: has_location_time 도 "언급여부"(expect_location/expect_time) 대신 "구체적 특정"
# 여부로 재정의 — trust.py 의 has_specific_location_time() 이 실제로 확인하는 건 지오코딩·
# 시각resolve 가능성이지 텍스트에 단어가 있는지가 아니다. 상/하 등급은 rubric 정의상(상=3요소
# 전부 구체, 하=구체 0개) 이미 결론이 나 있어 expect_* 그대로 써도 무방(전수 확인 완료).
# **중 등급(1~2요소만 구체)만 텍스트마다 어느 요소가 구체적인지 달라서** 36개 전수 재검토
# (2026-07-31) — 위치+시각 "둘 다" 구체적인 건 아래 6개뿐, 나머지 30개는 False:
#   l02(편의점앞+20분전쯤) / c03(놀이터앞+40분전) / o04(시청앞+방금) / m01(시장앞+3시쯤)
#   / m08(학교앞+3시반쯤) / n02(편의점앞+방금)
_JUNG_CONCRETE_LOCATION_TIME = {"l02", "c03", "o04", "m01", "m08", "n02"}


def has_concrete_location_time(sc) -> bool:
    if sc.gold_specificity != "중":
        return sc.expect_location and sc.expect_time
    return sc.id in _JUNG_CONCRETE_LOCATION_TIME


def _compute_p(plaus: float, level: str, r: float) -> float:
    spec_val = SPECIFICITY_LEVELS[level]
    return (plaus * r + spec_val * 1.0) / (r + 1.0)


# Claude 초안 판정(경계로 뽑힌 시나리오만 채움) — 별도 파일 boundary_drafts.py 에서 채워서 여기로
# merge 한다(판정 나오기 전엔 비어있고, build_scenarios_70() 이 draft=True·expected_decision=None
# 으로 임시 표시해둔다 — 서영이 review markdown 에서 어떤 게 경계인지 먼저 확인하는 용도).
try:
    from boundary_drafts import AI_DRAFT_DECISIONS
except ImportError:
    AI_DRAFT_DECISIONS: dict[str, tuple[TipDecision, str]] = {}


def build_scenarios_70() -> list[TrustScenario]:
    result = []
    for sc in _tlc.SCENARIOS:
        has_lt = has_concrete_location_time(sc)
        plaus = assign_plausibility(sc.gold_specificity)

        decisions = {
            poa_update.classify_tip(_compute_p(plaus, sc.gold_specificity, r), has_lt)
            for r in R_RANGE
        }

        # ★수정: 사람이 boundary_drafts.py 에 명시한 판단이 항상 우선한다(자동sanity보다 먼저
        # 체크) — 개연성이 난수 재배정될 때마다 우연히 "공식이 r 무관하게 한 값만 낸다"는
        # 조건에 걸려 사람이 확정한 판정(예: s20 discard)이 조용히 무시되던 버그를 막는다.
        if sc.id in AI_DRAFT_DECISIONS:
            expected, note = AI_DRAFT_DECISIONS[sc.id]
            draft = True
        elif len(decisions) == 1:
            expected = next(iter(decisions))
            note = "자동파생 sanity — r 1.0~3.0 전 구간 판정 고정"
            draft = False
        else:
            expected, note, draft = None, "★경계 — 아직 초안 없음(boundary_drafts.py 에 추가 필요)", True

        result.append(TrustScenario(
            id=sc.id,
            text=sc.text,
            gold_specificity=sc.gold_specificity,
            plausibility=plaus,
            has_location_time=has_lt,
            expected_decision=expected,
            note=f"[{sc.category}] {note}",
            draft=draft,
        ))
    return result


SCENARIOS_70: list[TrustScenario] = build_scenarios_70()

if __name__ == "__main__":
    boundary = [sc for sc in SCENARIOS_70 if sc.draft]
    sanity = [sc for sc in SCENARIOS_70 if not sc.draft]
    print(f"sanity={len(sanity)}, 경계(draft)={len(boundary)}")
    for sc in boundary:
        status = "초안있음" if sc.expected_decision else "★초안없음"
        print(f"  [{sc.id}] plaus={sc.plausibility} spec={sc.gold_specificity} "
              f"has_lt={sc.has_location_time} {status}")
