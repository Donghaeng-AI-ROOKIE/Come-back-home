"""P1-4 — D3 임계값 실험용 타임라인 생성.

정답(이동/정지)을 사람이 미리 라벨링하지 않는다. 대신:
1. 실제 Phase2 시뮬(Koester 기반 `simulation.run_monte_carlo`)로 "진짜 궤적" 1개를 뽑는다
   (n_walkers=1 + SimTrace로 경로 기록).
2. 초기 예측(pipeline.run_prediction)으로 POA를 만들고, 그 시점 알림 커버리지를
   last_alert_poa(footprint)로 고정한다 — 타임라인 내내 갱신하지 않는다(순환 방지,
   메모리 project_p1_4_d3_threshold_spec.md 참고).
3. 품질별(고신뢰/저신뢰/허위) 합성 제보를 진짜 궤적 근처(고·저) 또는 무관한 곳(허위)에
   뿌려 실제 trust/classify_tip/layer1_update/pipeline.run_prediction으로 POA를 진화시킨다.
4. 타임라인 종료 시점에 "진짜 위치가 footprint 밖으로 갔는가"가 결과적으로 결정된다
   (미리 정하지 않음) — 목표 개수(양/음성)에 도달할 때까지 반복 생성한다.

구체성(specificity)은 tip_llm(스텁)을 거치지 않고 trust.score_tip(structured=...)에
직접 주입한다 — 스텁 키워드 휴리스틱의 부정확성에 실험이 휘둘리지 않게 하기 위함
(2026-07-25/26 설계 확정, B경로).

실행: backend/ 에서
    python experiments/d3_threshold/gen_timelines.py --pilot   # 파일럿 150개
    python experiments/d3_threshold/gen_timelines.py           # 본 실험 3,200개
"""

from __future__ import annotations

import contextlib
import io
import json
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from app import llm, storage
from app.config import settings
from app.geo import h3grid
from app.llm.exaone import _KOESTER_PARAMS
from app.phase2 import pipeline, simulation
from app.phase3 import alerts, poa_update, trust, triggers
from app.schemas.case import Case, CaseStatus
from app.schemas.common import GeoPoint
from app.schemas.debug import SimTrace
from app.schemas.persona import Persona, PersonaType
from app.schemas.prediction import PriorParams
from app.schemas.report import MissingReport
from app.schemas.tip import Tip, TipDecision
from sim_testset import LKP, _STRATEGY_MIX  # noqa: E402 — 경로 삽입 후 임포트(관례)

OUT_DIR = Path(__file__).resolve().parent
_KOESTER = _KOESTER_PARAMS  # {PersonaType: LognormalParams}

# ★실제 .env 에 EXAONE_API_KEY 가 채워져 있어(is_stub=False) pipeline.run_prediction 이
# 그대로면 매 호출마다 진짜 EXAONE 네트워크 호출을 시도한다(실측: 콜당 ~3.4초, 팀이
# 이미 GPU/서빙 에러로 막힌 상태라고 확인함). 이 실험은 "LLM 호출 0회" 설계라 싱글턴
# 인스턴스의 api_key 를 직접 비워 강제 스텁 모드로 만든다(settings.exaone_api_key 를
# 바꿔도 이미 만들어진 llm.exaone 인스턴스엔 반영 안 됨 — base.py:13 처럼 생성 시점에
# 캡처된 인스턴스 속성이라 인스턴스 자체를 건드려야 함). 이 프로세스 안에서만 유효.
llm.exaone.api_key = ""

# 진짜 궤적 경과시간 범위 — 하한을 45분(층2 주기 트리거) 위로 올려, 늦게 도착하는
# 제보가 최소 한 번은 주기 재실행을 받을 여지를 준다(2026-07-26 파일럿에서 천장
# 85.3%로 낮게 나온 원인 — 재실행이 아예 없어 layer1_update 만으로는 POA 가 새 셀을
# 못 만드는 "정보부족" 케이스가 14.7%였음, N_REPORTS_RANGE 도 같이 올려 대응).
ELAPSED_HOURS_RANGE = (1.0, 2.5)
# 초기 예측(=footprint 확정) 시점 — 시뮬 시작 직후로 고정(신고 접수 직후 첫 예측).
INITIAL_PREDICT_DELAY_H = 0.1
# 타임라인 하나당 합성 제보 개수 범위(누적 신고 현실감) — 2~6 → 4~10 로 상향
# (고신뢰 제보가 한 번도 안 뽑힐 확률을 줄여 정보부족 놓침 비중 완화).
N_REPORTS_RANGE = (4, 10)

# 제보 품질 혼합 — (고신뢰, 저신뢰, 허위) 비율. 2026-07-25/26 확정.
QUALITY_MIXES: dict[str, tuple[float, float, float]] = {
    "baseline": (0.30, 0.50, 0.20),
    "false_stress_10": (0.30 * 0.9 / 0.8, 0.50 * 0.9 / 0.8, 0.10),
    "false_stress_30": (0.30 * 0.7 / 0.8, 0.50 * 0.7 / 0.8, 0.30),
    "low_quality": (0.15, 0.65, 0.20),
}

_SPECIFICITY_BY_QUALITY = {"high": "상", "low": "하"}


@dataclass
class SyntheticTip:
    t_hours: float
    quality: str            # "high" | "low" | "false"
    lat: float
    lng: float
    specificity: str        # "상"|"중"|"하" — trust.score_tip 에 직접 주입


@dataclass
class Timeline:
    id: str
    mix_name: str
    persona_type: str
    elapsed_hours: float
    lkp: tuple[float, float]
    lkp_time: str
    true_final: tuple[float, float]         # 진짜 최종 위치(정답 산출용)
    true_path: list[list[float]]            # [[lat,lng], ...] 20스텝 진짜 경로
    reports: list[dict] = field(default_factory=list)


def _true_position_at(path: list[list[float]], t_hours: float, elapsed_hours: float) -> GeoPoint:
    """20스텝 경로에서 t_hours 시점 위치(최근접 스텝 보간)."""
    if elapsed_hours <= 0:
        idx = 0
    else:
        idx = round((t_hours / elapsed_hours) * (len(path) - 1))
    idx = max(0, min(len(path) - 1, idx))
    lat, lng = path[idx]
    return GeoPoint(lat=lat, lng=lng)


def _make_persona(ptype: PersonaType, rng: random.Random) -> Persona:
    age = rng.randint(70, 85) if ptype == PersonaType.dementia else rng.randint(10, 30)
    return Persona(id="synthperson-" + storage.new_id(), type=ptype,
                   name="합성", age=age, home=LKP)


def _true_prior(ptype: PersonaType) -> PriorParams:
    """진짜 궤적용 prior — 실제 Koester 파라미터·전략 혼합 그대로(sim_testset 재사용)."""
    return PriorParams(strategy_probs=_STRATEGY_MIX[ptype], attraction_weights={},
                       radius_lognormal=_KOESTER[ptype], reasoning="합성 진짜 궤적")


def _simulate_truth(ptype: PersonaType, elapsed_hours: float, seed: int,
                    persona: Persona) -> list[list[float]]:
    """진짜 궤적 1개 — statistical 모드(LLM 무관) n_walkers=1 + SimTrace 경로 기록."""
    prior = _true_prior(ptype)
    trace = SimTrace(max_paths=1)
    v_max = None  # run_monte_carlo 내부에서 persona 기반으로 계산
    simulation.run_monte_carlo(LKP, prior, persona, elapsed_hours, mode="statistical",
                               net=None, n_walkers=1, seed=seed, trace=trace)
    if not trace.walkers:
        # 이론상 도달 안 함(trace_path(0) 는 max_paths=1 이라 항상 True) — 방어
        return [[LKP.lat, LKP.lng]]
    return trace.walkers[0].path


def _sample_quality(mix: tuple[float, float, float], rng: random.Random) -> str:
    r = rng.random()
    high, low, _false = mix
    if r < high:
        return "high"
    if r < high + low:
        return "low"
    return "false"


def _make_report_location(quality: str, true_pos: GeoPoint, rng: random.Random) -> GeoPoint:
    """품질별 제보 위치. 고/저신뢰는 진짜 위치 근처(노이즈만 다름), 허위는 진짜 위치와 무관."""
    if quality == "high":
        bearing = rng.uniform(0, 2 * 3.141592653589793)
        noise_km = rng.uniform(0.0, 0.1)   # ~0~100m
        return h3grid.move(true_pos, bearing, noise_km)
    if quality == "low":
        bearing = rng.uniform(0, 2 * 3.141592653589793)
        noise_km = rng.uniform(0.1, 0.5)   # ~100~500m
        return h3grid.move(true_pos, bearing, noise_km)
    # false — 진짜 위치와 무관한 임의 지점. 2026-07-26 파일럿에서 0.5~3km 범위가
    # reachability.plausibility() 의 도달반경(d_max=v_max×경과시간, 후반 시각일수록
    # 커짐)에 거의 항상 들어가 "장소가 무관하다"는 의도가 실제로는 거의 항상 통과로
    # 나온 문제 발견(허위제보 32.8%가 층2까지 도달) — 범위를 넓혀 개연성이 실제로
    # 갈리게 한다(가까운 값은 우연히 통과, 먼 값은 물리적으로 불가능해 걸러짐).
    bearing = rng.uniform(0, 2 * 3.141592653589793)
    dist_km = rng.uniform(1.0, 15.0)
    return h3grid.move(LKP, bearing, dist_km)


def _make_specificity(quality: str, rng: random.Random) -> str:
    if quality in _SPECIFICITY_BY_QUALITY:
        return _SPECIFICITY_BY_QUALITY[quality]
    # 허위 — 확신에 차 보이는(구체적인) 허위 목격도 있지만 드물어야 현실적이다.
    # 균등분포(1/3씩)였던 걸 하/중 쪽으로 기울임(2026-07-26 파일럿 발견 반영).
    return rng.choices(["상", "중", "하"], weights=[0.15, 0.35, 0.50])[0]


def gen_one_timeline(mix_name: str, mix: tuple[float, float, float],
                    rng: random.Random, seed: int) -> tuple[Timeline, bool]:
    """타임라인 1개 생성 + 처리 → (Timeline, 정답positive 여부).

    last_alert_poa(footprint)는 초기 예측 시점에 한 번만 고정한다 — 타임라인 내내
    다시 갱신하지 않는다(순환 방지, 메모리 설계 참고). 정답은 타임라인 종료 시점
    진짜 위치가 이 footprint 밖인지로 사후 결정된다(미리 안 정함).
    """
    ptype = rng.choice([PersonaType.dementia, PersonaType.intellectual_disability])
    elapsed_hours = rng.uniform(*ELAPSED_HOURS_RANGE)
    persona = _make_persona(ptype, rng)
    true_path = _simulate_truth(ptype, elapsed_hours, seed, persona)

    t0 = datetime(2026, 1, 1, 12, 0, 0)   # 임의 고정 기준시각(seed 로 재현성 보장)
    report = MissingReport(id="synthreport-" + storage.new_id(), persona_id=persona.id,
                           missing_type=ptype, lkp=LKP, lkp_time=t0)
    case = Case(id="synthcase-" + storage.new_id(), report=report,
               lkp=LKP, lkp_time=t0)
    storage.personas.save(persona.id, persona)
    storage.cases.save(case.id, case)

    # 초기 예측 — footprint 고정 시점. run_prediction 은 EXAONE(스텁) 자체 prior 사용
    # (진짜 궤적의 prior 와 별개 — "우리 믿음(POA)"과 "진짜 물리적 위치"는 독립).
    init_time = t0 + timedelta(hours=INITIAL_PREDICT_DELAY_H)
    pipeline.run_prediction(case, now=init_time, seed=seed + 1)
    case.last_alert_poa = dict(case.current_poa)
    case.last_alert_at = init_time
    footprint = set(case.last_alert_poa)

    n_reports = rng.randint(*N_REPORTS_RANGE)
    report_times = sorted(rng.uniform(0.05, elapsed_hours) for _ in range(n_reports))

    reruns = 0
    reports_log: list[dict] = []
    for t_h in report_times:
        quality = _sample_quality(mix, rng)
        true_pos = _true_position_at(true_path, t_h, elapsed_hours)
        loc = _make_report_location(quality, true_pos, rng)
        specificity = _make_specificity(quality, rng)
        seen_at = t0 + timedelta(hours=t_h)

        tip = Tip(id="synthtip-" + storage.new_id(), case_id=case.id, text="[합성 제보]",
                  location=loc, seen_at=seen_at)
        tip.p = trust.score_tip(tip, lkp=case.lkp, lkp_time=case.lkp_time,
                                persona_type=ptype, structured={"specificity": specificity})
        tip.decision = poa_update.classify_tip(tip.p, trust.has_specific_location_time(tip))
        reports_log.append({
            "t_hours": t_h, "quality": quality, "specificity": specificity,
            "p": tip.p, "decision": tip.decision.value,
        })

        if tip.decision == TipDecision.discard:
            continue

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

    # 종료 시점 정답 산출 — 진짜 위치 vs 고정 footprint (POA 와 독립)
    true_final = _true_position_at(true_path, elapsed_hours, elapsed_hours)
    true_final_cell = h3grid.cell_of(true_final)
    positive = true_final_cell not in footprint

    new_cells = set(case.current_poa or {}) - footprint
    total_new_mass = sum((case.current_poa or {}).get(c, 0.0) for c in new_cells)
    js = triggers.jensen_shannon_divergence(case.current_poa or {}, case.last_alert_poa or {})
    true_cell_prob = (case.current_poa or {}).get(true_final_cell, 0.0)

    tl = Timeline(
        id=case.id, mix_name=mix_name, persona_type=ptype.value, elapsed_hours=elapsed_hours,
        lkp=(LKP.lat, LKP.lng), lkp_time=t0.isoformat(),
        true_final=(true_final.lat, true_final.lng), true_path=true_path,
        reports=reports_log,
    )
    tl_dict = tl.__dict__ | {
        "positive": positive, "total_new_mass": total_new_mass, "js": js,
        "true_cell_prob": true_cell_prob, "reruns": reruns,
        "true_final_cell": true_final_cell,
        "footprint_size": len(footprint),
    }
    storage.personas.delete(persona.id)
    storage.cases.delete(case.id)
    return tl_dict, positive


def generate(mix_name: str, mix: tuple[float, float, float], target_pos: int, target_neg: int,
            seed_base: int, max_attempts: int) -> list[dict]:
    """목표 positive/negative 개수에 도달할 때까지 생성(자연 발생 비율 반영, 강제 라벨 없음)."""
    rng = random.Random(seed_base)
    rows: list[dict] = []
    n_pos = n_neg = 0
    attempt = 0
    while (n_pos < target_pos or n_neg < target_neg) and attempt < max_attempts:
        seed = seed_base * 100_000 + attempt
        with contextlib.redirect_stdout(io.StringIO()):  # pipeline.run_prediction 타이밍 로그 억제
            tl_dict, positive = gen_one_timeline(mix_name, mix, rng, seed)
        attempt += 1
        if positive and n_pos >= target_pos:
            continue
        if not positive and n_neg >= target_neg:
            continue
        rows.append(tl_dict)
        if positive:
            n_pos += 1
        else:
            n_neg += 1
    print(f"[{mix_name}] positive={n_pos}/{target_pos} negative={n_neg}/{target_neg} "
          f"(attempts={attempt}/{max_attempts})")
    return rows


def main(pilot: bool) -> None:
    all_rows: list[dict] = []
    if pilot:
        # 파일럿 150 — 하네스 검증 + 도달 가능 천장 확인. 기준 혼합만, 소규모.
        all_rows += generate("baseline", QUALITY_MIXES["baseline"], 75, 75,
                             seed_base=1, max_attempts=600)
    else:
        all_rows += generate("baseline", QUALITY_MIXES["baseline"], 1000, 1000,
                             seed_base=1, max_attempts=8000)
        all_rows += generate("false_stress_10", QUALITY_MIXES["false_stress_10"], 300, 300,
                             seed_base=2, max_attempts=3000)
        all_rows += generate("false_stress_30", QUALITY_MIXES["false_stress_30"], 300, 300,
                             seed_base=3, max_attempts=3000)
        all_rows += generate("low_quality", QUALITY_MIXES["low_quality"], 300, 300,
                             seed_base=4, max_attempts=3000)

    out_path = OUT_DIR / ("timelines_pilot.jsonl" if pilot else "timelines.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for row in all_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"저장: {out_path} ({len(all_rows)}개)")


if __name__ == "__main__":
    main(pilot="--pilot" in sys.argv)
