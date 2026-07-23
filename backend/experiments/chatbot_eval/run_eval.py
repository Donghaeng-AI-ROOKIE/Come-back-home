"""챗봇 평가 하네스 엔트리포인트.

실행 (반드시 backend 디렉토리에서 — .env 가 cwd 기준 로드):
  python -m experiments.chatbot_eval.run_eval            # 스텁 모드(기본) + 대화 전문
  python -m experiments.chatbot_eval.run_eval --scenario D1_kim
  python -m experiments.chatbot_eval.run_eval --real     # .env 의 Mi:dm 실키 사용
  python -m experiments.chatbot_eval.run_eval --quiet    # 대화 전문 생략, 점수만
  python -m experiments.chatbot_eval.run_eval --guard-off dedup --scenario D1_kim
  python -m experiments.chatbot_eval.run_eval --real --sweep --scenario PROBE_sparse  # 가드 다이어트

스텁 모드는 LLM 키를 빈값으로 덮어 결정론적으로 돈다(conftest 와 같은 원칙).
스텁에서는 추출이 비어 내용 지표(끌림점·축)가 0에 가깝다 — 배관 검증 전용이다.

**가드 스윕(--sweep)**: 베이스라인(전부 켜짐) + 가드 하나씩 끈 실행을 돌려
질문수·중복·수집·축을 비교한다. 가드를 껐을 때의 악화가 곧 그 가드의 실효성.
효율 가드(무지소진·부정충족·중복)는 실 Mi:dm 에서만 유의미(스텁은 slot_filled 로 즉시
닫혀 재질문이 안 일어남) — 스윕은 --real 로 돌린다.
"""

from __future__ import annotations

import argparse
import os
import sys


def _force_stub() -> None:
    """app.config 임포트 전에 LLM 키를 빈값으로 — 실키가 스텁 실행에 새지 않게."""
    for key in ("EXAONE_API_KEY", "EXAONE_BASE_URL", "EXAONE_MODEL",
                "MIDM_API_KEY", "MIDM_BASE_URL", "MIDM_MODEL"):
        os.environ[key] = ""


# 스윕 대상 가드 6종 (interview.GUARDS 5 + retrieval.DENOISE 1)
GUARD_NAMES = ["ignorance_exhaust", "negation_fill", "presupposition",
               "existence_first", "dedup", "topic_grounding"]


def _set_guard(interview, retrieval, name: str, on: bool) -> None:
    if name == "topic_grounding":
        retrieval.DENOISE = on
    else:
        interview.GUARDS[name] = on


def _reset_guards(interview, retrieval) -> None:
    for n in interview.GUARDS:
        interview.GUARDS[n] = True
    retrieval.DENOISE = True


def _aggregate(cards, transcripts, scenarios) -> dict:
    """설정 하나의 시나리오들을 집계 — 효율(질문·중복·폴백)과 내용(수집·축)."""
    def _mean(vals):
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None

    fallbacks = sum(sum(1 for t in tr.turns if t["a"] == sc.fallback)
                    for tr, sc in zip(transcripts, scenarios))
    return {
        "done": sum(1 for c in cards if c.done),
        "n": len(cards),
        "questions": sum(c.n_questions for c in cards),
        "dups": sum(c.duplicate_questions for c in cards),
        "fallbacks": fallbacks,
        "presump": sum(c.presumptive_q for c in cards),
        "negcond": sum(c.neg_conditional_q for c in cards),
        "collection": _mean([c.collection_recall for c in cards]),
        "axis": _mean([c.axis_coverage for c in cards]),
    }


def _run_config(targets, client, run_scenario, score, max_turns):
    cards, transcripts = [], []
    for scenario in targets:
        tr = run_scenario(scenario, client, max_turns=max_turns, verbose=False)
        transcripts.append(tr)
        cards.append(score(tr, scenario))
    return cards, transcripts


_NUM_KEYS = ["done", "questions", "dups", "fallbacks", "presump", "negcond"]


def _aggregate_runs(targets, client, run_scenario, score, max_turns, runs) -> dict:
    """설정 하나를 runs 회 돌려 평균 — Mi:dm 비결정성 제거(단일 실행은 노이즈 지배)."""
    aggs = []
    for _ in range(runs):
        cards, transcripts = _run_config(targets, client, run_scenario, score, max_turns)
        aggs.append(_aggregate(cards, transcripts, targets))
    out = {k: sum(a[k] for a in aggs) / len(aggs) for k in _NUM_KEYS}
    out["n"] = aggs[0]["n"]
    out["runs"] = runs
    for k in ("collection", "axis"):
        vals = [a[k] for a in aggs if a[k] is not None]
        out[k] = sum(vals) / len(vals) if vals else None
    return out


def _sweep(targets, client, interview, retrieval, run_scenario, score,
           max_turns, runs=1, guards=None) -> None:
    """베이스라인 + 가드 하나씩 끈 실행 비교 — '가드 다이어트'. runs 회 평균.

    guards: 스윕할 가드 부분집합(기본 전체 6종). 특정 군만 확정할 때 호출량을 줄인다.
    """
    def _pct(v):
        return "  —" if v is None else f"{v * 100:3.0f}%"

    swept = guards or GUARD_NAMES
    rows = []
    configs = [("baseline(전부켜짐)", None)] + [(f"~{n}", n) for n in swept]
    for label, off in configs:
        _reset_guards(interview, retrieval)
        if off:
            _set_guard(interview, retrieval, off, False)
        agg = _aggregate_runs(targets, client, run_scenario, score, max_turns, runs)
        rows.append((label, agg))
        print(f"  · {label:22} 완료(×{runs}) — 질문{agg['questions']:.1f} 중복{agg['dups']:.1f} "
              f"전제Q{agg['presump']:.1f} 부정조건Q{agg['negcond']:.1f}")
    _reset_guards(interview, retrieval)

    base = rows[0][1]

    def _d(agg, key, is_base):
        return "" if is_base else f"({agg[key]-base[key]:+.1f})"

    print("\n" + "═" * 96)
    print(f"가드 스윕 결과 · 설정당 {runs}회 평균 (가드 OFF 시 baseline 대비 변화 = 실효성)")
    print("═" * 96)
    print(f"{'설정':24} {'종료':>5} {'질문수':>10} {'중복':>9} {'폴백':>5} "
          f"{'전제Q':>9} {'부정조건Q':>11} {'수집':>5} {'축':>5}")
    print("─" * 96)
    for label, agg in rows:
        b = label.startswith("baseline")
        print(f"{label:24} {agg['done']:.1f}/{agg['n']:<2} "
              f"{agg['questions']:>5.1f}{_d(agg,'questions',b):>8} "
              f"{agg['dups']:>3.1f}{_d(agg,'dups',b):>7} "
              f"{agg['fallbacks']:>4.1f} "
              f"{agg['presump']:>3.1f}{_d(agg,'presump',b):>6} "
              f"{agg['negcond']:>4.1f}{_d(agg,'negcond',b):>6} "
              f"{_pct(agg['collection']):>5} {_pct(agg['axis']):>5}")
    print("─" * 96)
    print("해석: OFF 시 질문수·중복·전제Q·부정조건Q↑ 또는 종료↓·수집/축↓ = 그 가드가 실효.")
    print("      전제Q=presupposition 대상, 부정조건Q=existence_first 대상, 중복=dedup 대상.")
    if runs == 1:
        print("⚠ runs=1 은 Mi:dm 노이즈에 취약 — 작은 변화는 --runs 3+ 로 재확인 필요.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 0 챗봇 성능 평가 하네스")
    parser.add_argument("--scenario", help="시나리오 id (쉼표로 여러 개, 기본: 전부)")
    parser.add_argument("--real", action="store_true", help=".env 의 Mi:dm 실키 사용")
    parser.add_argument("--quiet", action="store_true", help="대화 전문 생략, 점수만")
    parser.add_argument("--max-turns", type=int, default=40)
    parser.add_argument("--guard-off", action="append", default=[], metavar="NAME",
                        help=f"가드 끄기(반복 가능). 이름: {', '.join(GUARD_NAMES)}")
    parser.add_argument("--sweep", action="store_true",
                        help="가드 다이어트 — 베이스라인 + 가드 하나씩 끈 실행 비교")
    parser.add_argument("--runs", type=int, default=1,
                        help="스윕 설정당 반복 횟수(평균) — Mi:dm 노이즈 제거. 권장 3+")
    parser.add_argument("--guards", help="스윕할 가드만 쉼표로 지정(기본 전체 6종)")
    args = parser.parse_args()

    sweep_guards = None
    if args.guards:
        sweep_guards = [g.strip() for g in args.guards.split(",") if g.strip()]
        bad = [g for g in sweep_guards if g not in GUARD_NAMES]
        if bad:
            print(f"알 수 없는 가드: {bad} (있는 것: {GUARD_NAMES})")
            return 2

    for g in args.guard_off:
        if g not in GUARD_NAMES:
            print(f"알 수 없는 가드: {g} (있는 것: {GUARD_NAMES})")
            return 2

    if not args.real:
        _force_stub()

    # 이 하네스는 엘리시테이션(끌림점·evidence·축 근거 수집)을 재는 것이지 축 점수
    # 채점이 아니다. 축 채점(EXAONE 다회 호출)은 axis_goldset 소관 — 여기선 꺼서
    # EXAONE 쿼터를 아끼고 실행을 결정론적으로 둔다. (app.config 임포트 전에 설정)
    os.environ["AXIS_SCORING_ENABLED"] = "false"

    # app 임포트는 키 확정 후에
    from fastapi.testclient import TestClient
    from app.main import app
    from app.llm import midm as midm_client
    from app.phase0 import interview, retrieval

    from .scenarios import SCENARIOS
    from .runner import run_scenario
    from .scorer import score, format_card

    mode = "실 Mi:dm" if not midm_client.is_stub else "스텁"
    print(f"═══ 챗봇 평가 하네스 · 모드: {mode} ═══")
    if args.real and midm_client.is_stub:
        print("⚠️  --real 이지만 Mi:dm 키가 .env 에 없어 스텁으로 돕니다.")

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

    # 가드 스윕 모드 — 별도 경로
    if args.sweep:
        n_cfg = len(sweep_guards or GUARD_NAMES) + 1
        print(f"시나리오 {len(targets)}개 × {n_cfg}개 설정 × {args.runs}회 스윕 시작…")
        _sweep(targets, client, interview, retrieval, run_scenario, score,
               args.max_turns, runs=args.runs, guards=sweep_guards)
        return 0

    # 단발 실행 — --guard-off 로 지정된 가드만 끈다
    _reset_guards(interview, retrieval)
    for g in args.guard_off:
        _set_guard(interview, retrieval, g, False)
    if args.guard_off:
        print(f"⚙ 가드 끔: {args.guard_off}")

    cards = []
    for scenario in targets:
        print("\n" + "─" * 72)
        print(f"▶ {scenario.id} — {scenario.title}  (유형: {scenario.persona_type})")
        print("─" * 72)
        tr = run_scenario(scenario, client, max_turns=args.max_turns, verbose=not args.quiet)
        if tr.stopped_reason and tr.stopped_reason != "done":
            print(f"\n  ⓘ 종료 사유: {tr.stopped_reason}")
        sc = score(tr, scenario)
        cards.append(sc)
        print("\n" + format_card(sc))

    print("\n" + "═" * 72)
    print(f"완료 — 시나리오 {len(cards)}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
