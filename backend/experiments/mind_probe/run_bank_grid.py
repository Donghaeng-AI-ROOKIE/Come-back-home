"""실추출 페르소나 뱅크 기반 마음 재해석 그리드 — 수정 전/후 공용 측정기.

mind_probe_dev_fixture_v1.json(실 Mi:dm 추출 산출물)을 Persona 로 복원해 reinterpret_mind 를
실호출한다. 손제작 페르소나 그리드(run_persona_grid.py)와 달리 라벨 품질·중복
노트·근거 등급이 전부 실사용 형태다.

사전 성공 기준 (수정 후 통과해야 하는 것 — 실행 전 등록):
  C1 균형(MB_dem_bal): 순서 정/역 양방향 모두에서 분산 (첫 후보 고착 해소)
  C2 발달(MB_dd_*): 치매 서사(옛집·time-shift 등) 0건
  C3 대조쌍: 자전 강(hi, 노트에 방앗간 반복시도) vs 약(lo) 출력 차이 발현
  C4 회귀 — 편중(MB_dem_biased): 옛집 우세 유지 (0.9 근거가 씻기면 실패)
  C5 회귀 — 발달 고착(MB_dd_fix): 청량리역(0.5) ≥ 기차역(0.3) 우세 유지
  C6 빈약(MB_dem_poor): 후보 0 → goal null 유지, 지어내기 0

실행: cd backend && .venv/bin/python -m experiments.mind_probe.run_bank_grid --tag before
"""
from __future__ import annotations

import argparse
import collections
import importlib
import inspect
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.schemas.persona import Persona  # noqa: E402
from app.schemas.prediction import LognormalParams, MindState, PriorParams  # noqa: E402

RESULTS = Path(__file__).parent / "results"
_STRATEGY = {"route_following": 0.3, "direction_keeping": 0.15, "random_walk": 0.15,
             "backtracking": 0.1, "staying_put": 0.1, "landmark_seeking": 0.2}
_DEM_NARRATIVE = re.compile(r"치매|time.?shift|옛집|과거로 착각|그 시절")

GAUGES = {
    "귀소": "집을 나선 지 90분 경과. 피로도: 중간, 혼란도: 중간, 귀소 충동: 높음, 불안: 낮음. 방금 귀소 게이지가 임계를 넘었다.",
    "불안": "집을 나선 지 60분 경과. 피로도: 중간, 혼란도: 중간, 귀소 충동: 낮음, 불안: 높음. 방금 불안 게이지가 임계를 넘었다.",
}


def load_bank() -> dict[str, Persona]:
    raw = json.loads((RESULTS / "mind_probe_dev_fixture_v1.json").read_text(encoding="utf-8"))
    out = {}
    for k, v in raw.items():
        if v.get("ok") and v.get("persona"):
            out[k] = Persona.model_validate(v["persona"])
    return out


def prior_for(p: Persona) -> PriorParams:
    total = sum(a.weight for a in p.attraction_points) or 1.0
    return PriorParams(
        strategy_probs=dict(_STRATEGY),
        attraction_weights={a.label: a.weight / total for a in p.attraction_points},
        radius_lognormal=LognormalParams(mu=0.095, sigma=1.48),
        reasoning="(뱅크 고정 prior)")


def reversed_persona(p: Persona) -> Persona:
    q = p.model_copy(deep=True)
    q.attraction_points = list(reversed(q.attraction_points))
    return q


def main(tag: str, n: int) -> None:
    ex = importlib.import_module("app.llm.exaone")
    client = ex.ExaoneClient()
    accepts_rng = "rng" in inspect.signature(client.reinterpret_mind).parameters

    bank = load_bank()
    # 균형 페르소나는 순서 정/역 두 조건으로 측정 (C1)
    conditions: list[tuple[str, Persona]] = []
    for key, p in bank.items():
        conditions.append((key, p))
        if key == "MB_dem_bal":
            conditions.append((key + "_rev", reversed_persona(p)))

    total = len(conditions) * len(GAUGES) * n
    print(f"[bank-grid:{tag}] model={client.model} rng지원={accepts_rng} "
          f"조건 {len(conditions)} × 게이지 {len(GAUGES)} × {n} = {total}콜")

    rows: list[dict] = []
    for ckey, p in conditions:
        labels = [a.label for a in p.attraction_points]
        prior = prior_for(p)
        for gname, greport in GAUGES.items():
            for i in range(n):
                kwargs = {}
                if accepts_rng:
                    kwargs["rng"] = random.Random(hash((ckey, gname, i)) & 0xFFFF)
                before = client.call_log[-1]["ts"] if client.call_log else None
                mind, goal = client.reinterpret_mind(
                    p, MindState(status="이동 중", confusion=0.5), greport,
                    labels, prior, None, **kwargs)
                ok = bool(client.call_log) and client.call_log[-1]["ts"] != before
                raw = client.call_log[-1]["response"] if ok else ""
                rows.append(dict(cond=ckey, gauge=gname, rep=i, ok=ok, goal=goal,
                                 conf=mind.confusion, status=mind.status, raw=raw))
        got = [r for r in rows if r["cond"] == ckey and r["ok"]]
        gd = collections.Counter(str(r["goal"]) for r in got)
        print(f"  {ckey}: {dict(gd)}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    (RESULTS / f"bank_grid_{tag}_{ts}.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")

    # ── 집계 + 기준 판정 ──
    by: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        if r["ok"]:
            by[r["cond"]].append(r)

    def dist(key: str) -> collections.Counter:
        return collections.Counter(str(r["goal"]) for r in by.get(key, []))

    def top_share(c: collections.Counter) -> float:
        t = sum(c.values())
        return (c.most_common(1)[0][1] / t) if t else 0.0

    lines = [f"# 뱅크 그리드 [{tag}] — {ts}", f"모델 {client.model} · n={n}/게이지 · rng={accepts_rng}", "",
             "| 조건 | goal 분포 | conf 분포 | 고유 status | 치매서사 |", "|---|---|---|---|---|"]
    for ckey, _ in conditions:
        rs = by.get(ckey, [])
        gd = " ".join(f"{k}:{v}" for k, v in dist(ckey).most_common()) or "-"
        cd = " ".join(f"{k}:{v}" for k, v in sorted(collections.Counter(r["conf"] for r in rs).items()))
        us = len({r["status"] for r in rs})
        dem = sum(1 for r in rs if _DEM_NARRATIVE.search(r["raw"] or r["status"] or ""))
        lines.append(f"| {ckey} | {gd} | {cd} | {us} | {dem}/{len(rs)} |")

    bal_f, bal_r = dist("MB_dem_bal"), dist("MB_dem_bal_rev")
    dd_dem = sum(1 for k in ("MB_dd_fix", "MB_dd_avoid")
                 for r in by.get(k, []) if _DEM_NARRATIVE.search(r["raw"] or ""))
    hi_rs, lo_rs = by.get("MB_dem_pair_hi", []), by.get("MB_dem_pair_lo", [])
    hi_sig = collections.Counter((str(r["goal"]), r["conf"]) for r in hi_rs)
    lo_sig = collections.Counter((str(r["goal"]), r["conf"]) for r in lo_rs)
    biased_top = dist("MB_dem_biased").most_common(1)
    fix_d = dist("MB_dd_fix")
    poor_bad = sum(1 for r in by.get("MB_dem_poor", []) if r["goal"] is not None)

    lines += ["", "## 사전 기준 판정", "",
              f"- C1 균형 양방향 분산: 정 {dict(bal_f)} / 역 {dict(bal_r)} — "
              f"{'⚠ 고착' if (top_share(bal_f) >= 0.9 or top_share(bal_r) >= 0.9) else '통과'}",
              f"- C2 발달 치매서사: {dd_dem}건 — {'⚠ 오염' if dd_dem else '통과'}",
              f"- C3 대조쌍 차이: hi {dict(hi_sig)} vs lo {dict(lo_sig)} — "
              f"{'통과(차이 있음)' if hi_sig != lo_sig else '⚠ 무차이'}",
              f"- C4 편중 회귀: 최빈 {biased_top} — "
              f"{'통과(옛집 우세)' if biased_top and '옛집' in biased_top[0][0] else '⚠ 개인화 신호 소실'}",
              f"- C5 발달고착 회귀: {dict(fix_d)} — "
              f"{'통과(청량리 우세)' if fix_d and '청량리' in fix_d.most_common(1)[0][0] else '⚠'}",
              f"- C6 빈약 절제: 비-null {poor_bad}건 — {'통과' if not poor_bad else '⚠ 지어냄'}", ""]
    out = RESULTS / f"bank_grid_{tag}_{ts}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[-10:]))
    print(f"[bank-grid:{tag}] 저장: {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True, choices=["before", "after"])
    ap.add_argument("--n", type=int, default=5)
    main(ap.parse_args().tag, ap.parse_args().n)
