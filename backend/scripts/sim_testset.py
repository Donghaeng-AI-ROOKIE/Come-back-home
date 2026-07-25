"""동선예측 테스트셋 — 시나리오 배터리로 시뮬레이션을 돌려 sanity 지표를 뽑는다.

회의록 4번 "테스트셋으로 시뮬레이션 돌리기" 구현. 정답 좌표가 없는 문제라
절대 정확도 대신 "상식 지표"로 평가한다:

  1. on_road   — 종착점이 전부 도로 노드 위인가 (허공 금지)
  2. dist_ratio — 이동거리 중앙값 / Koester 프로파일 중앙값 (0.2~1.5 밴드 기대;
                  그래프 우회·staying_put 혼합 때문에 1.0보다 다소 작게 나오는 게 정상)
  3. monotonic — 경과시간이 늘면 평균 이탈거리도 늘어나는가
  4. seek_pull — landmark_seeking 이 random_walk 보다 끌림점에 가까운가

statistical 모드만 사용 (LLM 미호출 — 공짜, 재현 가능). 게이지(F 휴식)는 켜진 상태.
계수 튜닝(역산 그리드서치)은 이 지표가 밴드를 벗어날 때 후속 작업으로.

실행:  python scripts/sim_testset.py          # 디스크 캐시된 정릉 3km 도로망 사용
       python scripts/sim_testset.py --fixture # 테스트 fixture(800m)로 빠르게
"""

import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.geo import h3grid
from app.geo.roadnet import OSMnxNetwork
from app.llm.exaone import _KOESTER_PARAMS
from app.phase2 import simulation
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, Persona, PersonaType
from app.schemas.prediction import PriorParams

LKP = GeoPoint(lat=37.6061, lng=127.0106)          # 정릉동 데모 LKP
ATTRACTION = GeoPoint(lat=37.6015, lng=127.0088)   # 옛집(아리랑고개)
N_WALKERS = 300
ELAPSED_HOURS = [1.0, 3.0, 6.0]
SEED = 42

# 시나리오: (이름, 페르소나, 끌림점 유무)
_STRATEGY_MIX = {  # 통계 프로파일 (exaone._STRATEGY_PRIORS 와 동일 값)
    PersonaType.dementia: {"route_following": 0.30, "direction_keeping": 0.25,
                           "random_walk": 0.15, "backtracking": 0.05,
                           "staying_put": 0.10, "landmark_seeking": 0.15},
    PersonaType.intellectual_disability: {"route_following": 0.25, "direction_keeping": 0.20,
                                          "random_walk": 0.15, "backtracking": 0.10,
                                          "staying_put": 0.15, "landmark_seeking": 0.15},
}


def make_persona(ptype: PersonaType, age: int, with_attraction: bool) -> Persona:
    points = [AttractionPoint(label="옛집", location=ATTRACTION, weight=1.0)] \
        if with_attraction else []
    return Persona(id=f"ts-{ptype.value}-{age}", type=ptype, name="테스트셋",
                   age=age, home=LKP, attraction_points=points)


def make_prior(ptype: PersonaType, with_attraction: bool,
               strategy_override: dict | None = None) -> PriorParams:
    return PriorParams(
        strategy_probs=strategy_override or _STRATEGY_MIX[ptype],
        attraction_weights={"옛집": 1.0} if with_attraction else {},
        radius_lognormal=_KOESTER_PARAMS[ptype],
        reasoning="테스트셋",
    )


SCENARIOS = [
    ("치매 78세", make_persona(PersonaType.dementia, 78, True)),
    ("ID 14세", make_persona(PersonaType.intellectual_disability, 14, True)),
    ("치매 78세·끌림점없음", make_persona(PersonaType.dementia, 78, False)),
]


def _mean_dist(poa: dict[str, float], origin: GeoPoint) -> float:
    return sum(h3grid.haversine_km(origin, h3grid.cell_center(c)) * p for c, p in poa.items())


def _median_dist(net, lkp, prior, persona, elapsed) -> float:
    """확률가중이 아니라 워커 표본의 중앙값 — Koester 중앙값과 직접 비교용."""
    poa = simulation.run_monte_carlo(lkp, prior, persona, elapsed, mode="statistical",
                                     net=net, n_walkers=N_WALKERS, seed=SEED)
    dists = []
    for cell, p in poa.items():
        dists += [h3grid.haversine_km(lkp, h3grid.cell_center(cell))] * round(p * N_WALKERS)
    return statistics.median(dists) if dists else 0.0


def run(net: OSMnxNetwork) -> list[str]:
    node_cells = {h3grid.cell_of(net.node_location(n)) for n in net.graph.nodes}
    rows = ["| 시나리오 | 경과 | on_road | 평균이탈km | dist_ratio | seek_pull |",
            "|---|---|---|---|---|---|"]
    failures: list[str] = []

    for name, persona in SCENARIOS:
        prior = make_prior(persona.type, bool(persona.attraction_points))
        prev_mean = -1.0
        for elapsed in ELAPSED_HOURS:
            poa = simulation.run_monte_carlo(LKP, prior, persona, elapsed,
                                             mode="statistical", net=net,
                                             n_walkers=N_WALKERS, seed=SEED)
            on_road = set(poa) <= node_cells
            mean_d = _mean_dist(poa, LKP)

            # dist_ratio: 워커 중앙값 / Koester 중앙값(경과시간 스케일 반영)
            koester_median = math.exp(prior.radius_lognormal.mu) * max(1.0, elapsed) ** 0.5
            ratio = _median_dist(net, LKP, prior, persona, elapsed) / koester_median

            # seek_pull: 끌림점 지향 vs 무작위 (끌림점 있는 시나리오만)
            seek_pull = "-"
            if persona.attraction_points and elapsed == 1.0:
                seek = simulation.run_monte_carlo(
                    LKP, make_prior(persona.type, True, {"landmark_seeking": 1.0}),
                    persona, elapsed, mode="statistical", net=net,
                    n_walkers=N_WALKERS, seed=SEED)
                rand = simulation.run_monte_carlo(
                    LKP, make_prior(persona.type, True, {"random_walk": 1.0}),
                    persona, elapsed, mode="statistical", net=net,
                    n_walkers=N_WALKERS, seed=SEED)
                d_seek = _mean_dist(seek, ATTRACTION)
                d_rand = _mean_dist(rand, ATTRACTION)
                ok = d_seek < d_rand
                seek_pull = f"{'OK' if ok else 'FAIL'} ({d_seek:.2f}<{d_rand:.2f})"
                if not ok:
                    failures.append(f"{name}: seek_pull 실패")

            if not on_road:
                failures.append(f"{name}/{elapsed}h: 도로 밖 종착점")
            if mean_d < prev_mean:
                failures.append(f"{name}/{elapsed}h: 시간 단조성 위반 ({mean_d:.2f} < {prev_mean:.2f})")
            prev_mean = mean_d

            rows.append(f"| {name} | {elapsed:.0f}h | {'O' if on_road else 'X'} "
                        f"| {mean_d:.2f} | {ratio:.2f} | {seek_pull} |")
    return rows + ["", f"실패 {len(failures)}건" + (": " + "; ".join(failures) if failures else " — 전부 통과")]


if __name__ == "__main__":
    if "--fixture" in sys.argv:
        net = OSMnxNetwork.from_graphml(
            Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "jeongneung_walk_800m.graphml")
    else:
        from app.geo import envlayer, roadnet
        net = roadnet.get_network(LKP)
        envlayer.attach(net, LKP)
    for line in run(net):
        print(line)
