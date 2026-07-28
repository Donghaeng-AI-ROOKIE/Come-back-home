"""마음 재해석 페르소나 그리드 — 실사용 분포 기반 정합성 검증.

run_probe.py(단일 페르소나 통제실험)의 한계 보완: 단일 페르소나 결론은 일반화
불가("옛집 100%"는 편중 페르소나에선 정답일 수 있음). 실사용에서 변하는 축 —
끌림점 균형도·유형(치매/발달)·정보 풍부도·특성 대조쌍 — 을 그리드로 돌린다.

검증 질문 (사전 등록):
  Q1 argmax 붕괴: 끌림점 가중치가 균형(0.35/0.35)이어도 한쪽 100% 고착이면 과합리.
     기대(분포 표집이 살아있다면): 두 후보로 갈라짐.
  Q2 유형 오염: 발달장애 페르소나 응답에 치매 서사(time-shift·옛집·과거 착각)가
     나오면 심각 — 학습·프롬프트의 치매 편향이 유형 경계를 넘은 것.
  Q3 빈약 절제: 끌림점 0·노트 최소(콜드스타트급) 페르소나에서 없는 장소·사실을
     지어내면 환각. goal null + 보수적 서사가 정답.
  Q4 대조쌍 감도: 자전적 목적지 강/약 한 끗 차이가 goal 분포 차이로 드러나야 개인화.

실행: cd backend && .venv/bin/python experiments/mind_probe/run_persona_grid.py [--n 5]
"""
from __future__ import annotations

import argparse
import collections
import importlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.schemas.common import GeoPoint  # noqa: E402
from app.schemas.persona import AttractionPoint, Persona, PersonaType  # noqa: E402
from app.schemas.prediction import LognormalParams, MindState, PriorParams  # noqa: E402

RESULTS_DIR = Path(__file__).parent / "results"
_P = {"lat": 37.6061, "lng": 127.0106}


def ap(label: str, weight: float) -> AttractionPoint:
    return AttractionPoint(label=label, location=GeoPoint(**_P), weight=weight)


def mk(pid: str, ptype: PersonaType, age: int, points: list[AttractionPoint],
       notes: list[str]) -> Persona:
    return Persona(id=pid, name="(그리드)", age=age, type=ptype,
                   home=GeoPoint(**_P), attraction_points=points, behavior_notes=notes)


# ── 페르소나 뱅크 — 실사용 변산 축을 하나씩 대표 (axis_goldset 10_시나리오 프로파일 참조) ──
BANK: list[dict] = [
    dict(key="dem_biased", q="기준(편중)",
         p=mk("g-dem-biased", PersonaType.dementia, 78,
              [ap("옛집(아리랑고개)", 0.55), ap("정릉시장", 0.30)],
              ["해질녘 옛집 방향으로 걷는 습관", "중기 치매 — 시간 인식 혼란(time-shift)"])),
    dict(key="dem_balanced", q="Q1 균형",
         p=mk("g-dem-bal", PersonaType.dementia, 75,
              [ap("복지관", 0.35), ap("딸네 집", 0.35)],
              ["복지관과 딸네 집을 비슷하게 자주 감", "초기 치매, 특별한 편향 없음"])),
    dict(key="dem_poor", q="Q3 빈약",
         p=mk("g-dem-poor", PersonaType.dementia, 81, [],
              ["치매 진단 3년차 — 상세 정보 미등록"])),
    dict(key="dem_autobio_hi", q="Q4 대조(강)",
         p=mk("g-dem-hi", PersonaType.dementia, 76,
              [ap("고향 방앗간 터", 0.5), ap("경로당", 0.3)],
              ["과거 실종 때 고향 방앗간 터에서 발견됨", "젊을 적 얘기를 반복함"])),
    dict(key="dem_autobio_lo", q="Q4 대조(약)",
         p=mk("g-dem-lo", PersonaType.dementia, 76,
              [ap("고향 방앗간 터", 0.5), ap("경로당", 0.3)],
              ["고향 얘기는 지나가듯 한 번 언급", "주로 경로당에서 소일"])),
    dict(key="dd_fixation", q="Q2 발달·고착",
         p=mk("g-dd-fix", PersonaType.intellectual_disability, 21,
              [ap("지하철 2호선 성수역", 0.5), ap("동네 PC방", 0.3)],
              ["지하철 노선도에 강한 집착 — 역만 보이면 들어가려 함",
               "낯선 사람이 말 걸면 그 자리에서 굳음"])),
    dict(key="dd_sparse", q="Q2+Q3 발달·빈약",
         p=mk("g-dd-sparse", PersonaType.intellectual_disability, 19, [],
              ["중등도 지적장애 — 보호자가 이동 습관을 잘 모름"])),
]

GAUGES = {
    "귀소": "집을 나선 지 90분 경과. 피로도: 중간, 혼란도: 중간, 귀소 충동: 높음, 불안: 낮음. 방금 귀소 게이지가 임계를 넘었다.",
    "불안": "집을 나선 지 60분 경과. 피로도: 중간, 혼란도: 중간, 귀소 충동: 낮음, 불안: 높음. 방금 불안 게이지가 임계를 넘었다.",
}

_DEM_NARRATIVE = re.compile(r"치매|time.?shift|옛집|과거로 착각|그 시절")
_STRATEGY = {"route_following": 0.3, "direction_keeping": 0.15, "random_walk": 0.15,
             "backtracking": 0.1, "staying_put": 0.1, "landmark_seeking": 0.2}


def prior_for(p: Persona) -> PriorParams:
    total = sum(a.weight for a in p.attraction_points) or 1.0
    return PriorParams(
        strategy_probs=dict(_STRATEGY),
        attraction_weights={a.label: a.weight / total for a in p.attraction_points},
        radius_lognormal=LognormalParams(mu=0.095, sigma=1.48),
        reasoning="(그리드 고정 prior)")


def main(n: int) -> None:
    ex = importlib.import_module("app.llm.exaone")
    client = ex.ExaoneClient()
    print(f"[grid] model={client.model}  페르소나 {len(BANK)} × 게이지 {len(GAUGES)} × {n}회 "
          f"= {len(BANK) * len(GAUGES) * n}콜")

    rows: list[dict] = []
    for item in BANK:
        p: Persona = item["p"]
        labels = [a.label for a in p.attraction_points]
        prior = prior_for(p)
        for gname, greport in GAUGES.items():
            for i in range(n):
                before = client.call_log[-1]["ts"] if client.call_log else None
                mind, goal = client.reinterpret_mind(
                    p, MindState(status="이동 중", confusion=0.5), greport, labels, prior, None)
                ok = bool(client.call_log) and client.call_log[-1]["ts"] != before
                raw = client.call_log[-1]["response"] if ok else ""
                rows.append(dict(key=item["key"], q=item["q"], gauge=gname, rep=i,
                                 ok=ok, goal=goal, conf=mind.confusion,
                                 status=mind.status, raw=raw))
                print(f"  {item['key']}/{gname} #{i}: goal={goal} conf={mind.confusion}"
                      f"{'' if ok else ' (실패)'}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / f"persona_grid_raw_{ts}.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")

    # ── 집계 ──
    lines = [f"# 페르소나 그리드 — {ts}", f"모델 {client.model} · n={n}/조건 · RAG 비활성", "",
             "| 페르소나 | 질문 | goal 분포 | conf 분포 | 고유 status | 치매서사 |",
             "|---|---|---|---|---|---|"]
    by = collections.defaultdict(list)
    for r in rows:
        if r["ok"]:
            by[r["key"]].append(r)
    for item in BANK:
        rs = by.get(item["key"], [])
        if not rs:
            lines.append(f"| {item['key']} | {item['q']} | (전건 실패) | | | |")
            continue
        goals = collections.Counter(str(r["goal"]) for r in rs)
        confs = collections.Counter(r["conf"] for r in rs)
        stats = len({r["status"] for r in rs})
        dem = sum(1 for r in rs if _DEM_NARRATIVE.search(r["raw"] or r["status"] or ""))
        gs = " ".join(f"{k}:{v}" for k, v in goals.most_common())
        cs = " ".join(f"{k}:{v}" for k, v in sorted(confs.items()))
        lines.append(f"| {item['key']} | {item['q']} | {gs} | {cs} | {stats} | {dem}/{len(rs)} |")

    bal = by.get("dem_balanced", [])
    bal_goals = collections.Counter(str(r["goal"]) for r in bal)
    hi = collections.Counter(str(r["goal"]) for r in by.get("dem_autobio_hi", []))
    lo = collections.Counter(str(r["goal"]) for r in by.get("dem_autobio_lo", []))
    dd_dem = sum(1 for k in ("dd_fixation", "dd_sparse")
                 for r in by.get(k, []) if _DEM_NARRATIVE.search(r["raw"] or ""))
    poor_halluc = [r["goal"] for r in by.get("dem_poor", []) + by.get("dd_sparse", [])
                   if r["goal"] is not None]
    lines += ["", "## 사전 질문 판정", "",
              f"- Q1 argmax 붕괴: 균형 페르소나 goal 분포 = {dict(bal_goals)} — "
              f"{'⚠ 한쪽 90%+ 고착' if bal_goals and bal_goals.most_common(1)[0][1] >= 0.9 * max(1, len(bal)) else '분산됨(통과)'}",
              f"- Q2 유형 오염: 발달 페르소나 응답 중 치매서사 {dd_dem}건 — "
              f"{'⚠ 오염' if dd_dem else '없음(통과)'}",
              f"- Q3 빈약 절제: 정보 빈약 페르소나의 비-null goal {len(poor_halluc)}건"
              f"{' (후보 자체가 없으므로 0이어야 정상)' if not poor_halluc else ' ⚠ 내용 검수 필요'}",
              f"- Q4 대조쌍 감도: 자전강 {dict(hi)} vs 자전약 {dict(lo)} — 분포가 다르면 개인화 감도 있음", ""]
    out = RESULTS_DIR / f"persona_grid_summary_{ts}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"[grid] 저장: {out}")


if __name__ == "__main__":
    apr = argparse.ArgumentParser()
    apr.add_argument("--n", type=int, default=5)
    main(apr.parse_args().n)
