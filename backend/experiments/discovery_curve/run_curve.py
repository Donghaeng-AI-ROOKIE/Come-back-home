"""발견율 곡선 — 타임라인 생성 + 비교군 4종 커버리지 스윕. LLM 호출 0회.

한 타임라인에서 진짜 궤적과 제보열을 만든 뒤, **같은 타임라인 위에서** 네 알림
전략을 각각 평가한다. 전략 간 차이만 남기기 위해 궤적·제보·시드를 공유한다.

평가 시점은 타임라인 종료 시각 하나다(d3_threshold 와 같은 규약). 그 시점의
진짜 위치 셀이 전략이 고른 알림 셀 집합 안에 있으면 hit.

**hit 는 발견율의 상한이다.** 알림을 받은 시민이 실제로 발견할 확률(POD)을 1로
놓았기 때문이다. 곡선을 "발견율"로 인용할 때는 이 가정을 함께 적어야 한다.

**순환 논법 주의.** 진짜 궤적을 우리 시뮬레이터(`simulation.run_monte_carlo`)가
만든다. 따라서 `stat_only` 대 `ours` 비교는 구조적으로 `ours` 에 유리하다.
이 곡선은 예측 성능의 증거가 아니라 **알림 전략 효율의 비교**로만 쓴다.
자세한 것은 README.md 의 "한계" 절.

실행: backend/ 에서
    python experiments/discovery_curve/run_curve.py --pilot   # 파일럿 60개
    python experiments/discovery_curve/run_curve.py           # 본 실험 800개
"""

from __future__ import annotations

import contextlib
import io
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "d3_threshold"))

import strategies

from app import storage
from app.config import settings
from app.geo import h3grid
from app.llm.exaone import _KOESTER_PARAMS
from app.phase3 import poa_update, triggers, trust
from app.schemas.case import Case
from app.schemas.debug import SimTrace
from app.schemas.persona import PersonaType
from app.schemas.report import MissingReport
from app.schemas.tip import Tip, TipDecision

# d3_threshold 의 생성 부품을 그대로 재사용한다(제보 품질 혼합·궤적 표집·위치
# 노이즈는 2026-07-25/26 에 파일럿으로 교정된 값이라 다시 만들면 그 교정이
# 사라진다). import 부작용으로 `llm.exaone.api_key = ""` 가 실행돼 LLM 호출이
# 0회로 강제되는 것도 이 실험이 원하는 동작이다.
from gen_timelines import (  # noqa: E402 — 경로 삽입 후 임포트(gen_timelines 와 같은 관례)
    ELAPSED_HOURS_RANGE,
    N_REPORTS_RANGE,
    QUALITY_MIXES,
    _make_persona,
    _make_report_location,
    _make_specificity,
    _sample_quality,
    _simulate_truth,
    _true_position_at,
    _true_prior,
)
from app.phase2 import pipeline  # noqa: E402 — gen_timelines 임포트 뒤(스텁 강제 후)에 둔다
from sim_testset import LKP  # noqa: E402 — scripts/ 경로는 gen_timelines 가 삽입한다

OUT_DIR = Path(__file__).resolve().parent

# 커버리지 스윕 격자 — 운영 기본값 0.8 을 반드시 포함시킨다(제안서가 인용할 점).
COVERAGES: tuple[float, ...] = (0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99)
# 셀 상한 두 계열 — 운영 상한(500)이 곡선 우측을 자르는 정도를 분리해서 보려고
# 무제한 계열을 같이 잰다. 무제한은 "커버리지만의 효과", 500 은 "실제 발송 형태".
CAPS: tuple[int | None, ...] = (None, settings.max_alert_cells)
_NO_CAP = 10**9


def install_fixed_roadnet(radius_m: int = 5000):
    """실험 전용 — 도로망을 LKP 중심 그래프 하나로 고정한다(`--roadnet` 모드).

    제보로 `case.lkp` 가 옮겨질 때마다 그 중심의 그래프를 새로 받으면 중심당
    약 114초가 든다(실측, 5km 도보망 32,682노드). 타임라인마다 layer2 제보가
    여러 번 나오므로 그대로는 실험이 성립하지 않는다. LKP 중심 그래프 하나를
    모든 예측·궤적이 공유하게 만든다.

    대가: 반경 밖으로 나갈 워커가 그래프 경계에 갇힌다. 관측된 이탈거리
    90분위가 2.9km 라 5km 로 대부분 덮이지만, 먼 꼬리는 잘린다 — 결과 문서에
    한계로 적을 것.
    """
    from app.geo import envlayer
    from app.geo import roadnet as rn

    net = rn.get_network(LKP, radius_m=radius_m)
    envlayer.attach(net, LKP, radius_m=radius_m)
    # pipeline._load_roadnet 은 함수 안에서 모듈을 import 한 뒤 속성으로 부르므로
    # 모듈 속성을 갈아끼우면 그대로 먹는다.
    rn.get_network = lambda center, radius_m=None: net
    envlayer.attach = lambda n, center, radius_m=None: {
        "nodes": len(getattr(n, "node_env", {})), "source": "fixed"}
    settings.use_roadnet = True
    return net


def _simulate_truth_net(ptype: PersonaType, elapsed_hours: float, seed: int,
                        persona, net) -> list[list[float]]:
    """진짜 궤적 — 도로망 위 버전(`--roadnet` 모드).

    `gen_timelines._simulate_truth` 는 `net=None` 을 고정으로 넘겨 연속 공간
    워커를 탄다. 그 경로는 Koester 표본을 **경로 길이**로 소비해 최종 변위가
    통계 기대치의 27~42% 로 짧아진다(2026-08-04 실측). 도로망 워커에는 변위
    기준 종료 교정이 들어 있으므로 이쪽으로 궤적을 만들면 그 편향이 사라진다.
    """
    from app.phase2 import simulation

    prior = _true_prior(ptype)
    trace = SimTrace(max_paths=1)
    simulation.run_monte_carlo(LKP, prior, persona, elapsed_hours, mode="statistical",
                               net=net, n_walkers=1, seed=seed, trace=trace)
    if not trace.walkers:
        return [[LKP.lat, LKP.lng]]
    return trace.walkers[0].path


def _run_timeline(mix: tuple[float, float, float], rng: random.Random, seed: int,
                  net=None) -> dict:
    """타임라인 1개 진행 → 종료 시점 상태(진짜 위치·POA·경과시간) 반환.

    제보 처리 루프는 `gen_timelines.gen_one_timeline` 과 같은 로직이다. 그 함수를
    직접 부르지 않고 복제한 이유: 그쪽은 반환값에 `current_poa` 가 없고(파일
    비대화를 피하려 요약 지표만 남긴다), 시그니처를 바꾸면 이미 측정을 마친
    D3 실험의 재현성이 흔들린다. 로직을 고칠 일이 생기면 양쪽을 함께 고칠 것.
    """
    ptype = PersonaType.dementia   # 대상 유형은 치매 단독 (2026-08-03)
    elapsed_hours = rng.uniform(*ELAPSED_HOURS_RANGE)
    persona = _make_persona(ptype, rng)
    true_path = (_simulate_truth_net(ptype, elapsed_hours, seed, persona, net) if net is not None
                 else _simulate_truth(ptype, elapsed_hours, seed, persona))

    t0 = datetime(2026, 1, 1, 12, 0, 0)
    report = MissingReport(id="dcreport-" + storage.new_id(), persona_id=persona.id,
                           missing_type=ptype, lkp=LKP, lkp_time=t0)
    case = Case(id="dccase-" + storage.new_id(), report=report, lkp=LKP, lkp_time=t0)
    storage.personas.save(persona.id, persona)
    storage.cases.save(case.id, case)

    # 초기 예측 — 신고 접수 직후 첫 예측(=1차 알림 발송 시점).
    init_time = t0 + timedelta(hours=0.1)
    pipeline.run_prediction(case, now=init_time, seed=seed + 1)
    case.last_alert_poa = dict(case.current_poa)
    case.last_alert_at = init_time

    n_reports = rng.randint(*N_REPORTS_RANGE)
    report_times = sorted(rng.uniform(0.05, elapsed_hours) for _ in range(n_reports))

    reruns = 0
    n_used_tips = 0
    for t_h in report_times:
        quality = _sample_quality(mix, rng)
        true_pos = _true_position_at(true_path, t_h, elapsed_hours)
        loc = _make_report_location(quality, true_pos, rng)
        specificity = _make_specificity(quality, rng)
        seen_at = t0 + timedelta(hours=t_h)

        tip = Tip(id="dctip-" + storage.new_id(), case_id=case.id, text="[합성 제보]",
                  location=loc, seen_at=seen_at)
        tip.p = trust.score_tip(tip, lkp=case.lkp, lkp_time=case.lkp_time,
                                persona_type=ptype, structured={"specificity": specificity})
        tip.decision = poa_update.classify_tip(tip.p, trust.has_specific_location_time(tip))

        if tip.decision == TipDecision.discard:
            continue
        n_used_tips += 1

        if tip.location is not None and case.current_poa:
            case.current_poa = poa_update.layer1_update(case.current_poa, tip.location, tip.p)

        if tip.decision == TipDecision.layer2:
            case.lkp = tip.location
            case.lkp_time = tip.seen_at
            pipeline.run_prediction(case, now=seen_at, seed=seed + 2 + len(case.tips))
            reruns += 1
            case.tips.append(tip)
            case.current_poa = poa_update.reapply_tips(
                case.baseline_poa or {}, case.tips, since=tip.seen_at)
        else:
            case.tips.append(tip)
            rerun, _reason = triggers.should_rerun_phase2(case, seen_at)
            if rerun:
                pipeline.run_prediction(case, now=seen_at, seed=seed + 2 + len(case.tips))
                reruns += 1
                case.current_poa = poa_update.reapply_tips(
                    case.baseline_poa or {}, case.tips, since=case.lkp_time)

    true_final = _true_position_at(true_path, elapsed_hours, elapsed_hours)
    state = {
        "elapsed_hours": elapsed_hours,
        "true_final_cell": h3grid.cell_of(true_final),
        "true_dist_km": h3grid.haversine_km(LKP, true_final),
        "poa": dict(case.current_poa or {}),
        "persona": persona,
        "reruns": reruns,
        "n_reports": n_reports,
        "n_used_tips": n_used_tips,
    }
    storage.personas.delete(persona.id)
    storage.cases.delete(case.id)
    return state


def _evaluate(state: dict, rng: random.Random) -> list[dict]:
    """종료 시점 상태에 네 전략을 적용 → [{strategy, coverage, cap, cells, hit}, ...]."""
    truth = state["true_final_cell"]
    elapsed = state["elapsed_hours"]
    persona = state["persona"]
    rows: list[dict] = [
        {"strategy": "none", "coverage": None, "cap": None, "cells": 0, "hit": False},
    ]

    blanket = strategies.blanket_cells(LKP, persona, elapsed)
    rows.append({"strategy": "blanket", "coverage": None, "cap": None,
                 "cells": len(blanket), "hit": truth in set(blanket)})

    # 통계 POA 는 제보를 쓰지 않으므로 **원래 LKP**·전체 경과시간 기준으로 만든다.
    stat_poa = strategies.statistical_poa(
        LKP, _KOESTER_PARAMS[PersonaType.dementia], persona, elapsed, rng)

    for name, poa in (("stat_only", stat_poa), ("ours", state["poa"])):
        for cap in CAPS:
            for cov in COVERAGES:
                cells = strategies.coverage_cells(poa, cov, _NO_CAP if cap is None else cap)
                rows.append({"strategy": name, "coverage": cov, "cap": cap,
                             "cells": len(cells), "hit": truth in set(cells)})

    # 비용 정합 — `ours` 가 쓴 셀 수 k 를 stat_only 에 그대로 주고 상위 k 셀로 평가.
    # 커버리지 격자로 근사하면 stat_only 쪽이 항상 과소평가된다(격자 간격만큼).
    for r in [x for x in rows if x["strategy"] == "ours"]:
        k = r["cells"]
        cells = strategies.top_k_cells(stat_poa, k)
        rows.append({"strategy": "stat_only_at_k", "coverage": r["coverage"], "cap": r["cap"],
                     "cells": len(cells), "hit": truth in set(cells)})
    return rows


def generate(mix_name: str, mix: tuple[float, float, float], n: int, seed_base: int,
             net=None) -> list[dict]:
    """타임라인 n 개 생성·평가. d3_threshold 와 달리 정답 라벨 균형을 맞추지 않는다.

    발견율은 자연 발생 비율 그대로 재야 의미가 있다 — positive/negative 를 목표
    개수로 맞추면 (그쪽 실험의 판정 목적에는 맞지만) 발견율이 인위적으로 바뀐다.
    """
    rng = random.Random(seed_base)
    rows: list[dict] = []
    for i in range(n):
        seed = seed_base * 100_000 + i
        with contextlib.redirect_stdout(io.StringIO()):   # 파이프라인 타이밍 로그 억제
            state = _run_timeline(mix, rng, seed, net=net)
        rows.append({
            "mix": mix_name,
            "seed": seed,
            "elapsed_hours": state["elapsed_hours"],
            "true_final_cell": state["true_final_cell"],
            "true_dist_km": state["true_dist_km"],
            "poa_cells": len(state["poa"]),
            "reruns": state["reruns"],
            "n_reports": state["n_reports"],
            "n_used_tips": state["n_used_tips"],
            "results": _evaluate(state, rng),
        })
        if (i + 1) % 10 == 0:
            print(f"[{mix_name}] {i + 1}/{n}", flush=True)
    return rows


def main(pilot: bool, use_roadnet: bool, n: int | None = None) -> None:
    net = None
    if use_roadnet:
        print("[roadnet] 고정 그래프 준비 중(최초 1회는 다운로드로 100초 이상 걸림)...", flush=True)
        net = install_fixed_roadnet()
        print(f"[roadnet] 준비 완료 — 노드 {net.graph.number_of_nodes():,}", flush=True)

    all_rows: list[dict] = []
    if pilot:
        # 파일럿 — 하네스 검증용. 곡선 모양이 나오는지·상한에 걸리는지만 본다.
        all_rows += generate("baseline", QUALITY_MIXES["baseline"], n or 60, seed_base=11, net=net)
    else:
        all_rows += generate("baseline", QUALITY_MIXES["baseline"], n or 500,
                             seed_base=11, net=net)
        all_rows += generate("false_stress_30", QUALITY_MIXES["false_stress_30"], 150,
                             seed_base=12, net=net)
        all_rows += generate("low_quality", QUALITY_MIXES["low_quality"], 150,
                             seed_base=13, net=net)

    suffix = "_roadnet" if use_roadnet else ""
    out_path = OUT_DIR / (f"curve_pilot{suffix}.jsonl" if pilot else f"curve{suffix}.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for row in all_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"저장: {out_path} ({len(all_rows)}개 타임라인)")


if __name__ == "__main__":
    _n = None
    for _a in sys.argv[1:]:
        if _a.startswith("--n="):
            _n = int(_a.split("=", 1)[1])
    main(pilot="--pilot" in sys.argv, use_roadnet="--roadnet" in sys.argv, n=_n)
