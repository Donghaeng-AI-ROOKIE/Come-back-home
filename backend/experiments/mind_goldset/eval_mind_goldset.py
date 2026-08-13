"""마음 골드셋 평가기 — 04_gold.jsonl 의 범위 라벨로 reinterpret_mind 를 채점한다.

마음 단독 평가: 입력 페르소나를 (추출이 아니라) 골드 라벨 + 대본 답변으로 구성해
추출 오류와 마음 오류를 분리한다. (E2E 평가는 별도 — Phase 0 통과본으로 실행)

기본은 dev(G01~G04)만 실행한다. test(G09~G14)는 봉인 — `--split test --unseal` 을
명시해야 돌고, 실행 사실이 results/test_usage.log 에 기록된다(README 봉인 규칙).

채점:
  goal:      allowed 적중률 / forbidden 위반(치명) / 중립(등재됐으나 allowed 밖)
  confusion: confusion_range 안 비율
  (expected_relation·대조쌍은 test 전용 — G09/G10 쌍 비교로 채점)
  (발달 시나리오 대비 '치매 서사 오염' 검정은 2026-08-03 치매 단독 스코프로 폐기)

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
_P = {"lat": 37.55, "lng": 127.0}
GAUGES = {
    "A_귀소": "집을 나선 지 90분 경과. 피로도: 중간, 혼란도: 중간, 귀소 충동: 높음, 불안: 낮음. 방금 귀소 게이지가 임계를 넘었다.",
    "B_불안": "집을 나선 지 60분 경과. 피로도: 중간, 혼란도: 중간, 귀소 충동: 낮음, 불안: 높음. 방금 불안 게이지가 임계를 넘었다.",
}

_BEHAVIORS = {"끌림점 접근", "귀소 시도", "은신·멈춤", "계속 배회"}  # v1.1 닫힌 어휘
# guardrail.CONFUSION_LEVELS 와 동일 — 여기 복사해 두는 이유는 채점이 운영
# 코드 경로(후처리 포함)와 독립이어야 하기 때문.
_CONF_LEVELS = {"상": 0.85, "중": 0.6, "하": 0.35}


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
    ptype = PersonaType.dementia
    return Persona(
        id=f"gold-{gid}", name="(골드)", age=78,
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
    # 실험은 어떤 variant 든 빌더를 스스로 제어한다 — 운영 기본이 v2 계약으로
    # 승격(2026-07-30)된 뒤에도 analyst/first_person* monkeypatch 가 그대로
    # 작동하도록 운영 분기(v2)를 끄고 v1 경로 위에서 패치한다.
    from app.config import settings as _settings
    _settings.mind_contract = "v1"
    if variant.startswith("first_person"):
        import first_person
        first_person.patch(ex, keep_rag=variant.endswith("_rag"),
                           contract="v2" if "_v2" in variant else "v1")
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
                # confusion 은 **모델 원출력**으로 채점한다 (2026-08-07 정정).
                # mind.confusion 을 쓰면 운영 후처리(혼란도 규칙 교체 등)가 끼어든
                # 값이 채점된다 — 실제로 미커밋 규칙 교체가 있는 작업트리에서
                # dem5 dev/test confusion 이 100% 로 채점된 사례가 있다(재채점 시
                # 75%/85%). 여기서 재는 것은 모델의 채널이지 파이프라인이 아니다.
                m_conf = re.search(r'"confusion_level"\s*:\s*"([^"]*)"', raw)
                model_conf = _CONF_LEVELS.get(m_conf.group(1).strip()) if m_conf else None
                conf_val = model_conf if model_conf is not None else mind.confusion
                conf_ok = lo <= conf_val <= hi
                # 행동 채점 (계약 v2) — raw 의 behavior 필드를 v1.1 라벨과 대조.
                # v1 출력에는 behavior 가 없으므로 "없음"으로 남는다.
                behavior, b_verdict = None, None
                if "allowed_behaviors" in lab:
                    m = re.search(r'"behavior"\s*:\s*"([^"]*)"', raw)
                    behavior = m.group(1).strip() if m else None
                    if behavior is not None:
                        if behavior not in _BEHAVIORS:
                            b_verdict = "invalid"       # 닫힌 어휘 밖 — 실패로 집계
                        elif behavior in lab["forbidden_behaviors"]:
                            b_verdict = "FORBIDDEN"
                        elif behavior in lab["allowed_behaviors"]:
                            b_verdict = "allowed"
                        else:
                            b_verdict = "neutral"
                rows.append(dict(gid=gid, situation=sk, rep=i, ok=ok, goal=goal,
                                 verdict=verdict, conf=conf_val, conf_pipeline=mind.confusion, conf_ok=conf_ok,
                                 behavior=behavior, b_verdict=b_verdict,
                                 status=mind.status, raw=raw))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = f"{split}_{variant}_{client.model}_{ts}"
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"goldset_eval_{tag}.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")

    okr = [r for r in rows if r["ok"]]
    fails = len(rows) - len(okr)
    v = collections.Counter(r["verdict"] for r in okr)
    conf_in = sum(1 for r in okr if r["conf_ok"])
    lines = [f"# 골드셋 평가 [{split}] — {ts}",
             f"모델 {client.model} · variant={variant} · n={n}/상황 · "
             f"유효 {len(okr)}/{len(rows)} (호출실패 {fails})", "",
             f"- goal allowed 적중: {v.get('allowed', 0)}/{len(okr)} = {v.get('allowed', 0) / max(1, len(okr)):.0%}",
             f"- goal FORBIDDEN 위반(치명): {v.get('FORBIDDEN', 0)}건",
             f"- goal 중립(등재됐으나 비권장): {v.get('neutral', 0)}건",
             f"- confusion 범위 내: {conf_in}/{len(okr)} = {conf_in / max(1, len(okr)):.0%}",
             ""]
    bv = collections.Counter(r["b_verdict"] for r in okr if r["b_verdict"])
    if bv:
        bt = sum(bv.values())
        lines += ["## 행동 채점 (계약 v2 — v1.1 라벨)", "",
                  f"- behavior allowed 적중: {bv.get('allowed', 0)}/{bt} = {bv.get('allowed', 0) / max(1, bt):.0%}",
                  f"- behavior FORBIDDEN 위반(치명): {bv.get('FORBIDDEN', 0)}건",
                  f"- behavior 중립: {bv.get('neutral', 0)}건 · 어휘 밖(invalid): {bv.get('invalid', 0)}건",
                  "- behavior 분포: " + ", ".join(f"{b}:{c}" for b, c in collections.Counter(
                      r["behavior"] for r in okr if r["behavior"]).most_common()), ""]
    # ── 깡통 기준선 — "이 시험이 이 점수를 떨어뜨릴 수 있는가"의 자동 증명 ──
    # 2026-08-07 실측 교훈: dem5 봉인 behavior 100% 가 실은 "무조건 끌림점 접근"
    # 깡통도 만점인 무이빨 루브릭의 산물이었다. 모델 점수는 반드시 같은 루브릭
    # 위의 상수 정책 점수와 나란히 읽어야 한다 — 깡통과 같거나 낮으면 그 지표는
    # 정보가 없다. (사람 지시 없이 임계·라벨을 바꾸지 말 것: 기준선은 표시만 한다.)
    situations = [g["situations"][sk] for gid_ in ids for g in [gold[gid_]] for sk in GAUGES]
    n_sit = len(situations)
    lines += ["## 깡통 기준선 (상수 정책이 같은 루브릭에서 받는 점수)", ""]
    model_b_rate = bv.get("allowed", 0) / max(1, sum(bv.values())) if bv else None
    for pol in sorted(_BEHAVIORS):
        al = sum(pol in s["allowed_behaviors"] for s in situations)
        fb = sum(pol in s["forbidden_behaviors"] for s in situations)
        note = ""
        if model_b_rate is not None and fb == 0 and al / n_sit >= model_b_rate:
            note = "  ← ⚠ 모델 behavior 점수가 이 깡통 이하 — 지표 무정보"
        lines.append(f"- 무조건 「{pol}」: allowed {al}/{n_sit} · 치명 {fb}건{note}")
    null_ok = sum(1 for s in situations
                  if None in s["allowed_goals"] or "null" in map(str, s["allowed_goals"]))
    goal_note = ("  ← ⚠ 모델 goal 점수가 이 깡통 이하 — 지표 무정보"
                 if v.get("allowed", 0) / max(1, len(okr)) <= null_ok / n_sit else "")
    lines.append(f"- 무조건 goal=null: allowed {null_ok}/{n_sit} · 치명 0건{goal_note}")
    mid_ok = sum(1 for s in situations
                 if s["confusion_range"][0] <= 0.6 <= s["confusion_range"][1])
    conf_note = ("  ← ⚠ 모델 confusion 점수가 이 깡통 이하 — 지표 무정보"
                 if conf_in / max(1, len(okr)) <= mid_ok / n_sit else "")
    lines.append(f"- 무조건 confusion=「중」(0.6): 범위 내 {mid_ok}/{n_sit}{conf_note}")
    lines.append("")

    lines += ["## 시나리오별", "",
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


def rescore(jsonl_path: str) -> None:
    """저장된 결과 jsonl 을 현재 골드 라벨로 재채점 — **모델 호출 0**.

    봉인 규칙은 호출을 제한하지 채점을 제한하지 않는다. 라벨(정답지)이
    바뀌었을 때 과거 실행분(raw 보존)을 새 잣대로 다시 읽는 경로다
    (2026-08-07: behavior forbidden 4건 추가 후 dem3·dem5 재채점이 첫 사용).

    goal 은 저장된 goal 값, behavior 는 raw 의 behavior 필드, confusion 은
    raw 의 confusion_level 로 채점한다 — main() 과 같은 규칙.
    """
    src = Path(jsonl_path)
    rows = [json.loads(line) for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]
    gold = load_gold()

    for r in rows:
        lab = gold[r["gid"]]["situations"][r["situation"]]
        goal = r.get("goal")
        allow_null = None in lab["allowed_goals"] or "null" in [str(x) for x in lab["allowed_goals"]]
        if goal is None:
            r["verdict"] = "allowed" if allow_null else "neutral"
        elif goal in set(lab["forbidden_goals"]):
            r["verdict"] = "FORBIDDEN"
        elif goal in set(lab["allowed_goals"]) - {None}:
            r["verdict"] = "allowed"
        else:
            r["verdict"] = "neutral"
        raw = r.get("raw") or ""
        m = re.search(r'"behavior"\s*:\s*"([^"]*)"', raw)
        behavior = (m.group(1).strip() if m else None) or r.get("behavior")
        r["behavior"] = behavior
        if behavior is None:
            r["b_verdict"] = None
        elif behavior not in _BEHAVIORS:
            r["b_verdict"] = "invalid"
        elif behavior in lab["forbidden_behaviors"]:
            r["b_verdict"] = "FORBIDDEN"
        elif behavior in lab["allowed_behaviors"]:
            r["b_verdict"] = "allowed"
        else:
            r["b_verdict"] = "neutral"
        mc = re.search(r'"confusion_level"\s*:\s*"([^"]*)"', raw)
        conf = _CONF_LEVELS.get(mc.group(1).strip()) if mc else None
        if conf is not None:
            r["conf"] = conf
        lo, hi = lab["confusion_range"]
        r["conf_ok"] = lo <= r["conf"] <= hi

    okr = [r for r in rows if r.get("ok")]
    v = collections.Counter(r["verdict"] for r in okr)
    conf_in = sum(1 for r in okr if r["conf_ok"])
    bv = collections.Counter(r["b_verdict"] for r in okr if r["b_verdict"])
    bt = sum(bv.values())
    gids = sorted({r["gid"] for r in rows})
    situations = [gold[g]["situations"][sk] for g in gids for sk in GAUGES]
    print(f"# 재채점 [{src.name}] — 골드 라벨 현재본 기준, 호출 0")
    print(f"- goal: allowed {v.get('allowed', 0)}/{len(okr)} · 치명 {v.get('FORBIDDEN', 0)} · 중립 {v.get('neutral', 0)}")
    print(f"- behavior: allowed {bv.get('allowed', 0)}/{bt} · **치명 {bv.get('FORBIDDEN', 0)}** · "
          f"중립 {bv.get('neutral', 0)} · invalid {bv.get('invalid', 0)}")
    print(f"- confusion(모델 원출력): {conf_in}/{len(okr)} = {conf_in / max(1, len(okr)):.0%}")
    for pol in sorted(_BEHAVIORS):
        al = sum(pol in s["allowed_behaviors"] for s in situations)
        fb = sum(pol in s["forbidden_behaviors"] for s in situations)
        print(f"  깡통 「{pol}」: allowed {al}/{len(situations)} · 치명 {fb}건")
    fatals = [r for r in okr if r["b_verdict"] == "FORBIDDEN"]
    for r in fatals:
        print(f"  치명 상세: {r['gid']} {r['situation']} rep{r['rep']} → {r['behavior']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--unseal", action="store_true")
    ap.add_argument("--variant", default="analyst",
                    choices=["analyst", "first_person", "first_person_rag",
                             "first_person_v2", "first_person_v2_rag"])
    ap.add_argument("--model", default=None, help="EXAONE_MODEL 오버라이드 (예: exaone-base)")
    ap.add_argument("--rescore", default=None, metavar="JSONL",
                    help="저장된 결과 jsonl 을 현재 골드 라벨로 재채점 (호출 0)")
    a = ap.parse_args()
    if a.rescore:
        rescore(a.rescore)
    else:
        main(a.split, a.n, a.unseal, a.variant, a.model)
