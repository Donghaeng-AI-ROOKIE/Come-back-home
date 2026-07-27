"""절대 임계 3개 스윕 — chatbot_eval 하네스를 굴리며 상수만 갈아끼운다.

`run_eval.py` 의 가드 스윕과 같은 원리. 재는 대상이 가드가 아니라
`retrieval.PIVOT_SIM` · `RISK_GATE` · `COHERENCE_THRESHOLD` 다.

이 셋은 **코사인 유사도 절대값**이라 임베더에 종속된다. 임베더를 바꾸면
분포가 통째로 이동해 값을 그대로 두면 가드가 조용히 무력화되므로,
교체할 때마다 여기서 재보정해야 한다.

하네스 기본 지표(질문수·중복질문)만으로는 부족해서 두 가지를 더 잰다:

  ① 정상피벗 / 헛피벗
     질문수·중복은 **슬롯 순서에 구조적으로 둔감**하다 — 슬롯은 어차피 전부
     질문되므로 순서가 바뀌어도 총량이 같다. 그래서 피벗 발동을 직전 발화의
     성격으로 쪼갠다. 정상피벗(정보성 답변 뒤)은 높을수록, 헛피벗(무정보
     답변 뒤)은 낮을수록 좋다.

  ② 라이브 융합 쿼리의 max-sim 분포
     실제 랭킹은 단일 발화가 아니라 `build_history_aware_query` 가 만든 융합
     쿼리를 쓴다. 문장을 이어붙이면 벡터가 희석돼 코퍼스 유사도보다 낮게
     나오므로, **임계는 반드시 이 분포 위에서 골라야 한다.**

⚠ 스텁 모드로 상수를 확정하지 말 것 — 스텁은 질문 문구가 고정 템플릿이라
  대화 궤적·폴백 분포가 실 Mi:dm 과 다르다. 실측에서 세 번 모두 결론이
  뒤집혔다(P1-1). 스텁은 후보를 3~4개로 좁히는 데까지만 쓴다.

사용 (backend 디렉토리에서):
  # 현재 상수만 (베이스라인 확인)
  PYTHONUTF8=1 PYTHONPATH=. python -m experiments.slot_ranking.const_sweep

  # 후보 비교 — 라벨:PIVOT/RISK/COH
  PYTHONUTF8=1 PYTHONPATH=. python -m experiments.slot_ranking.const_sweep \
      --config "PIVOT 0.45:0.45/0.30/0.15" --config "COH 0.45:0.32/0.30/0.45"

  # 실 Mi:dm 확정 (쿼터 소모 — 설정당 시나리오수 × runs 회 대화)
  PYTHONUTF8=1 PYTHONPATH=. python -m experiments.slot_ranking.const_sweep \
      --real --runs 3 --config "후보:0.45/0.30/0.45"
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from .corpus import is_noinfo


def _parse_config(spec: str, base: tuple[float, float, float]):
    """'라벨:PIVOT/RISK/COH' 파싱. 값 자리를 비우면 현재값 유지."""
    label, _, vals = spec.partition(":")
    if not vals:
        raise ValueError(f"설정 형식 오류: {spec!r} — '라벨:0.45/0.30/0.45' 처럼")
    parts = vals.split("/")
    if len(parts) != 3:
        raise ValueError(f"설정 형식 오류: {spec!r} — 값 3개(PIVOT/RISK/COH) 필요")
    out = tuple(base[i] if not p.strip() else float(p) for i, p in enumerate(parts))
    return label.strip(), out


class _Cached:
    """임베딩 캐시 — 슬롯 embed_text 는 고정인데 매 턴 재인코딩된다.

    임계값은 인코딩에 영향이 없으므로 설정 간에 캐시를 공유해도 결과가 같다.
    실측 2.6배 단축(시나리오당 45.1s → 17.2s).
    """

    def __init__(self, inner):
        self.inner, self.c, self.hit, self.miss = inner, {}, 0, 0

    def encode(self, texts):
        need = [t for t in texts if t not in self.c]
        self.hit += len(texts) - len(need)
        self.miss += len(need)
        if need:
            for t, v in zip(need, self.inner.encode(need)):
                self.c[t] = v
        return [self.c[t] for t in texts]


def main() -> int:
    ap = argparse.ArgumentParser(description="절대 임계 3개 스윕")
    ap.add_argument("--config", action="append", default=[], metavar="라벨:P/R/C",
                    help="비교할 상수 조합(반복 가능). 없으면 현재값만 돌린다")
    ap.add_argument("--real", action="store_true", help=".env 의 Mi:dm 실키 사용")
    ap.add_argument("--runs", type=int, default=1, help="설정당 반복 횟수(평균). 확정은 3+")
    ap.add_argument("--scenario", help="시나리오 id (쉼표, 기본 전부)")
    ap.add_argument("--model", help="임베더 교체 (HF 모델명/경로). 기본=settings")
    ap.add_argument("--max-turns", type=int, default=40)
    args = ap.parse_args()

    sys.path.insert(0, ".")
    from experiments.chatbot_eval.run_eval import _force_stub

    if not args.real:
        _force_stub()
    os.environ["AXIS_SCORING_ENABLED"] = "false"

    from fastapi.testclient import TestClient

    from app.llm import midm as midm_client
    from app.main import app
    from app.phase0 import interview, retrieval
    from experiments.chatbot_eval.run_eval import _aggregate_runs, _reset_guards
    from experiments.chatbot_eval.runner import run_scenario
    from experiments.chatbot_eval.scenarios import SCENARIOS
    from experiments.chatbot_eval.scorer import score

    mode = "실 Mi:dm" if not midm_client.is_stub else "스텁"
    print(f"═══ 상수 스윕 · 모드: {mode} · runs={args.runs} ═══")
    if args.real and midm_client.is_stub:
        print("⚠️  --real 이지만 Mi:dm 키가 .env 에 없어 스텁으로 돕니다.")
    if not args.real:
        print("⚠️  스텁 모드 — 후보 좁히기 전용. 상수 확정은 --real 로.")

    inner = retrieval.LocalSTEmbedder(args.model) if args.model else interview._EMB
    if args.model:
        print(f"임베더 교체: {args.model}")
    cache = _Cached(inner)
    interview._EMB = cache

    # ── 계측: 피벗 발동을 직전 발화 성격으로 쪼갠다 ────────────────────
    # rank_next_slots 는 정렬 후 슬라이스하므로 top_k 를 크게 줘도 호출자가
    # 받는 상위 목록은 동일하다(추가 임베딩 호출 없음).
    stats = {"info": 0, "piv_info": 0, "noinfo": 0, "piv_noinfo": 0}
    sims: dict[str, list[float]] = {"info": [], "noinfo": []}
    _orig_rank = retrieval.rank_next_slots

    def _instrumented(ptype, user_turns, *a, top_k=5, **kw):
        ranked, kept = _orig_rank(ptype, user_turns, *a, top_k=10_000, **kw)
        if ranked and user_turns:
            mx = max(x.similarity for x in ranked)
            bucket = "noinfo" if is_noinfo(user_turns[-1]) else "info"
            stats[bucket] += 1
            stats[f"piv_{bucket}"] += mx >= retrieval.PIVOT_SIM
            sims[bucket].append(mx)
        return ranked[:top_k], kept

    retrieval.rank_next_slots = _instrumented

    client = TestClient(app)
    if args.scenario:
        ids = [s.strip() for s in args.scenario.split(",") if s.strip()]
        unknown = [i for i in ids if i not in SCENARIOS]
        if unknown:
            print(f"알 수 없는 시나리오: {unknown} (있는 것: {list(SCENARIOS)})")
            return 2
        targets = [SCENARIOS[i] for i in ids]
    else:
        targets = list(SCENARIOS.values())

    base = (retrieval.PIVOT_SIM, retrieval.RISK_GATE, retrieval.COHERENCE_THRESHOLD)
    try:
        configs = [_parse_config(c, base) for c in args.config] or [("현재값", base)]
    except ValueError as e:
        print(e)
        return 2

    print(f"시나리오 {len(targets)}개 × 설정 {len(configs)}개 × {args.runs}회\n")
    rows = []
    for label, (piv, risk, coh) in configs:
        _reset_guards(interview, retrieval)
        retrieval.PIVOT_SIM, retrieval.RISK_GATE, retrieval.COHERENCE_THRESHOLD = piv, risk, coh
        for k in stats:
            stats[k] = 0
        sims["info"], sims["noinfo"] = [], []
        t0 = time.time()
        agg = _aggregate_runs(targets, client, run_scenario, score, args.max_turns, args.runs)
        agg["good"] = stats["piv_info"] / stats["info"] if stats["info"] else None
        agg["bad"] = stats["piv_noinfo"] / stats["noinfo"] if stats["noinfo"] else None
        agg["n_noinfo"] = stats["noinfo"]
        agg["sims"] = {k: sorted(v) for k, v in sims.items()}
        agg["sec"] = (time.time() - t0) / (len(targets) * args.runs)
        rows.append((label, piv, risk, coh, agg))
        print(f"  · {label:24} 질문{agg['questions']:.1f} 중복{agg['dups']:.1f} "
              f"정상피벗{(agg['good'] or 0):.0%} 헛피벗{(agg['bad'] or 0):.0%}")

    retrieval.PIVOT_SIM, retrieval.RISK_GATE, retrieval.COHERENCE_THRESHOLD = base
    retrieval.rank_next_slots = _orig_rank

    ref = rows[0][4]

    def d(agg, key):
        return "" if agg is ref else f"({agg[key] - ref[key]:+.1f})"

    def p(v):
        return "  —" if v is None else f"{v * 100:3.0f}%"

    print("\n" + "═" * 104)
    print(f"상수 스윕 결과 · 설정당 {args.runs}회 평균 · 시나리오 {len(targets)}개")
    print("═" * 104)
    print(f"{'설정':24} {'PIV':>5} {'RSK':>5} {'COH':>5} {'종료':>6} {'질문수':>11} "
          f"{'중복':>9} {'정상피벗':>8} {'헛피벗':>7} {'수집':>6} {'축':>5}")
    print("─" * 104)
    for label, piv, risk, coh, agg in rows:
        print(f"{label:24} {piv:>5.2f} {risk:>5.2f} {coh:>5.2f} "
              f"{agg['done']:>3.1f}/{agg['n']:<2} "
              f"{agg['questions']:>6.1f}{d(agg,'questions'):>7} "
              f"{agg['dups']:>4.1f}{d(agg,'dups'):>6} "
              f"{p(agg['good']):>8} {p(agg['bad']):>7} "
              f"{p(agg['collection']):>6} {p(agg['axis']):>5}")
    print("─" * 104)
    print(f"임베딩 캐시 적중률 {cache.hit / (cache.hit + cache.miss):.1%}  ·  "
          + " · ".join(f"{lab}={agg['sec']:.1f}s/시나리오" for lab, _, _, _, agg in rows))
    print(f"해석: 정상피벗은 높을수록, 헛피벗(n={ref['n_noinfo']})은 낮을수록 좋다.")
    print("⚠ 수집률·축 커버리지는 분모가 작아 노이즈가 크다(P1-1 실측 8pp/4pp) —")
    print("  몇 %p 차이로 판단하지 말 것. 질문수(SD≈0.6)가 신뢰할 수 있는 지표.")
    if args.runs < 3 and args.real:
        print("⚠ 실 Mi:dm × runs<3 은 노이즈 지배 — 확정 전 --runs 3+ 로 재확인.")

    # ── 라이브 융합 쿼리 분포 — 임계는 여기서 고른다 ──────────────────
    seen: dict[float, tuple[str, dict]] = {}
    for label, _, _, coh, agg in rows:
        seen.setdefault(coh, (label, agg))

    print("\n" + "═" * 104)
    print("라이브 융합 쿼리의 max-sim 분포 — PIVOT_SIM 은 이 위에서 고른다")
    print("(코퍼스 유사도보다 낮다: 과거 턴 이어붙이기로 벡터가 희석됨)")
    print("═" * 104)
    for coh in sorted(seen):
        label, agg = seen[coh]
        info, noinfo = agg["sims"]["info"], agg["sims"]["noinfo"]
        print(f"\n▶ COHERENCE_THRESHOLD = {coh:.2f}  (설정: {label})")
        for bucket, ko in (("info", "정보성 턴"), ("noinfo", "무정보 턴")):
            s = agg["sims"][bucket]
            if s:
                i = lambda q: s[min(len(s) - 1, max(0, int(round((len(s) - 1) * q / 100))))]  # noqa: E731
                print(f"  {ko}  n={len(s):<4} min={s[0]:.3f} p25={i(25):.3f} "
                      f"med={i(50):.3f} p75={i(75):.3f} max={s[-1]:.3f}")
        if info and noinfo:
            print(f"  {'임계':>6} {'정상피벗 유지':>13} {'헛피벗 잔존':>12}   손익")
            for t in [0.28, 0.30, 0.32, 0.35, 0.38, 0.40, 0.45, 0.50]:
                a = sum(1 for v in info if v >= t) / len(info)
                b = sum(1 for v in noinfo if v >= t) / len(noinfo)
                print(f"  {t:>6.2f} {a:>12.1%} {b:>11.1%}   {a-b:+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
