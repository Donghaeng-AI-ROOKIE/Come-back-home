"""P1-2(재정의: 거리 앵커 방어 패키지) — 국내 치매군 이동 예산 실측 vs 설계 상수.

데이터: AI Hub 「치매 고위험군 웨어러블 라이프로그」 계열 병합 CSV
(반지형 웨어러블 person-day 활동, DIAG_NM ∈ {CN, MCI, Dem}).
대용량 원본 CSV 는 레포에 넣지 않는다 — --csv 로 경로 지정.

산출(LLM 0회, stdlib 만):
  1. 일일 이동 예산   — 그룹별 movement(m)·걸음수 분포 (person-day 풀 + 피험자 단위)
  2. 활동 시간 구조   — 하루 활동분(low+med+high)·활동 중 이동률(m/분)·보폭
  3. 연속 활동 bout   — 5분 클래스(≥3) 연속 구간 길이 분포 (배회 중 정지 모델 근거)
  4. 시간대 프로파일  — 시간대별 활동 비율, 야간(22~06시) 활동 점유율
  5. 정합 판정        — WALK_SPEED 48m/분·피로 1.3·v_max 4.32km/h·Koester 1h 앵커 대조

주의: 웨어러블은 위치가 없다 — 발견거리 분포·μ/σ 검증에는 못 쓴다(그건 ISRID 몫).
여기서 재는 것은 "하루 이동 총량·연속 활동 구조"라는 워커 동역학의 상식 범위다.

실행:
  .venv/bin/python experiments/wearable_budget/run_budget_match.py \
      --csv "~/Downloads/AI Hub 웨어러블/wearable_activity_merged.csv"
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "results"

CLASS_COL = "CONVERT(activity_class_5min USING utf8)"
GROUPS = ["CN", "MCI", "Dem"]
ACTIVE_CLASS = 3          # 3=low 이상을 '활동'으로 본다 (0=미착용 1=휴식 2=비활동)
NIGHT_HOURS = {22, 23, 0, 1, 2, 3, 4, 5}   # 야간 = 22:00~06:00
DAY_START_HOUR = 4        # activity_day_start 04:00 KST — 블록 0 의 시각

# 대조할 설계 상수 (backend 코드 실값 — 바뀌면 여기도 갱신)
WALK_SPEED_M_PER_MIN_DEM = 48.0     # app/phase2/gauges.py WALK_SPEED_M_PER_MIN
FATIGUE_MULT_DEM = 1.3              # app/phase2/gauges.py _FATIGUE_MULT
VMAX_DEM_KMH = 4.32                 # app/config.py reach_vmax_dementia_kmh
KOESTER_1H_P50_KM = 1.1             # ISRID Dementia Urban p50 (Laing 2013 Table 1)


def q(vals: list[float], p: float) -> float:
    """분위수 (n 이 작아도 동작하는 단순 보간)."""
    s = sorted(vals)
    k = (len(s) - 1) * p
    lo = int(k)
    return s[lo] + (s[min(lo + 1, len(s) - 1)] - s[lo]) * (k - lo)


def load_days(csv_path: Path) -> tuple[dict[str, list[dict]], dict[str, int], int]:
    """유효일만 추린 person-day 목록(그룹별)과 필터 카운트."""
    days: dict[str, list[dict]] = defaultdict(list)
    dropped = defaultdict(int)
    arith_ok = arith_n = 0
    with open(csv_path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            grp = r["DIAG_NM"]
            if grp not in GROUPS:
                dropped["라벨외"] += 1
                continue
            try:
                steps = float(r["activity_steps"])
                move = float(r["activity_daily_movement"])
                non_wear = float(r["activity_non_wear"] or 0)
                active_min = sum(float(r[c] or 0) for c in
                                 ("activity_low", "activity_medium", "activity_high"))
                total_col = float(r["activity_total"] or 0)
            except (ValueError, KeyError):
                dropped["파싱실패"] += 1
                continue
            seq = [int(x) for x in
                   (r.get(CLASS_COL) or "").strip().strip("/").split("/") if x.isdigit()]
            # 유효일 = 하루 완전 기록(288블록) + 착용(비착용 2h 미만) + 보행 존재
            if len(seq) != 288:
                dropped["시퀀스불완전"] += 1
                continue
            if non_wear >= 120:
                dropped["비착용2h이상"] += 1
                continue
            if steps <= 0 or move <= 0:
                dropped["보행0"] += 1
                continue
            # 분 단위 검산: rest+inactive+active+non_wear ≈ 1440
            try:
                mins = (float(r["activity_rest"]) + float(r["activity_inactive"])
                        + active_min + non_wear)
                arith_n += 1
                if abs(mins - 1440) <= 10:
                    arith_ok += 1
            except (ValueError, KeyError):
                pass
            days[grp].append({
                "email": r["EMAIL"], "steps": steps, "move_m": move,
                "active_min": active_min if active_min > 0 else total_col,
                "seq": seq,
            })
    print(f"[검산] rest+inactive+active+non_wear≈1440분: {arith_ok}/{arith_n}")
    print(f"[필터] 제외 사유: {dict(dropped)}")
    return days, dict(dropped), arith_ok


def bouts_of(seq: list[int]) -> list[int]:
    """활동(클래스≥3) 연속 블록 길이 목록 (블록 = 5분)."""
    out, run = [], 0
    for c in seq:
        if c >= ACTIVE_CLASS:
            run += 1
        elif run:
            out.append(run)
            run = 0
    if run:
        out.append(run)
    return out


def hour_of_block(i: int) -> int:
    return (DAY_START_HOUR + (5 * i) // 60) % 24


def analyze(days: dict[str, list[dict]]) -> dict:
    res: dict = {}
    for grp in GROUPS:
        rows = days[grp]
        by_subj: dict[str, list[dict]] = defaultdict(list)
        for d in rows:
            by_subj[d["email"]].append(d)

        moves = [d["move_m"] for d in rows]
        steps = [d["steps"] for d in rows]
        strides = [d["move_m"] / d["steps"] for d in rows]
        act_mins = [d["active_min"] for d in rows if d["active_min"] > 0]
        ambient = [d["move_m"] / d["active_min"] for d in rows if d["active_min"] > 0]

        # 피험자 단위(person-day 의사반복 방지): 피험자별 중앙값의 그룹 통계
        subj_move_med = [st.median([d["move_m"] for d in ds]) for ds in by_subj.values()]
        subj_daycnt = sorted(len(ds) for ds in by_subj.values())

        all_bouts: list[int] = []
        subj_max_bout: list[int] = []
        night_active = total_active = 0
        hour_active = [0] * 24
        hour_total = [0] * 24
        for ds in by_subj.values():
            smax = 0
            for d in ds:
                bs = bouts_of(d["seq"])
                all_bouts += bs
                smax = max(smax, max(bs, default=0))
                for i, c in enumerate(d["seq"]):
                    if c == 0:      # 미착용 블록은 분모에서 제외
                        continue
                    h = hour_of_block(i)
                    hour_total[h] += 1
                    if c >= ACTIVE_CLASS:
                        hour_active[h] += 1
                        total_active += 1
                        if h in NIGHT_HOURS:
                            night_active += 1
            subj_max_bout.append(smax)

        res[grp] = {
            "subjects": len(by_subj), "days": len(rows),
            "days_per_subj_min_max": [subj_daycnt[0], subj_daycnt[-1]],
            "move_m": {"p25": q(moves, .25), "p50": q(moves, .50),
                       "p75": q(moves, .75), "p90": q(moves, .90)},
            "move_m_subj_median": {"p50": st.median(subj_move_med),
                                   "min": min(subj_move_med), "max": max(subj_move_med)},
            "steps_p50": q(steps, .50),
            "stride_m_p50": q(strides, .50),
            "active_min_p50": q(act_mins, .50),
            "ambient_rate_m_per_min_p50": q(ambient, .50),
            "bout_min": {"p50": q(all_bouts, .50) * 5, "p90": q(all_bouts, .90) * 5,
                         "p99": q(all_bouts, .99) * 5, "n": len(all_bouts)},
            "subj_max_bout_min_p50": st.median(subj_max_bout) * 5,
            "night_active_share": night_active / total_active if total_active else None,
            "hourly_active_rate": [round(hour_active[h] / hour_total[h], 4)
                                   if hour_total[h] else None for h in range(24)],
        }
    return res


def write_report(res: dict, dropped: dict, csv_name: str) -> str:
    dem, cn = res["Dem"], res["CN"]
    # 정합 지표
    budget_h = dem["move_m"]["p50"] / (WALK_SPEED_M_PER_MIN_DEM * 60)
    path_1h_km = WALK_SPEED_M_PER_MIN_DEM * 60 / 1000
    tortuosity = path_1h_km / KOESTER_1H_P50_KM

    L = ["# P1-2 — 국내 치매군 이동 예산 실측 vs 워커 설계 상수", "",
         f"입력: `{csv_name}` (레포 외부). 유효일 필터 = 288블록 완전기록 + "
         "비착용 2h 미만 + 보행 존재. 제외 내역: "
         + ", ".join(f"{k} {v}" for k, v in dropped.items()) + ".", "",
         "## 1. 일일 이동 예산 (person-day 풀 / [피험자 중앙값])", "",
         "| 그룹 | 인원 | 유효일 | 이동 p25 | p50 | p75 | p90 | 걸음 p50 | 보폭 p50 |",
         "|---|---|---|---|---|---|---|---|---|"]
    for g in GROUPS:
        r = res[g]
        L.append(f"| {g} | {r['subjects']} | {r['days']} "
                 f"| {r['move_m']['p25']:.0f}m | **{r['move_m']['p50']:.0f}m "
                 f"[{r['move_m_subj_median']['p50']:.0f}m]** "
                 f"| {r['move_m']['p75']:.0f}m | {r['move_m']['p90']:.0f}m "
                 f"| {r['steps_p50']:.0f} | {r['stride_m_p50']:.2f}m |")
    L += ["",
          f"피험자별 유효일 범위: Dem {dem['days_per_subj_min_max']} — **인원 "
          f"{dem['subjects']}명**은 반드시 병기(표본 과장 방지).", "",
          "## 2. 활동 구조 · 연속 활동 bout", "",
          "| 그룹 | 활동분/일 p50 | 활동 중 이동률 p50 | bout p50 | p90 | p99 "
          "| 피험자 최장 bout p50 | 야간(22~06) 활동 점유 |",
          "|---|---|---|---|---|---|---|---|"]
    for g in GROUPS:
        r = res[g]
        L.append(f"| {g} | {r['active_min_p50']:.0f}분 "
                 f"| {r['ambient_rate_m_per_min_p50']:.1f} m/분 "
                 f"| {r['bout_min']['p50']:.0f}분 | {r['bout_min']['p90']:.0f}분 "
                 f"| {r['bout_min']['p99']:.0f}분 | {r['subj_max_bout_min_p50']:.0f}분 "
                 f"| {r['night_active_share']*100:.1f}% |")
    L += ["", "## 3. 설계 상수 정합 판정", "",
          f"- **하루 예산 소진 시간**: Dem 일일 이동 p50 {dem['move_m']['p50']:.0f}m ÷ "
          f"워커 속도 {WALK_SPEED_M_PER_MIN_DEM:.0f}m/분 = **연속 보행 "
          f"{budget_h:.1f}h 이면 평소 하루 이동량 전부 소진**. 장시간 경과(3h+) "
          "시나리오에서 피로 정지(rest, 배수 1.3)가 필수라는 국내 데이터 근거.",
          f"- **연속 활동 실측**: Dem bout p99 {dem['bout_min']['p99']:.0f}분, 피험자 "
          f"최장 bout 중앙값 {dem['subj_max_bout_min_p50']:.0f}분 — '수 시간 무정지 "
          "보행' 가정은 평시 데이터와 불합치. 워커 fatigue_fired→rest() 설계와 정합.",
          f"- **굴곡비 sanity**: 워커 1h 경로 {path_1h_km:.2f}km vs Koester 1h 변위 "
          f"p50 {KOESTER_1H_P50_KM}km → 경로/변위 {tortuosity:.1f}배. 배회 경로의 "
          "비직선성(테스트셋 검증에서 확인된 성질)과 방향 일치.",
          f"- **속도 상수 위치**: 활동 중 이동률(Dem "
          f"{dem['ambient_rate_m_per_min_p50']:.1f}m/분)은 일상 저강도 활동 평균이라 "
          f"배회 보행의 하한, v_max {VMAX_DEM_KMH}km/h(={VMAX_DEM_KMH*1000/60:.0f}m/분)"
          f"는 상한 — 48m/분은 그 사이. 웨어러블엔 위치가 없어 보행 순간속도 직접 "
          "실측은 불가(한계 명기).",
          f"- **야간 활동**: Dem 야간 점유 {dem['night_active_share']*100:.1f}% vs CN "
          f"{cn['night_active_share']*100:.1f}% — **역방향**(치매군이 더 낮음). 관리 중 "
          "코호트라 야간 배회 신호가 안 잡히는 것으로 해석 — 야간 배회 prior 를 이 "
          "데이터로 정당화할 수 없음(정직 표기).", "",
          "## 한계", "",
          "- 위치정보 없음 → 발견거리 분포·μ/σ 보정에는 사용 불가(ISRID 몫 불변).",
          f"- Dem 인원 {dem['subjects']}명(코호트 = 관리 중 경증 위주 가능성) — "
          "실종 위험군과 활동 수준이 다를 수 있음.",
          "- 활동 클래스는 강도 기반이라 '보행'과 '제자리 활동'을 완전 구분 못 함.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="~/Downloads/AI Hub 웨어러블/wearable_activity_merged.csv")
    args = ap.parse_args()
    csv_path = Path(args.csv).expanduser()
    if not csv_path.exists():
        print(f"CSV 없음: {csv_path} — 대용량 원본은 레포 밖에서 --csv 로 지정")
        return 1
    days, dropped, _ = load_days(csv_path)
    res = analyze(days)
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "budget_match.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    md = write_report(res, dropped, csv_path.name)  # 파일명만 — 개인 절대경로 유출 방지
    (OUT_DIR / "budget_match.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
