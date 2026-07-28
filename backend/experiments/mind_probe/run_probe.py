"""마음 재해석 과합리 실측 — README.md 의 사전 판정 기준을 코드로 집행한다.

reinterpret_mind 를 조건 6개 × n회 실호출하고, 원 JSON 을 call_log 에서 회수해
goal 고착도·혼란 반응성·장면 반응성·표집 다양성·time-shift 발현을 집계한다.

주의: reinterpret_mind 는 실패 시 조용히 폴백("혼란 심화")을 돌려준다. 폴백을
데이터로 오인하면 측정 전체가 무효라, 콜마다 call_log 증가를 확인하고 아니면
그 콜을 fallback 으로 별도 분류한다. 프리플라이트에서 엔드포인트 사망이면 중단.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.schemas.common import GeoPoint                     # noqa: E402
from app.schemas.persona import AttractionPoint, Persona, PersonaType  # noqa: E402
from app.schemas.prediction import LognormalParams, MindState, PriorParams  # noqa: E402

RESULTS_DIR = Path(__file__).parent / "results"

# ── 대상 페르소나 — seed.py 의 김순자를 그대로 복제 (seed 부작용 없이) ──
PERSONA = Persona(
    id="probe-kim-soonja",
    name="김순자",
    age=78,
    type=PersonaType.dementia,
    home=GeoPoint(lat=37.6061, lng=127.0106),
    attraction_points=[
        AttractionPoint(label="옛집(아리랑고개)", location=GeoPoint(lat=37.6015, lng=127.0088), weight=0.55),
        AttractionPoint(label="정릉시장", location=GeoPoint(lat=37.6047, lng=127.0121), weight=0.30),
    ],
    behavior_notes=["해질녘 옛집 방향으로 걷는 습관", "중기 치매 — 시간 인식 혼란(time-shift)"],
)

LABELS = [ap.label for ap in PERSONA.attraction_points]
TOP_LABEL = "옛집(아리랑고개)"

# 고정 prior — seed 가중치 미러 (재현성 우선, LLM prior 생성은 이 실험의 대상이 아님)
PRIOR = PriorParams(
    strategy_probs={"route_following": 0.35, "direction_keeping": 0.15, "random_walk": 0.10,
                    "backtracking": 0.05, "staying_put": 0.05, "landmark_seeking": 0.30},
    attraction_weights={"옛집(아리랑고개)": 0.55, "정릉시장": 0.30},
    radius_lognormal=LognormalParams(mu=0.095, sigma=1.48),
    reasoning="(프로브 고정 prior)",
)


def gauge_report(elapsed_min: int, f: str, c: str, h: str, a: str, reason: str) -> str:
    """gauges.report() 실제 포맷 재현 — 수준은 낮음/중간/높음 문자열로 직접 지정."""
    return (f"집을 나선 지 {elapsed_min}분 경과. "
            f"피로도: {f}, 혼란도: {c}, 귀소 충동: {h}, 불안: {a}. "
            f"방금 {reason} 게이지가 임계를 넘었다.")


SCENARIOS: list[dict] = [
    dict(id="S1_baseline", report=gauge_report(30, "낮음", "중간", "중간", "낮음", "귀소"),
         scene=None, confusion0=0.5),
    dict(id="S2_homing", report=gauge_report(90, "중간", "중간", "높음", "낮음", "귀소") + " 해질녘이다.",
         scene=None, confusion0=0.5),
    dict(id="S3_anxiety", report=gauge_report(60, "중간", "중간", "낮음", "높음", "불안"),
         scene=None, confusion0=0.5),
    dict(id="S4_water", report=gauge_report(60, "중간", "중간", "낮음", "높음", "불안"),
         scene="물가 25m", confusion0=0.5),
    dict(id="S5_market", report=gauge_report(90, "중간", "중간", "높음", "낮음", "귀소"),
         scene="시장 40m", confusion0=0.5),
    dict(id="S6_late_confused", report=gauge_report(180, "높음", "높음", "중간", "중간", "귀소"),
         scene=None, confusion0=0.8),
]

_TIMESHIFT_PAT = re.compile(r"옛|과거|예전|시절|착각|출퇴근|직장|젊|30년|그 시절")


def preflight(client) -> tuple[bool, str]:
    """엔드포인트 생존 + RAG 활성 여부. 죽었으면 즉시 중단용 False."""
    if client.is_stub:
        return False, "클라이언트가 스텁 모드(키/URL/모델 미설정) — 측정 불가"
    try:
        out = client.chat([{"role": "user", "content": "1+1=? 숫자만."}],
                          temperature=0.0, max_tokens=8)
        if not (out or "").strip():
            return False, "엔드포인트 응답이 비어 있음 (thinking 이슈 가능)"
    except Exception as e:  # noqa: BLE001
        return False, f"엔드포인트 호출 실패: {e!r}"

    from app.rag import get_retriever
    r = get_retriever()
    rag = "활성" if (r is not None and r.available) else "비활성(인덱스 없음/꺼짐)"
    return True, f"엔드포인트 OK · RAG {rag} · model={client.model}"


def run(n: int, dry_run: bool) -> None:
    import importlib

    from app.config import settings

    # app.llm.__init__ 이 `exaone = ExaoneClient()` 싱글턴으로 모듈명을 가리므로
    # 모듈 함수(_build_mind_input)는 importlib 로 모듈 자체를 가져온다.
    ex = importlib.import_module("app.llm.exaone")

    client = ex.ExaoneClient()  # 운영 기본 모델 (EXAONE_MODEL / .env)
    print(f"[probe] base_url={settings.exaone_base_url}  model={client.model}")

    if dry_run:
        print(f"[dry-run] 조건 {len(SCENARIOS)}개 × {n}회 = {len(SCENARIOS) * n}콜 예정. 입력 미리보기:\n")
        preview = ex._build_mind_input(PERSONA, SCENARIOS[0]["report"], LABELS, PRIOR,
                                       SCENARIOS[3]["scene"])
        print(preview)
        ok, msg = preflight(client)
        print(f"\n[preflight] {msg}" + ("" if ok else "  → 실측은 터널 연 뒤 재실행"))
        return

    ok, msg = preflight(client)
    print(f"[preflight] {msg}")
    if not ok:
        sys.exit(1)

    RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = RESULTS_DIR / f"probe_raw_{ts}.jsonl"
    rows: list[dict] = []

    with raw_path.open("w", encoding="utf-8") as fh:
        for sc in SCENARIOS:
            for i in range(n):
                current = MindState(status="이동 중", confusion=sc["confusion0"])
                # call_log 는 최근 50건에서 잘리므로(_log_call 의 del [:-50])
                # 길이 비교는 51콜째부터 오작동한다 — 마지막 항목의 ts 로 감지.
                before_ts = client.call_log[-1]["ts"] if client.call_log else None
                t0 = time.perf_counter()
                mind, goal = client.reinterpret_mind(
                    PERSONA, current, sc["report"], LABELS, PRIOR, sc["scene"])
                elapsed = (time.perf_counter() - t0) * 1000
                logged = bool(client.call_log) and client.call_log[-1]["ts"] != before_ts
                raw_json: dict | None = None
                if logged:
                    resp = client.call_log[-1]["response"]
                    try:
                        raw_json = json.loads(resp[resp.index("{"): resp.rindex("}") + 1])
                    except Exception:  # noqa: BLE001
                        raw_json = {"_parse_error": resp[:200]}
                row = dict(scenario=sc["id"], rep=i, fallback=not logged,
                           goal=goal, status=mind.status, confusion=mind.confusion,
                           raw=raw_json, elapsed_ms=round(elapsed, 1))
                rows.append(row)
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                print(f"  {sc['id']} #{i}: goal={goal} conf={mind.confusion} "
                      f"{'(FALLBACK)' if not logged else ''} {elapsed:.0f}ms")

    summarize(rows, ts)


def summarize(rows: list[dict], ts: str) -> None:
    ok_rows = [r for r in rows if not r["fallback"]]
    n_fb = len(rows) - len(ok_rows)
    lines = [f"# 마음 재해석 과합리 프로브 — {ts}", "",
             f"총 {len(rows)}콜, 폴백 {n_fb}건 (폴백은 집계 제외)", ""]

    by_sc: dict[str, list[dict]] = collections.defaultdict(list)
    for r in ok_rows:
        by_sc[r["scenario"]].append(r)

    lines += ["| 조건 | n | goal=옛집 | goal=시장 | null | conf 분포 | 고유(goal,conf) | time-shift | 고유 status |",
              "|---|---|---|---|---|---|---|---|---|"]
    for sc in SCENARIOS:
        rs = by_sc.get(sc["id"], [])
        if not rs:
            lines.append(f"| {sc['id']} | 0 | - | - | - | - | - | - | - |")
            continue
        n = len(rs)
        gold = sum(1 for r in rs if r["goal"] == TOP_LABEL)
        market = sum(1 for r in rs if r["goal"] == "정릉시장")
        null = sum(1 for r in rs if r["goal"] is None)
        confs = collections.Counter(r["confusion"] for r in rs)
        conf_str = " ".join(f"{k}:{v}" for k, v in sorted(confs.items()))
        uniq = len({(r["goal"], r["confusion"]) for r in rs})
        tshift = sum(1 for r in rs
                     if _TIMESHIFT_PAT.search((r["status"] or "") +
                                              json.dumps(r.get("raw") or {}, ensure_ascii=False)))
        ustat = len({r["status"] for r in rs})
        lines.append(f"| {sc['id']} | {n} | {gold}/{n} | {market}/{n} | {null}/{n} "
                     f"| {conf_str} | {uniq} | {tshift}/{n} | {ustat} |")

    # ── 사전 기준 자동 판정 (README 표와 1:1) ──
    total = len(ok_rows) or 1
    gold_all = sum(1 for r in ok_rows if r["goal"] == TOP_LABEL) / total
    uniq_min = min((len({(r["goal"], r["confusion"]) for r in rs})
                    for rs in by_sc.values() if len(rs) >= 5), default=0)
    s3 = collections.Counter(r["confusion"] for r in by_sc.get("S3_anxiety", []))
    s1 = collections.Counter(r["confusion"] for r in by_sc.get("S1_baseline", []))
    s4_goal = collections.Counter(r["goal"] for r in by_sc.get("S4_water", []))
    s3_goal = collections.Counter(r["goal"] for r in by_sc.get("S3_anxiety", []))
    s5_market = sum(1 for r in by_sc.get("S5_market", []) if r["goal"] == "정릉시장")
    tshift_all = sum(1 for r in ok_rows
                     if _TIMESHIFT_PAT.search((r["status"] or "") +
                                              json.dumps(r.get("raw") or {}, ensure_ascii=False)))

    lines += ["", "## 사전 기준 대조", "",
              f"- 지표1 goal 고착도: 전체 옛집 비율 {gold_all:.0%} → {'⚠ 과합리 신호(≥90%)' if gold_all >= 0.9 else '통과'}",
              f"- 지표2 혼란 반응성: S1 {dict(s1)} vs S3 {dict(s3)} → {'⚠ 무반응' if s1 == s3 and s1 else '반응 있음'}",
              f"- 지표3 장면 반응성: S3 goal {dict(s3_goal)} vs S4(물가) {dict(s4_goal)}"
              f" · S5(시장 눈앞) 시장 선택 {s5_market}/{len(by_sc.get('S5_market', []))}",
              f"- 지표4 표집 다양성: 조건당 최소 고유출력 {uniq_min} → {'⚠ 사실상 결정론(≤2) — _MindPool 전제 재검토' if uniq_min <= 2 else '분포 표집 성립'}",
              f"- 지표5 time-shift 발현: {tshift_all}/{total} → {'⚠ 발현 0 — 단서를 줘도 안 씀' if tshift_all == 0 else '발현함'}",
              "",
              "판정 규칙(README): 1·2·3 모두 과합리 쪽이면 마음 튜닝(혼란 예시 저작) 착수 근거 성립.", ""]

    md = "\n".join(lines)
    out = RESULTS_DIR / f"probe_summary_{ts}.md"
    out.write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"[probe] 저장: {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10, help="조건당 반복 (기본 10)")
    ap.add_argument("--dry-run", action="store_true", help="배관 점검만 (프리플라이트 포함, 측정 0콜)")
    args = ap.parse_args()
    run(args.n, args.dry_run)
