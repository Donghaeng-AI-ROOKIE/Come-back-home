"""마음 골드셋 평가기 — 04_gold.jsonl 의 범위 라벨로 reinterpret_mind 를 채점한다.

마음 단독 평가: 입력 페르소나를 (추출이 아니라) 골드 라벨 + 대본 답변으로 구성해
추출 오류와 마음 오류를 분리한다. (E2E 평가는 별도 — Phase 0 통과본으로 실행)

기본은 dev(G01~G08)만 실행한다. test(G09~G20)는 봉인 — `--split test --unseal` 을
명시해야 돌고, 실행 사실이 results/test_usage.log 에 기록된다(README 봉인 규칙).

채점:
  goal:      allowed 적중률 / forbidden 위반(치명) / 중립(등재됐으나 allowed 밖)
  confusion: confusion_range 안 비율
  서사:      발달 시나리오에서 치매 서사(regex) = forbidden_narratives 위반
  (expected_relation·대조쌍은 test 전용 — G09/G10·G15/G16 쌍 비교로 채점)

실행: cd backend && .venv/bin/python experiments/mind_goldset/eval_mind_goldset.py --n 4
"""
from __future__ import annotations

import argparse
import collections
import importlib
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1]))

from app.schemas.common import GeoPoint  # noqa: E402
from app.schemas.persona import AttractionPoint, Persona, PersonaType  # noqa: E402
from app.schemas.prediction import LognormalParams, MindState, PriorParams  # noqa: E402

RESULTS = HERE / "results"
_EV_W = {"previous_missing_found": 0.9, "caregiver_report": 0.5, "mention_only": 0.3}
_STRATEGY = {"route_following": 0.3, "direction_keeping": 0.15, "random_walk": 0.15,
             "backtracking": 0.1, "staying_put": 0.1, "landmark_seeking": 0.2}
_DEM_NARRATIVE = re.compile(r"치매|time.?shift|옛집|과거로 착각|그 시절")
_P = {"lat": 37.55, "lng": 127.0}
GAUGES = {
    "A_귀소": "집을 나선 지 90분 경과. 피로도: 중간, 혼란도: 중간, 귀소 충동: 높음, 불안: 낮음. 방금 귀소 게이지가 임계를 넘었다.",
    "B_불안": "집을 나선 지 60분 경과. 피로도: 중간, 혼란도: 중간, 귀소 충동: 낮음, 불안: 높음. 방금 불안 게이지가 임계를 넘었다.",
}

_DEM_IDS = {f"G{i:02d}" for i in list(range(1, 5)) + list(range(9, 15))}


def load_gold() -> dict[str, dict]:
    return {d["id"]: d for d in map(json.loads, (HERE / "04_gold.jsonl").open(encoding="utf-8"))}


def load_scenario_answers() -> dict[str, list[str]]:
    """01 대본의 보호자 답변을 골드 페르소나의 behavior_notes 원천으로 쓴다."""
    text = (HERE / "01_시나리오_대화_v1.md").read_text(encoding="utf-8")
    out: dict[str, list[str]] = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r"^## (G\d+)", line)
        if m:
            cur = m.group(1)
            out[cur] = []
        elif cur and line.startswith("- ") and ": " in line:
            slot, ans = line[2:].split(": ", 1)
            if slot not in ("identity", "home"):
                out[cur].append(ans.strip())
    return out


def persona_for(gid: str, gold: dict, answers: list[str]) -> Persona:
    ptype = PersonaType.dementia if gid in _DEM_IDS else PersonaType.intellectual_disability
    return Persona(
        id=f"gold-{gid}", name="(골드)", age=78 if ptype == PersonaType.dementia else 19,
        type=ptype, home=GeoPoint(**_P),
        attraction_points=[AttractionPoint(label=a["label"], location=GeoPoint(**_P),
                                           weight=_EV_W[a["evidence"]], evidence=a["evidence"])
                           for a in gold["attractions"]],
        behavior_notes=answers)


def prior_for(p: Persona) -> PriorParams:
    total = sum(a.weight for a in p.attraction_points) or 1.0
    return PriorParams(strategy_probs=dict(_STRATEGY),
                       attraction_weights={a.label: a.weight / total for a in p.attraction_points},
                       radius_lognormal=LognormalParams(mu=0.095, sigma=1.48),
                       reasoning="(골드 평가 고정)")


def main(split: str, n: int, unseal: bool, variant: str = "analyst",
         model: str | None = None) -> None:
    gold = load_gold()
    answers = load_scenario_answers()
    ids = sorted(g for g, d in gold.items() if d["split"] == split)
    if split == "test":
        if not unseal:
            sys.exit("test 는 봉인됨 — 최종 측정에만 --unseal 로 실행 (README 규칙)")
        with (RESULTS / "test_usage.log").open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now().isoformat()} test 실행 (n={n}, variant={variant})\n")

    ex = importlib.import_module("app.llm.exaone")
    if variant.startswith("first_person"):
        import first_person
        first_person.patch(ex, keep_rag=variant.endswith("_rag"))
    client = ex.ExaoneClient(model=model)
    print(f"[goldset-eval] split={split} 시나리오 {len(ids)} × 상황 2 × {n} = "
          f"{len(ids) * 2 * n}콜  model={client.model} variant={variant}")

    rows: list[dict] = []
    for gid in ids:
        g = gold[gid]
        p = persona_for(gid, g, answers.get(gid, []))
        labels = [a.label for a in p.attraction_points]
        prior = prior_for(p)
        for sk, report in GAUGES.items():
            lab = g["situations"][sk]
            allowed = set(lab["allowed_goals"]) - {None}
            allow_null = None in lab["allowed_goals"] or "null" in [str(x) for x in lab["allowed_goals"]]
            forbidden = set(lab["forbidden_goals"])
            lo, hi = lab["confusion_range"]
            for i in range(n):
                before = client.call_log[-1]["ts"] if client.call_log else None
                mind, goal = client.reinterpret_mind(
                    p, MindState(status="이동 중", confusion=0.5), report, labels, prior,
                    None, rng=random.Random(hash((gid, sk, i)) & 0xFFFF))
                ok = bool(client.call_log) and client.call_log[-1]["ts"] != before
                raw = client.call_log[-1]["response"] if ok else ""
                if goal is None:
                    verdict = "allowed" if allow_null else "neutral"
                elif goal in forbidden:
                    verdict = "FORBIDDEN"
                elif goal in allowed:
                    verdict = "allowed"
                else:
                    verdict = "neutral"
                conf_ok = lo <= mind.confusion <= hi
                narr_bad = bool(gid not in _DEM_IDS and _DEM_NARRATIVE.search(raw or mind.status or ""))
                rows.append(dict(gid=gid, situation=sk, rep=i, ok=ok, goal=goal,
                                 verdict=verdict, conf=mind.confusion, conf_ok=conf_ok,
                                 narr_bad=narr_bad, status=mind.status, raw=raw))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = f"{split}_{variant}_{client.model}_{ts}"
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"goldset_eval_{tag}.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")

    okr = [r for r in rows if r["ok"]]
    fails = len(rows) - len(okr)
    v = collections.Counter(r["verdict"] for r in okr)
    conf_in = sum(1 for r in okr if r["conf_ok"])
    narr = sum(1 for r in okr if r["narr_bad"])
    lines = [f"# 골드셋 평가 [{split}] — {ts}",
             f"모델 {client.model} · variant={variant} · n={n}/상황 · "
             f"유효 {len(okr)}/{len(rows)} (호출실패 {fails})", "",
             f"- goal allowed 적중: {v.get('allowed', 0)}/{len(okr)} = {v.get('allowed', 0) / max(1, len(okr)):.0%}",
             f"- goal FORBIDDEN 위반(치명): {v.get('FORBIDDEN', 0)}건",
             f"- goal 중립(등재됐으나 비권장): {v.get('neutral', 0)}건",
             f"- confusion 범위 내: {conf_in}/{len(okr)} = {conf_in / max(1, len(okr)):.0%}",
             f"- 발달 시나리오 치매서사 위반: {narr}건", "", "## 시나리오별", "",
             "| 시나리오 | 상황 | allowed | 중립 | 치명 | conf적합 |", "|---|---|---|---|---|---|"]
    for gid in ids:
        for sk in GAUGES:
            rs = [r for r in okr if r["gid"] == gid and r["situation"] == sk]
            c = collections.Counter(r["verdict"] for r in rs)
            ci = sum(1 for r in rs if r["conf_ok"])
            lines.append(f"| {gid} | {sk} | {c.get('allowed', 0)} | {c.get('neutral', 0)} "
                         f"| {c.get('FORBIDDEN', 0)} | {ci}/{len(rs)} |")
    out = RESULTS / f"goldset_eval_{tag}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:10]))
    print(f"[goldset-eval] 저장: {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--unseal", action="store_true")
    ap.add_argument("--variant", default="analyst",
                    choices=["analyst", "first_person", "first_person_rag"])
    ap.add_argument("--model", default=None, help="EXAONE_MODEL 오버라이드 (예: exaone-base)")
    a = ap.parse_args()
    main(a.split, a.n, a.unseal, a.variant, a.model)
