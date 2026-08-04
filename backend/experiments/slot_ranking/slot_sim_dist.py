"""임베더의 슬롯 검색 품질 측정 — 코퍼스 기준.

임베더를 바꾸거나 슬롯 `embed_text` 를 손볼 때 "좋아졌나"를 재는 도구.
LLM 을 안 부르므로 빠르고(수 분) 쿼터를 안 쓴다.

내는 것:
  ① ON/OFF 발화의 max-sim 분포 + 히스토그램 — 임베더별 코사인 스케일 파악
  ② argmax 적중률 — 정답 슬롯이 1등인 비율. 모델 비교의 핵심 지표
  ③ 자석 슬롯 진단 — "1등 횟수 ≫ 정답 횟수" 인 슬롯 찾기
  ④ 절대 임계 3개 후보 스윕

⚠ 여기서 나온 임계 후보를 그대로 쓰면 안 된다. 실제 랭킹은 단일 발화가 아니라
  `build_history_aware_query` 가 만든 융합 쿼리를 쓰는데, 문장을 이어붙이면
  벡터가 희석돼 max-sim 이 낮아진다. 임계 확정은 const_sweep.py 로.

사용 (backend 디렉토리에서):
  PYTHONUTF8=1 PYTHONPATH=. python -m experiments.slot_ranking.slot_sim_dist
  PYTHONUTF8=1 PYTHONPATH=. python -m experiments.slot_ranking.slot_sim_dist --model nlpai-lab/KURE-v1
"""

from __future__ import annotations

import argparse
import statistics as st

from app.phase0 import retrieval as R
from app.phase0.slots import slots_for
from app.schemas.persona import PersonaType

from .corpus import build_corpus, is_noinfo


def _pctl(sorted_vals: list[float], q: int) -> float:
    i = int(round((len(sorted_vals) - 1) * q / 100))
    return sorted_vals[min(len(sorted_vals) - 1, max(0, i))]


def _summarize(name: str, vals: list[float]) -> None:
    s = sorted(vals)
    print(f"  {name:<12} n={len(s):<4} min={s[0]:.3f} p10={_pctl(s,10):.3f} "
          f"p25={_pctl(s,25):.3f} med={st.median(s):.3f} p75={_pctl(s,75):.3f} "
          f"p90={_pctl(s,90):.3f} max={s[-1]:.3f}")


def _histogram(name: str, vals: list[float], lo=-0.10, hi=0.90, w=0.05) -> None:
    print(f"\n  [{name}] n={len(vals)}")
    b = lo
    while b < hi:
        c = sum(1 for v in vals if b <= v < b + w)
        if c:
            print(f"    {b:+.2f}~{b+w:+.2f} | {'█' * c} {c}")
        b += w


def main() -> int:
    ap = argparse.ArgumentParser(description="임베더의 슬롯 검색 품질 측정 (코퍼스 기준)")
    ap.add_argument("--model", help="HF 모델명 또는 로컬 경로. 기본=settings.embed_model")
    ap.add_argument("--persona", default="dementia", choices=["dementia"])
    args = ap.parse_args()

    from app.config import settings

    model = args.model or settings.embed_model
    emb = R.LocalSTEmbedder(args.model) if args.model else R.get_embedder()
    ptype = PersonaType(args.persona)
    slots = slots_for(ptype)
    keys = [s.key for s in slots]
    slot_embs = emb.encode([s.embed_text for s in slots])

    on, off = build_corpus(args.persona)
    print(f"### 임베더: {model}")
    print(f"### 유형 {args.persona} · 슬롯 {len(slots)} · ON {len(on)} · OFF {len(off)}\n")
    if not on:
        print("ON 코퍼스가 비었습니다 — 이 유형의 시나리오가 아직 없습니다.")
        return 1

    # ── ① 분포 + ② 적중률 + ③ 자석 진단 ──────────────────────────────
    on_max, rows = [], []
    won = {k: 0 for k in keys}
    gold_n: dict[str, int] = {}
    for gold, text in on:
        q = emb.encode([text])[0]
        sims = [R.cosine(q, se) for se in slot_embs]
        top = max(range(len(sims)), key=lambda i: sims[i])
        on_max.append(sims[top])
        won[keys[top]] += 1
        gold_n[gold] = gold_n.get(gold, 0) + 1
        rows.append((sims[top], keys[top], gold, sims[keys.index(gold)], text))

    off_max = []
    for text in off:
        q = emb.encode([text])[0]
        sims = [R.cosine(q, se) for se in slot_embs]
        off_max.append(max(sims))
        won[keys[max(range(len(sims)), key=lambda i: sims[i])]] += 1

    print("=" * 76)
    print("① max-sim 분포 — 임베더마다 코사인 스케일이 다르다")
    print("=" * 76)
    _summarize("ON  (본론)", on_max)
    _summarize("OFF (잡담)", off_max)
    _histogram("ON  max-sim", on_max)
    _histogram("OFF max-sim", off_max)

    hits = sum(1 for _, top, gold, _, _ in rows if top == gold)
    print("\n" + "=" * 76)
    print(f"② argmax 적중률 — 정답 슬롯이 1등: {hits}/{len(rows)} = {hits/len(rows):.1%}")
    print("=" * 76)
    for mx, top, gold, gsim, text in rows:
        if top != gold:
            print(f"  {mx:.3f} 1등={top:<38} 정답={gold}({gsim:.3f})")
            print(f"        < {text[:58]}")

    print("\n" + "=" * 76)
    print("③ 자석 슬롯 진단 — 1등 횟수 ≫ 정답 횟수 면 embed_text 가 너무 넓다")
    print("   (단, 1등이 전부 잡담 발화면 '자석'이 아니라 허브니스 — 아래 오답 목록과 대조할 것)")
    print("=" * 76)
    for k in sorted(keys, key=lambda k: -won[k]):
        if won[k] or gold_n.get(k):
            print(f"  {k:<40} 1등 {won[k]:>2}회 (정답 {gold_n.get(k, 0):>2}회) {'█' * won[k]}")

    # ── ④ 절대 임계 후보 스윕 ────────────────────────────────────────
    print("\n" + "=" * 76)
    print("④ 절대 임계 후보 — ⚠ 확정은 const_sweep.py(라이브 분포)에서")
    print("=" * 76)
    print(f"\n[PIVOT_SIM] 현재 {R.PIVOT_SIM} — ON 은 발동해야, OFF 는 안 해야 좋다")
    print(f"  {'임계':>6} {'ON 발동':>9} {'OFF 오발동':>11}   분리도")
    for t in [0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]:
        a = sum(1 for v in on_max if v >= t) / len(on_max)
        b = sum(1 for v in off_max if v >= t) / len(off_max)
        mark = "  ← 현재값" if abs(t - R.PIVOT_SIM) < 1e-9 else ""
        print(f"  {t:>6.2f} {a:>8.1%} {b:>10.1%}   {a-b:+.2f}{mark}")

    risk_slots = [(s, se) for s, se in zip(slots, slot_embs) if s.risk > 0]
    if risk_slots:
        rel, unrel = [], []
        for gold, text in on:
            q = emb.encode([text])[0]
            for s, se in risk_slots:
                (rel if s.key == gold else unrel).append(R.cosine(q, se))
        for text in off:
            q = emb.encode([text])[0]
            unrel.extend(R.cosine(q, se) for _, se in risk_slots)
        print(f"\n[RISK_GATE] 현재 {R.RISK_GATE} — 위험 슬롯 {len(risk_slots)}개 "
              f"(관련 턴 n={len(rel)} — 표본이 작으니 참고용)")
        print(f"  {'임계':>6} {'관련 통과':>10} {'무관 오통과':>12}")
        for t in [0.30, 0.35, 0.40, 0.45, 0.50, 0.55]:
            a = sum(1 for v in rel if v >= t) / len(rel)
            b = sum(1 for v in unrel if v >= t) / len(unrel)
            mark = "  ← 현재값" if abs(t - R.RISK_GATE) < 1e-9 else ""
            print(f"  {t:>6.2f} {a:>9.1%} {b:>11.1%}{mark}")

    # 디노이즈: 앵커↔과거턴. 본론끼리는 살리고 잡담↔본론은 잘라야 한다.
    same_topic, cross = [], []
    from experiments.chatbot_eval.scenarios import SCENARIOS
    for sc in SCENARIOS.values():
        if sc.persona_type != args.persona:
            continue
        turns = [t for t in dict.fromkeys(sc.answers.values()) if not is_noinfo(t)]
        if len(turns) < 2:
            continue
        embs = emb.encode(turns)
        for i in range(1, len(turns)):
            same_topic.extend(R.cosine(embs[i], embs[j]) for j in range(i))
    on_embs = emb.encode([t for _, t in on])
    for text in off:
        q = emb.encode([text])[0]
        cross.extend(R.cosine(q, oe) for oe in on_embs)

    print(f"\n[COHERENCE_THRESHOLD] 현재 {R.COHERENCE_THRESHOLD} — 앵커와 과거 턴의 유사도")
    _summarize("본론끼리", same_topic)
    _summarize("잡담↔본론", cross)
    print(f"  {'임계':>6} {'본론 컷(낮을수록↑)':>20} {'잡담 컷(높을수록↑)':>20}")
    for t in [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]:
        a = sum(1 for v in same_topic if v < t) / len(same_topic)
        b = sum(1 for v in cross if v < t) / len(cross)
        mark = "  ← 현재값" if abs(t - R.COHERENCE_THRESHOLD) < 1e-9 else ""
        print(f"  {t:>6.2f} {a:>19.1%} {b:>19.1%}{mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
