"""P1-4 — 층2(Phase2 재실행) 트리거 그리드서치.

D3(experiments/d3_threshold)와 달리 층2 트리거는 재실행이 baseline_poa 를 리셋해
이후 궤적 전체가 갈라지므로, mass·js 처럼 사후 스칼라 정렬로 붕괴하지 않는다 —
25개 조합마다 타임라인을 실제로 재생해야 한다(메모리
project_p1_4_d3_threshold_spec.md "07-28 후속작업 B" 참고).

## 세계(world)와 재생(replay)의 분리 — 이 하네스의 핵심 설계

제보의 신뢰도 p·판정(discard/층1/층2)은 `trust.score_tip`·`poa_update.classify_tip`
으로 결정되는데, 이 둘 다 층2 트리거 임계값(layer2_periodic_minutes·
kl_divergence_threshold)을 전혀 참조하지 않는다(app/phase3/trust.py,
app/phase3/poa_update.py 실제 확인). 즉 "이 제보가 층2를 직접 발동시키는가"는
25개 조합 전부에서 동일하다 — **조합마다 달라지는 건 오직 층2-미달 제보 처리
후 `triggers.should_rerun_phase2`(주기·KL) 판정 하나뿐**이다.

그래서 진짜 궤적 + 제보(위치·품질·시각·p·판정)를 seed 로 고정해 딱 한 번
만들고("세계", build_world), 25개 조합은 이 세계를 그대로 재생하되 주기·KL
재실행 시점만 다르게 한다(replay_world). 세계 생성 단계에서는
`pipeline.run_prediction`을 부르지 않는다(비용 큰 부분은 재생 단계에만 있음).

## 탐지 시점을 깔끔하게 정의할 수 있는 이유

`poa_update.layer1_update`는 기존 POA 셀만 재가중하고 새 셀을 만들지 못한다
(likelihood 커널이 `poa.keys()` 위에서만 계산됨). 그래서 초기 footprint 밖
진짜 셀의 확률은 **재실행(Phase2) 전까지 정확히 0**이다 — "그 시점 진짜 셀
확률이 0→양수로 바뀐 첫 순간"이 곧 "그 재실행이 이동을 실제로 포착한 순간"과
같다. 이 성질 덕에 탐지 지연을 라벨 없이 기계적으로 잴 수 있다.

## D3와 공유하는 것 / 안 하는 것

- 공유: 진짜 궤적 생성(`_simulate_truth`)·제보 위치/구체성 샘플링·EXAONE 강제
  스텁(임포트만 해도 `gen_timelines.py`의 `llm.exaone.api_key = ""`가 적용됨).
- 공유 안 함: 제보 품질 스트레스(false_stress_10/30, low_quality) — 이 실험은
  트리거 타이밍만 보므로 baseline mix(고30/저50/허위20) 하나만 쓴다.

실행: backend/ 에서
    python experiments/layer2_gridsearch/run_sweep.py --pilot   # 파일럿 (기본 30개 세계)
    python experiments/layer2_gridsearch/run_sweep.py           # 본 실험 (기본 200개 세계)
    python experiments/layer2_gridsearch/run_sweep.py --n-worlds 80
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "d3_threshold"))

from app import storage
from app.config import settings
from app.geo import h3grid
from app.phase2 import pipeline
from app.phase3 import poa_update, trust, triggers
from app.schemas.case import Case
from app.schemas.common import GeoPoint
from app.schemas.persona import Persona, PersonaType
from app.schemas.report import MissingReport
from app.schemas.tip import Tip, TipDecision

import gen_timelines as d3gen  # noqa: E402 — 경로 삽입 후 임포트(D3 관례). 임포트만으로
# llm.exaone.api_key = "" 부작용 발동(EXAONE 강제 스텁, LLM 호출 0회 보장).

OUT_DIR = Path(__file__).resolve().parent
LKP = d3gen.LKP

# ★D3 튜닝값 재사용 — 이 값들을 바꾸면 정보부족 놓침이 늘어 층2 자체가 발동할
# 기회가 줄어든다(d3gen 모듈 docstring 07-26 발견 참고). 층2 실험도 같은 전제.
ELAPSED_HOURS_RANGE = d3gen.ELAPSED_HOURS_RANGE
N_REPORTS_RANGE = d3gen.N_REPORTS_RANGE
INITIAL_PREDICT_DELAY_H = d3gen.INITIAL_PREDICT_DELAY_H
BASELINE_MIX = d3gen.QUALITY_MIXES["baseline"]

# 트리거 그리드
PERIODIC_GRID = [15, 30, 45, 60, 90]        # 분
KL_GRID = [0.2, 0.35, 0.5, 0.7, 1.0]
INF = 10 ** 6  # "이 트리거는 사실상 끔"으로 쓰는 값(분/발산 단위 무관하게 절대 안 넘음)
DEFAULT_PERIODIC = settings.layer2_periodic_minutes  # 45 — ablation "both" 기준값
DEFAULT_KL = settings.kl_divergence_threshold          # 0.5


@dataclass
class Combo:
    label: str
    periodic_minutes: float
    kl_threshold: float
    combo_type: str  # "grid" | "ablation"


def build_combos() -> list[Combo]:
    combos = [
        Combo(f"p{p}_kl{kl}", p, kl, "grid")
        for p in PERIODIC_GRID for kl in KL_GRID
    ]
    combos += [
        Combo("ablation_periodic_only", DEFAULT_PERIODIC, INF, "ablation"),
        Combo("ablation_kl_only", INF, DEFAULT_KL, "ablation"),
        Combo("ablation_both_default", DEFAULT_PERIODIC, DEFAULT_KL, "ablation"),
    ]
    return combos


@dataclass
class ReportSpec:
    t_hours: float
    lat: float
    lng: float
    quality: str
    specificity: str
    seen_at: datetime
    p: float
    decision: str  # TipDecision.value — 세계 단계에서 이미 확정(조합 무관)


@dataclass
class World:
    id: str
    seed: int
    ptype: PersonaType
    persona_age: int
    elapsed_hours: float
    t0: datetime
    true_path: list[list[float]]
    reports: list[ReportSpec]
    footprint: set[str]        # 참조용 초기 POA 셀 집합(세계당 1회 계산, 콤보 무관 재현성 가정)
    t_move_hours: float | None  # 진짜 위치가 footprint 밖으로 처음 나가는 시각(없으면 None)
    true_final_cell: str


def _true_pos(world_path: list[list[float]], t_h: float, elapsed_hours: float):
    return d3gen._true_position_at(world_path, t_h, elapsed_hours)


def _find_t_move(true_path: list[list[float]], elapsed_hours: float,
                  footprint: set[str]) -> float | None:
    """진짜 경로 20스텝 중 footprint 밖으로 처음 나가는 시각(스텝 보간 해상도)."""
    n = len(true_path)
    for idx in range(n):
        t_h = (idx / (n - 1)) * elapsed_hours if n > 1 else 0.0
        cell = h3grid.cell_of(_true_pos(true_path, t_h, elapsed_hours))
        if cell not in footprint:
            return t_h
    return None


def build_world(world_id: str, seed: int, rng: random.Random) -> World:
    """세계 생성 — 진짜 궤적 + 제보(p·판정 확정) + 참조 footprint. run_prediction 은
    footprint 계산용으로 딱 1번만 부른다(콤보 재생 단계와 별개 — 재생 단계는 각자
    독립적으로 다시 초기 예측을 돌린다, 아래 replay_world 참고)."""
    ptype = rng.choice([PersonaType.dementia, PersonaType.intellectual_disability])
    elapsed_hours = rng.uniform(*ELAPSED_HOURS_RANGE)
    persona = d3gen._make_persona(ptype, rng)
    true_path = d3gen._simulate_truth(ptype, elapsed_hours, seed, persona)

    t0 = datetime(2026, 1, 1, 12, 0, 0)
    report = MissingReport(id="l2report-" + storage.new_id(), persona_id=persona.id,
                           missing_type=ptype, lkp=LKP, lkp_time=t0)
    ref_case = Case(id="l2refcase-" + storage.new_id(), report=report, lkp=LKP, lkp_time=t0)
    storage.personas.save(persona.id, persona)
    storage.cases.save(ref_case.id, ref_case)

    init_time = t0 + timedelta(hours=INITIAL_PREDICT_DELAY_H)
    with contextlib.redirect_stdout(io.StringIO()):
        pipeline.run_prediction(ref_case, now=init_time, seed=seed + 1)
    footprint = set(ref_case.current_poa or {})

    # 제보 p·판정을 조합과 무관하게 한 번만 확정 — lkp/lkp_time 은 층2 판정
    # 제보(TipDecision.layer2)에서만 갱신된다(주기·KL 제외 재실행은 lkp 를
    # 안 건드림, app/phase3/tip_flow.py 실제 구조 확인 완료).
    n_reports = rng.randint(*N_REPORTS_RANGE)
    report_times = sorted(rng.uniform(0.05, elapsed_hours) for _ in range(n_reports))
    shadow_lkp, shadow_lkp_time = LKP, t0
    reports: list[ReportSpec] = []
    for t_h in report_times:
        quality = d3gen._sample_quality(BASELINE_MIX, rng)
        true_pos = _true_pos(true_path, t_h, elapsed_hours)
        loc = d3gen._make_report_location(quality, true_pos, rng)
        specificity = d3gen._make_specificity(quality, rng)
        seen_at = t0 + timedelta(hours=t_h)

        tip = Tip(id="l2tip-" + storage.new_id(), case_id=ref_case.id, text="[합성 제보]",
                  location=loc, seen_at=seen_at)
        p = trust.score_tip(tip, lkp=shadow_lkp, lkp_time=shadow_lkp_time,
                            persona_type=ptype, structured={"specificity": specificity})
        decision = poa_update.classify_tip(p, trust.has_specific_location_time(tip))
        reports.append(ReportSpec(t_hours=t_h, lat=loc.lat, lng=loc.lng, quality=quality,
                                  specificity=specificity, seen_at=seen_at, p=p,
                                  decision=decision.value))
        if decision == TipDecision.layer2:
            shadow_lkp, shadow_lkp_time = loc, seen_at

    true_final = _true_pos(true_path, elapsed_hours, elapsed_hours)
    true_final_cell = h3grid.cell_of(true_final)
    t_move = _find_t_move(true_path, elapsed_hours, footprint)

    storage.personas.delete(persona.id)
    storage.cases.delete(ref_case.id)

    return World(id=world_id, seed=seed, ptype=ptype, persona_age=persona.age,
                elapsed_hours=elapsed_hours, t0=t0, true_path=true_path, reports=reports,
                footprint=footprint, t_move_hours=t_move, true_final_cell=true_final_cell)


def replay_world(world: World, combo: Combo) -> dict:
    """세계 하나를 콤보 하나의 트리거 설정으로 재생 — 이 조합에서만 달라지는
    주기·KL 재실행 시점을 결정하고 4개 지표를 계산한다."""
    settings.layer2_periodic_minutes = combo.periodic_minutes
    settings.kl_divergence_threshold = combo.kl_threshold

    persona = Persona(id="l2rp-" + storage.new_id(), type=world.ptype, name="합성",
                      age=world.persona_age, home=LKP)
    report = MissingReport(id="l2rr-" + storage.new_id(), persona_id=persona.id,
                           missing_type=world.ptype, lkp=LKP, lkp_time=world.t0)
    case = Case(id="l2rc-" + storage.new_id(), report=report, lkp=LKP, lkp_time=world.t0)
    storage.personas.save(persona.id, persona)
    storage.cases.save(case.id, case)

    init_time = world.t0 + timedelta(hours=INITIAL_PREDICT_DELAY_H)
    with contextlib.redirect_stdout(io.StringIO()):
        pipeline.run_prediction(case, now=init_time, seed=world.seed + 1)

    policy_reruns = 0   # 이 콤보(주기·KL)가 "추가로" 발동시킨 재실행 — 진짜 비용 지표
    layer2_reruns = 0   # 층2 제보로 발동 — 세계 고정, 콤보 무관(참고용)
    t_detect: float | None = None

    for i, r in enumerate(world.reports):
        decision = TipDecision(r.decision)
        if decision == TipDecision.discard:
            continue

        tip = Tip(id="l2rtip-" + storage.new_id(), case_id=case.id, text="[합성 제보]",
                  location=GeoPoint(lat=r.lat, lng=r.lng), seen_at=r.seen_at)
        tip.p = r.p
        tip.decision = decision

        if tip.location is not None and case.current_poa:
            case.current_poa = poa_update.layer1_update(case.current_poa, tip.location, tip.p)

        if decision == TipDecision.layer2:
            case.lkp = tip.location
            case.lkp_time = tip.seen_at
            with contextlib.redirect_stdout(io.StringIO()):
                pipeline.run_prediction(case, now=r.seen_at, seed=world.seed + 2 + i)
            layer2_reruns += 1
            case.tips.append(tip)
            case.current_poa = poa_update.reapply_tips(
                case.baseline_poa or {}, case.tips, since=tip.seen_at)
        else:
            case.tips.append(tip)
            rerun, _reason = triggers.should_rerun_phase2(case, r.seen_at)
            if rerun:
                with contextlib.redirect_stdout(io.StringIO()):
                    pipeline.run_prediction(case, now=r.seen_at, seed=world.seed + 2 + i)
                policy_reruns += 1
                case.current_poa = poa_update.reapply_tips(
                    case.baseline_poa or {}, case.tips, since=case.lkp_time)

        # 탐지 시점 — 이동 이후 첫 재실행에서 진짜 셀 확률이 0→양수로 바뀐 순간.
        if (t_detect is None and world.t_move_hours is not None
                and r.t_hours >= world.t_move_hours):
            # 종료 시점 true_final_cell 이 아니라, 이 시점 실시간 진짜 셀 기준으로 판정.
            true_cell_now = h3grid.cell_of(_true_pos(world.true_path, r.t_hours, world.elapsed_hours))
            prob_now = (case.current_poa or {}).get(true_cell_now, 0.0)
            if prob_now > 0.0:
                t_detect = r.t_hours

    final_poa = case.current_poa or {}
    poa_accuracy_final = final_poa.get(world.true_final_cell, 0.0)

    centroid_km: float | None = None
    if final_poa:
        total = sum(final_poa.values()) or 1.0
        clat = sum(h3grid.cell_center(c).lat * v for c, v in final_poa.items()) / total
        clng = sum(h3grid.cell_center(c).lng * v for c, v in final_poa.items()) / total
        centroid = GeoPoint(lat=clat, lng=clng)
        true_final = _true_pos(world.true_path, world.elapsed_hours, world.elapsed_hours)
        centroid_km = h3grid.haversine_km(centroid, true_final)

    detection_delay_min = None
    detected = False
    if world.t_move_hours is not None:
        if t_detect is not None:
            detection_delay_min = round((t_detect - world.t_move_hours) * 60, 1)
            detected = True

    storage.personas.delete(persona.id)
    storage.cases.delete(case.id)

    return {
        "world_id": world.id, "combo": combo.label, "combo_type": combo.combo_type,
        "periodic_minutes": combo.periodic_minutes, "kl_threshold": combo.kl_threshold,
        "moved": world.t_move_hours is not None,
        "detected": detected, "detection_delay_min": detection_delay_min,
        "poa_accuracy_final": round(poa_accuracy_final, 4),
        "centroid_km_final": round(centroid_km, 3) if centroid_km is not None else None,
        "policy_reruns": policy_reruns, "layer2_reruns": layer2_reruns,
        "total_reruns": policy_reruns + layer2_reruns,
    }


def summarize(records: list[dict]) -> str:
    """실행 직후 빠른 확인용(정식 결정표는 analyze.py). ★정확도·중심점거리는 반드시
    이동/정지로 나눠서 낸다 — 정지 케이스는 애초에 안 움직여 처음 예측이 계속 맞기
    쉬워서, 합쳐서 평균내면 실제보다 좋아 보이는 착시가 생긴다(2026-07-28 발견)."""
    from collections import defaultdict
    by_combo: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_combo[r["combo"]].append(r)

    def _avg(rows: list[dict], key: str) -> float:
        vals = [r[key] for r in rows if r.get(key) is not None]
        return sum(vals) / len(vals) if vals else float("nan")

    lines = ["| combo | type | periodic | kl | 탐지율 | 평균탐지지연(분) | "
             "정확도(이동) | 정확도(정지) | 중심점km(이동) | 평균정책재실행 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for label, rows in sorted(by_combo.items(), key=lambda kv: (kv[1][0]["combo_type"], kv[0])):
        moved = [r for r in rows if r["moved"]]
        stationary = [r for r in rows if not r["moved"]]
        detect_rate = (sum(r["detected"] for r in moved) / len(moved) * 100) if moved else float("nan")
        delays = [r["detection_delay_min"] for r in moved if r["detected"]]
        avg_delay = sum(delays) / len(delays) if delays else float("nan")
        avg_policy = sum(r["policy_reruns"] for r in rows) / len(rows)
        r0 = rows[0]
        lines.append(f"| {label} | {r0['combo_type']} | {r0['periodic_minutes']} | "
                     f"{r0['kl_threshold']} | {detect_rate:.1f}% | {avg_delay:.1f} | "
                     f"{_avg(moved, 'poa_accuracy_final'):.4f} | {_avg(stationary, 'poa_accuracy_final'):.4f} | "
                     f"{_avg(moved, 'centroid_km_final'):.3f} | {avg_policy:.2f} |")
    return "\n".join(lines)


def build_worlds(n_moved: int, n_stationary: int, max_attempts: int) -> list[World]:
    """이동/정지 쿼터 기반 생성(D3 generate() 관례) — 자연 발생 이동 비율이 낮아
    (실측 파일럿 15세계 중 20%) 그냥 순차 생성하면 탐지지연 통계용 '이동' 표본이
    너무 적어진다. 라벨을 강제하는 게 아니라(순환 아님), t_move_hours 가
    None인지 아닌지로 사후 분류해 목표 개수가 찰 때까지 반복 생성한다."""
    rng = random.Random(20260728)
    worlds: list[World] = []
    n_mv = n_st = 0
    attempt = 0
    t0 = time.time()
    while (n_mv < n_moved or n_st < n_stationary) and attempt < max_attempts:
        seed = 20260728 * 1000 + attempt
        with contextlib.redirect_stdout(io.StringIO()):
            w = build_world(f"w{attempt}", seed, rng)
        attempt += 1
        moved = w.t_move_hours is not None
        if moved and n_mv >= n_moved:
            continue
        if not moved and n_st >= n_stationary:
            continue
        worlds.append(w)
        if moved:
            n_mv += 1
        else:
            n_st += 1
        if len(worlds) % 20 == 0:
            print(f"  세계 생성 {len(worlds)}/{n_moved + n_stationary} "
                  f"(이동{n_mv}/정지{n_st}, 시도{attempt}, {time.time() - t0:.0f}s)")
    print(f"세계 생성 완료: {len(worlds)}개 (이동 {n_mv}/{n_moved}, 정지 {n_st}/{n_stationary}, "
          f"시도 {attempt}/{max_attempts}, {time.time() - t0:.0f}s)")
    return worlds


def main(pilot: bool, n_worlds: int | None) -> None:
    n = n_worlds or (30 if pilot else 200)
    n_moved, n_stationary = n // 2, n - n // 2
    combos = build_combos()
    print(f"세계 {n}개(이동{n_moved}/정지{n_stationary} 목표) x 콤보 {len(combos)}개 "
          f"= 재생 {n * len(combos)}회")

    t_start = time.time()
    worlds = build_worlds(n_moved, n_stationary, max_attempts=n * 20)

    records: list[dict] = []
    total = len(worlds) * len(combos)
    done = 0
    for world in worlds:
        for combo in combos:
            records.append(replay_world(world, combo))
            done += 1
            if done % 200 == 0:
                print(f"  재생 {done}/{total} ({time.time() - t_start:.0f}s)")

    settings.layer2_periodic_minutes = DEFAULT_PERIODIC  # 실험 종료 후 원상복구
    settings.kl_divergence_threshold = DEFAULT_KL

    out_jsonl = OUT_DIR / ("records_pilot.jsonl" if pilot else "records.jsonl")
    with open(out_jsonl, "w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = summarize(records)
    out_md = OUT_DIR / "results" / ("layer2_gridsearch_pilot.md" if pilot else "layer2_gridsearch.md")
    out_md.write_text(
        f"# 층2 그리드서치 결과 ({'파일럿' if pilot else '본실험'})\n\n"
        f"세계 {len(worlds)}개 x 콤보 {len(combos)}개, 소요 {time.time() - t_start:.0f}초\n\n"
        f"{summary}\n", encoding="utf-8")

    print(f"저장: {out_jsonl} ({len(records)}행), {out_md}")
    print(f"총 소요: {time.time() - t_start:.0f}초")
    print()
    print(summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--n-worlds", type=int, default=None)
    args = parser.parse_args()
    main(pilot=args.pilot, n_worlds=args.n_worlds)
