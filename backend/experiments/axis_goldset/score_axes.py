r"""축 점수 골드셋 — EXAONE 채점 실험 스크립트 (Phase A ③).

같은 폴더의 md 두 개가 단일 소스다:
  01_점수기준표_초안.md  → 기준표(0.1~0.9 행동 앵커)·축 방향 (P1 선택지로 변환)
  02_시나리오_대화.md    → 시나리오 8개 (보호자 답변의 `→ axis_field` 태그로 B안 조립)

실험 조건 (README '잊으면 안 되는 요구사항' 반영):
  입력   A = 대화 통짜(챗봇 질문 포함, 태그 제거) / B = 축 단위 근거 발화만
  프롬프트 P1 = 기준표 A~E 분류 + quote 강제 + F(판정 불가) + temp 0
              — 숫자는 프롬프트에 노출하지 않고 코드가 A~E → 0.1~0.9 매핑
          P2 = (비교용 원안) 같은 기준표 + few-shot + 숫자 직접 출력, quote 없음

실행 (반드시 backend 디렉토리에서 — .env 가 cwd 기준으로 로드됨):
  python experiments\axis_goldset\score_axes.py                 # 드라이런: 계획·샘플 프롬프트만 출력
  python experiments\axis_goldset\score_axes.py --go            # 실호출 (기본: D1,P1 × B-P1 × 3회)
  옵션: --scenarios D1,P1,D2 --conditions B-P1,A-P1 --runs 3

결과: results/results_<시각>.jsonl (호출 1건 = 1줄) + 콘솔 요약.
⚠️ 실호출 전 총 호출 수를 출력한다 — 쿼터 확인 후 --go 로만 실행.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# Windows 콘솔(cp949)에서 프롬프트 속 특수문자 출력이 깨지지 않도록
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
sys.path.insert(0, str(BACKEND))

# P1 프롬프트·기준표 파싱·응답 파서는 운영 모듈(app.phase0.axis_scoring)을 그대로
# 사용 — 실험과 프로덕션이 갈라지지 않게 하고, 실험이 곧 운영 코드 검증이 된다.
from app.phase0 import axis_scoring  # noqa: E402

RUBRIC_MD = BACKEND / "app" / "phase0" / "axis_rubric.md"   # 기준표 단일 소스
SCENARIO_MD = HERE / "02_시나리오_대화.md"
RESULTS_DIR = HERE / "results"

COMMON_AXES = [
    "mobility_transport_capacity",
    "hazard_awareness_vulnerability",
    "communication_approach_vulnerability",
]
DEMENTIA_AXES = COMMON_AXES + [
    "route_environment_familiarity",
    "autobiographical_destination_pull",
    "wayfinding_error_recovery_deficit",
    "distress_induced_movement_reactivity",
]
DD_AXES = COMMON_AXES + [
    "preferred_target_seeking",
    "aversive_context_escape",
    "transition_routine_disruption",
    "elopement_pattern_consistency",
]


# ── md 파싱: 시나리오 ───────────────────────────────────────────────

def load_scenarios() -> dict[str, dict]:
    """02_시나리오_대화.md → {id: {title, info, axes, turns[{q, a, tags}]}}."""
    text = SCENARIO_MD.read_text(encoding="utf-8")
    scenarios: dict[str, dict] = {}
    cur: dict | None = None
    pending_q: str | None = None

    for line in text.splitlines():
        m = re.match(r"^#\s+([DP]\d)\.\s+(.+)$", line)
        if m:
            sid, title = m.group(1), m.group(2)
            is_dem = "치매" in title
            info = re.search(r"\(([^)]*)\)", title)
            cur = {
                "title": title,
                "info": info.group(1) if info else "",
                "axes": DEMENTIA_AXES if is_dem else DD_AXES,
                "turns": [],
            }
            scenarios[sid] = cur
            pending_q = None
            continue
        if cur is None:
            continue
        if line.startswith("챗봇:"):
            pending_q = line[len("챗봇:"):].strip()
        elif line.startswith("보호자:"):
            body = line[len("보호자:"):].strip()
            if "→" in body:
                utter, _, tagpart = body.rpartition("→")
                tags = re.findall(r"[a-z_]{3,}", tagpart)
            else:
                utter, tags = body, []
            cur["turns"].append({"q": pending_q or "", "a": utter.strip(), "tags": tags})
            pending_q = None

    for sid, s in scenarios.items():
        if not s["turns"]:
            raise ValueError(f"시나리오 파싱 실패: {sid} 턴 없음")
    return scenarios


# ── 입력 조립 (A안/B안) ─────────────────────────────────────────────

def build_input_a(scn: dict) -> str:
    """A안 — 챗봇 질문 포함 대화 통짜 (태그 제거)."""
    lines = []
    for t in scn["turns"]:
        if t["q"]:
            lines.append(f"챗봇: {t['q']}")
        lines.append(f"보호자: {t['a']}")
    return "\n".join(lines)


def build_input_b(scn: dict, axis: str) -> str:
    """B안 — 해당 축으로 태그된 보호자 원발화만."""
    quotes = [t["a"] for t in scn["turns"] if axis in t["tags"]]
    if not quotes:
        return "(이 축과 관련해 수집된 보호자 발화 없음)"
    return "\n".join(f"- {q}" for q in quotes)


# ── 프롬프트 ────────────────────────────────────────────────────────

# P1(기준표 분류)은 axis_scoring.build_p1_messages 사용. P2 는 실험 전용 비교군.
P2_SYSTEM = """\
너는 실종 위험 프로파일 채점자다. 보호자 상담 내용에서 지정된 '평가 축' 하나만 보고, \
기준표를 참고해 0.1, 0.3, 0.5, 0.7, 0.9 다섯 값 중 하나로 점수를 매긴다.

규칙:
- JSON 객체 하나만 출력한다. JSON 밖에 어떤 문장도 쓰지 않는다.
- score: 0.1 / 0.3 / 0.5 / 0.7 / 0.9 중 하나.
- reason: 판단 근거 1~2문장 (한국어)."""

# P2 few-shot — 골드셋 밖 케이스 (평가 오염 방지: 시나리오 8명과 무관한 가상 사례)
P2_FEWSHOT_USER = """\
[대상자] 남, 68, 치매
[평가 축] 이동·교통 능력
[기준표]
0.1 보조기구·부축 없이는 단독 보행이 어렵고 집 주변을 벗어나기 힘듦
0.3 집 주변 짧은 거리는 혼자 걷지만 오래 걷지 못하고, 대중교통은 혼자 이용하지 못함
0.5 30분 이상 쉬지 않고 걸을 수 있고 동네 범위를 혼자 다니지만, 대중교통은 혼자 이용하지 못함
0.7 장시간·장거리 보행이 가능하거나, 익숙한 노선의 버스·지하철을 혼자 탄 경험이 있음
0.9 보행 제한이 거의 없고 대중교통(또는 차량)을 혼자 자유롭게 이용함
[보호자 상담 내용]
- 하루에 두 시간씩 등산을 다니시고, 시외버스를 혼자 갈아타고 형님 댁에도 다녀오세요."""

P2_FEWSHOT_ASSISTANT = """\
{"score": 0.9, "reason": "장시간 보행에 제한이 없고 시외버스 환승까지 혼자 가능해 최상위 이동 능력에 해당한다."}"""

P2_USER_TMPL = """\
[대상자] {info}
[평가 축] {label}
[기준표]
0.1 {a01}
0.3 {a03}
0.5 {a05}
0.7 {a07}
0.9 {a09}
[보호자 상담 내용]
{input_text}

출력 형식: {{"score": 숫자, "reason": "..."}}"""


def build_messages(prompt: str, rubric: dict, direction: str, info: str, input_text: str) -> list[dict]:
    if prompt == "P1":
        return axis_scoring.build_p1_messages(rubric, direction, info, input_text)
    a = rubric["anchors"]
    return [
        {"role": "system", "content": P2_SYSTEM},
        {"role": "user", "content": P2_FEWSHOT_USER},
        {"role": "assistant", "content": P2_FEWSHOT_ASSISTANT},
        {"role": "user", "content": P2_USER_TMPL.format(
            info=info, label=rubric["label"], input_text=input_text,
            a01=a["0.1"], a03=a["0.3"], a05=a["0.5"], a07=a["0.7"], a09=a["0.9"])},
    ]


# ── 응답 파싱·검증 — P1 은 운영 파서(axis_scoring.parse_p1) 그대로 ────

def parse_response(prompt: str, raw: str, input_text: str) -> dict:
    """P1 → 운영 파서 / P2(실험 전용) → 숫자 5단계 검사."""
    if prompt == "P1":
        return axis_scoring.parse_p1(raw, input_text)
    out: dict = {"choice": None, "score": None, "quote": None,
                 "quote_verified": None, "reason": None, "parse_error": None,
                 "format_violation": False}
    data, strict = axis_scoring._extract_json(raw)
    out["format_violation"] = not strict
    if data is None:
        out["parse_error"] = "JSON 파싱 실패 (복구 불가)"
        return out
    out["reason"] = data.get("reason")
    try:
        score = float(data.get("score"))
    except (TypeError, ValueError):
        out["parse_error"] = f"score 형식 위반: {data.get('score')!r}"
        return out
    out["score"] = score
    if round(score, 1) not in (0.1, 0.3, 0.5, 0.7, 0.9):
        out["parse_error"] = f"5단계 밖 점수: {score}"
    return out


# ── 실행 ────────────────────────────────────────────────────────────

def plan_jobs(scenarios: dict, sids: list[str], conditions: list[str], runs: int) -> list[dict]:
    jobs = []
    for sid in sids:
        for axis in scenarios[sid]["axes"]:
            for cond in conditions:
                for run in range(1, runs + 1):
                    jobs.append({"scenario": sid, "axis": axis, "condition": cond, "run": run})
    return jobs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scenarios", default="D1,P1", help="쉼표 구분 (기본: 파일럿 D1,P1)")
    ap.add_argument("--conditions", default="B-P1", help="입력-프롬프트 조합, 예: B-P1,A-P1,B-P2,A-P2")
    ap.add_argument("--runs", type=int, default=3, help="재현성 반복 횟수 (기본 3)")
    ap.add_argument("--go", action="store_true", help="실호출 실행 (없으면 드라이런)")
    args = ap.parse_args()

    rubrics, directions = axis_scoring.load_rubrics(RUBRIC_MD)
    scenarios = load_scenarios()

    sids = [s.strip() for s in args.scenarios.split(",") if s.strip()]
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    for sid in sids:
        if sid not in scenarios:
            raise SystemExit(f"시나리오 없음: {sid} (있는 것: {', '.join(scenarios)})")
    for cond in conditions:
        inp, _, prm = cond.partition("-")
        if inp not in ("A", "B") or prm not in ("P1", "P2"):
            raise SystemExit(f"조건 형식 오류: {cond} (예: B-P1)")

    jobs = plan_jobs(scenarios, sids, conditions, args.runs)
    print(f"파싱 확인: 기준표 {len(rubrics)}축 / 방향 {len(directions)}축 / 시나리오 {len(scenarios)}개")
    print(f"실행 계획: 시나리오 {sids} × 축 7 × 조건 {conditions} × 반복 {args.runs}회")
    print(f"→ 총 EXAONE 호출 수: {len(jobs)}")

    if not args.go:
        sid, axis, cond = jobs[0]["scenario"], jobs[0]["axis"], jobs[0]["condition"]
        inp, _, prm = cond.partition("-")
        scn = scenarios[sid]
        input_text = build_input_a(scn) if inp == "A" else build_input_b(scn, axis)
        msgs = build_messages(prm, rubrics[axis], directions.get(axis, ""), scn["info"], input_text)
        print("\n[드라이런] 첫 작업 프롬프트 샘플 ↓ (실호출은 --go)")
        for m in msgs:
            print(f"\n--- {m['role']} ---\n{m['content']}")
        return

    from app.llm.exaone import ExaoneClient  # .env 로드는 backend cwd 기준

    client = ExaoneClient()
    if client.is_stub:
        raise SystemExit("EXAONE 스텁 모드 — .env 의 EXAONE_BASE_URL/MODEL/API_KEY 를 확인하세요.")

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / f"results_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    records: list[dict] = []

    with out_path.open("a", encoding="utf-8") as f:
        for i, job in enumerate(jobs, 1):
            sid, axis, cond = job["scenario"], job["axis"], job["condition"]
            inp, _, prm = cond.partition("-")
            scn = scenarios[sid]
            input_text = build_input_a(scn) if inp == "A" else build_input_b(scn, axis)
            msgs = build_messages(prm, rubrics[axis], directions.get(axis, ""), scn["info"], input_text)
            rec = dict(job)
            t0 = time.time()
            try:
                raw = client.chat(msgs, temperature=0.0, max_tokens=400, enable_thinking=False)
                rec["raw"] = raw
                rec.update(parse_response(prm, raw, input_text))
            except Exception as e:  # noqa: BLE001 — 한 호출 실패가 실험을 멈추면 안 됨
                rec["error"] = f"{type(e).__name__}: {e}"
            rec["elapsed_s"] = round(time.time() - t0, 1)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            records.append(rec)
            print(f"[{i}/{len(jobs)}] {sid} {axis} {cond} run{job['run']} → "
                  f"{rec.get('choice') or rec.get('score')} "
                  f"{'(quote 미검증!)' if rec.get('quote_verified') is False else ''}"
                  f"{rec.get('error', '')}")

    # ── 요약 ──
    print(f"\n결과 저장: {out_path}")
    print(f"\n{'시나리오':<6} {'축':<38} {'조건':<6} 반복별 판정")
    keys = sorted({(r["scenario"], r["axis"], r["condition"]) for r in records},
                  key=lambda k: (k[0], k[2], k[1]))
    for sid, axis, cond in keys:
        vals = [r.get("choice") or r.get("score") or "ERR"
                for r in records
                if (r["scenario"], r["axis"], r["condition"]) == (sid, axis, cond)]
        stable = "일치" if len(set(map(str, vals))) == 1 else "★불일치"
        print(f"{sid:<6} {axis:<38} {cond:<6} {vals}  {stable}")
    n_quote = [r for r in records if r.get("quote_verified") is not None]
    if n_quote:
        ok = sum(1 for r in n_quote if r["quote_verified"])
        print(f"\nquote 실존 검증: {ok}/{len(n_quote)} 통과")
    n_err = sum(1 for r in records if r.get("error") or r.get("parse_error"))
    n_fmt = sum(1 for r in records if r.get("format_violation"))
    print(f"호출·파싱 오류: {n_err}/{len(records)} / JSON 형식 위반(복구 포함): {n_fmt}/{len(records)}")


if __name__ == "__main__":
    main()
