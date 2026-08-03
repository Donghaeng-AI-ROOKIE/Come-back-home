r"""축 골드셋 v1 — 라벨러 합의 정답표 vs EXAONE 채점 비교.

파이프라인:
  1) 시나리오(10_시나리오_확장.md) → 페르소나별·축별 근거 발화(B안 입력)
  2) 라벨러 답표(11_정답표_v1.md[Claude] + 있으면 12[GPT]·13[Gemini]) → 셀별 합의 정답
     - 라벨러 ≥2/3 합의 = 정답 채택, 갈리면 DISPUTE(지표에서 제외·따로 집계)
  3) EXAONE 채점 — 운영 경로(axis_scoring.build_p1_messages/parse_p1) 그대로, 축당 runs회 다수결
  4) 축별 지표: n·정확일치·인접일치(±1)·MAE·이차가중 kappa·Spearman, F는 따로
  5) 대조쌍(DAL/DAH·PAL/PAH): 변별(varied 축 방향) + 분리(비-varied 축 Δ)

실행 (backend 디렉토리에서 — .env 가 cwd 기준 로드):
  python experiments\axis_goldset\eval_axis_goldset.py            # 드라이런: 합의 정답표만 점검
  python experiments\axis_goldset\eval_axis_goldset.py --go       # EXAONE 실호출 + 지표
  옵션: --runs 3  --labels 11_정답표_v1.md,12_정답표_GPT.md,13_정답표_Gemini.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
sys.path.insert(0, str(BACKEND))

from app.phase0 import axis_scoring  # noqa: E402

SCENARIO_MD = HERE / "10_시나리오_확장.md"
RESULTS_DIR = HERE / "results"
ORD = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5}  # F 제외 (순서형 밖)
TYPE_KO = {"dementia": "치매", "치매": "치매"}
CONTRAST = [("DAL", "DAH", "autobiographical_destination_pull")]


# ── 파싱 ────────────────────────────────────────────────────────────

def load_scenarios() -> dict[str, dict]:
    """10_시나리오_확장.md → {id: {type, age, axis_input{axis: text}}}."""
    out: dict[str, dict] = {}
    cur = None
    text = SCENARIO_MD.read_text(encoding="utf-8")
    for line in text.splitlines():
        h = re.match(r"^#\s+([A-Z0-9]+)\.\s+(치매)\s*\((\d+)\s*세", line)
        if h:
            cur = {"type": "dementia", "age": int(h.group(3)), "axis_input": {}}
            out[h.group(1)] = cur
            continue
        if cur is None or not line.startswith("보호자:"):
            continue
        body = line[len("보호자:"):].strip()
        if "→" not in body:
            continue
        utter, _, tagpart = body.rpartition("→")
        utter = utter.strip()
        for axis in re.findall(r"[a-z_]{3,}", tagpart):
            cur["axis_input"].setdefault(axis, []).append(utter)
    if not out:
        raise SystemExit("시나리오 파싱 실패 — 10_시나리오_확장.md 확인")
    return out


def load_labels(path: Path) -> dict[tuple[str, str], str]:
    """답표 md → {(id, axis): choice}. `axis: CHOICE | quote` 형식."""
    labels: dict[tuple[str, str], str] = {}
    cur = None
    for line in path.read_text(encoding="utf-8").splitlines():
        h = re.match(r"^##\s+([A-Z0-9]+)\s*\(", line)
        if h:
            cur = h.group(1)
            continue
        m = re.match(r"^([a-z_]{3,})\s*:\s*([A-F])\b", line)
        if cur and m:
            labels[(cur, m.group(1))] = m.group(2)
    return labels


def build_consensus(label_sets: dict[str, dict]) -> dict[tuple[str, str], dict]:
    """라벨러별 답표들 → 셀별 {choice, votes, status}. status: agree/solo/DISPUTE."""
    cells = {k for s in label_sets.values() for k in s}
    out: dict[tuple[str, str], dict] = {}
    for cell in cells:
        votes = {who: s[cell] for who, s in label_sets.items() if cell in s}
        cnt = Counter(votes.values())
        top, n = cnt.most_common(1)[0]
        if len(votes) == 1:
            out[cell] = {"choice": top, "votes": votes, "status": "solo"}
        elif n >= 2:  # ≥2/3 합의
            out[cell] = {"choice": top, "votes": votes, "status": "agree"}
        else:
            out[cell] = {"choice": None, "votes": votes, "status": "DISPUTE"}
    return out


# ── 지표 ────────────────────────────────────────────────────────────

def quad_kappa(pairs: list[tuple[int, int]]) -> float | None:
    """이차 가중 Cohen's kappa (범주 1~5). pairs=(gold, pred)."""
    if len(pairs) < 2:
        return None
    cats = [1, 2, 3, 4, 5]
    idx = {c: i for i, c in enumerate(cats)}
    n = len(pairs)
    obs = [[0] * 5 for _ in range(5)]
    for g, p in pairs:
        obs[idx[g]][idx[p]] += 1
    gr = [sum(obs[i]) for i in range(5)]
    pr = [sum(obs[i][j] for i in range(5)) for j in range(5)]
    W = [[((i - j) ** 2) / 16 for j in range(5)] for i in range(5)]
    num = sum(W[i][j] * obs[i][j] for i in range(5) for j in range(5))
    den = sum(W[i][j] * gr[i] * pr[j] / n for i in range(5) for j in range(5))
    if den == 0:
        return 1.0
    return 1 - num / den


def spearman(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 3:
        return None

    def ranks(xs):
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        r = [0.0] * len(xs)
        i = 0
        while i < len(xs):
            j = i
            while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = ranks([a for a, _ in pairs]), ranks([b for _, b in pairs])
    n = len(pairs)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    vx = sum((r - mx) ** 2 for r in rx) ** 0.5
    vy = sum((r - my) ** 2 for r in ry) ** 0.5
    return cov / (vx * vy) if vx and vy else None


# ── EXAONE 채점 ─────────────────────────────────────────────────────

def score_exaone(scenarios, runs, rubrics, directions, client):
    """{(id, axis): choice} — 운영 P1 경로, 축당 runs회 다수결."""
    out: dict[tuple[str, str], str] = {}
    for sid, scn in scenarios.items():
        info = f"{TYPE_KO[scn['type']]}, {scn['age']}세"
        for axis, utters in scn["axis_input"].items():
            if axis not in rubrics:
                continue
            input_text = "\n".join(f"- {u}" for u in utters)
            msgs = axis_scoring.build_p1_messages(
                rubrics[axis], directions.get(axis, ""), info, input_text)
            choices = []
            for _ in range(runs):
                try:
                    raw = client.chat(msgs, temperature=0.0, max_tokens=400,
                                      enable_thinking=False)
                    parsed = axis_scoring.parse_p1(raw, input_text)
                    if parsed["choice"]:
                        choices.append(parsed["choice"])
                except Exception as e:  # noqa: BLE001
                    print(f"  [warn] {sid} {axis}: {e}")
            if choices:
                out[(sid, axis)] = Counter(choices).most_common(1)[0][0]
    return out


# ── 리포트 ──────────────────────────────────────────────────────────

def report_metrics(consensus, exaone):
    per_axis = defaultdict(list)   # axis → [(gold_choice, pred_choice)]
    f_cells = {"gold_F_pred_F": 0, "gold_F_pred_score": 0, "gold_score_pred_F": 0}
    for cell, info in consensus.items():
        if info["status"] == "DISPUTE":
            continue
        g = info["choice"]
        p = exaone.get(cell)
        if p is None:
            continue
        _, axis = cell
        if g == "F" or p == "F":
            if g == "F" and p == "F":
                f_cells["gold_F_pred_F"] += 1
            elif g == "F":
                f_cells["gold_F_pred_score"] += 1
            else:
                f_cells["gold_score_pred_F"] += 1
            continue
        per_axis[axis].append((g, p))

    print(f"\n{'축':<40} {'n':>3} {'정확':>6} {'인접':>6} {'MAE':>6} {'κ_qw':>6} {'ρ':>6}")
    print("-" * 74)
    all_pairs = []
    for axis in sorted(per_axis):
        pairs = per_axis[axis]
        all_pairs += pairs
        ordp = [(ORD[g], ORD[p]) for g, p in pairs]
        n = len(pairs)
        exact = sum(g == p for g, p in ordp) / n
        adj = sum(abs(g - p) <= 1 for g, p in ordp) / n
        mae = sum(abs(g - p) for g, p in ordp) / n * 0.2  # 단계차 → 0.2 스케일
        kap = quad_kappa(ordp)
        rho = spearman([(float(g), float(p)) for g, p in ordp])
        print(f"{axis:<40} {n:>3} {exact:>6.2f} {adj:>6.2f} {mae:>6.2f} "
              f"{'  -  ' if kap is None else f'{kap:>6.2f}'} "
              f"{'  -  ' if rho is None else f'{rho:>6.2f}'}")
    if all_pairs:
        o = [(ORD[g], ORD[p]) for g, p in all_pairs]
        n = len(o)
        print("-" * 74)
        print(f"{'전체(pooled)':<40} {n:>3} {sum(g==p for g,p in o)/n:>6.2f} "
              f"{sum(abs(g-p)<=1 for g,p in o)/n:>6.2f} "
              f"{sum(abs(g-p) for g,p in o)/n*0.2:>6.2f} "
              f"{quad_kappa(o):>6.2f} {spearman([(float(g),float(p)) for g,p in o]):>6.2f}")
    print(f"\nF 처리: 둘다F {f_cells['gold_F_pred_F']} / "
          f"정답F·EXAONE점수 {f_cells['gold_F_pred_score']} / "
          f"정답점수·EXAONE_F {f_cells['gold_score_pred_F']}")


def report_contrast(exaone):
    print("\n── 대조쌍 (변별·축분리) ──")
    for lo, hi, varied in CONTRAST:
        pl, ph = exaone.get((lo, varied)), exaone.get((hi, varied))
        if pl and ph:
            ok = "✓" if ORD.get(pl, 0) < ORD.get(ph, 0) else "✗ (변별 실패)"
            print(f"{varied}: {lo}={pl} → {hi}={ph}  {ok}")
        # 분리 — 비-varied 축 Δ
        deltas = []
        for (sid, axis), _ in exaone.items():
            if sid == lo and axis != varied and (hi, axis) in exaone:
                d = abs(ORD.get(exaone[(lo, axis)], 0) - ORD.get(exaone[(hi, axis)], 0))
                deltas.append((axis, d))
        if deltas:
            avg = sum(d for _, d in deltas) / len(deltas)
            moved = [a for a, d in deltas if d > 0]
            print(f"   분리: 비-varied 축 평균 Δ단계 {avg:.2f}"
                  + (f" · 움직인 축 {moved}" if moved else " · 전부 고정 ✓"))


# ── main ────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--labels", default="11_정답표_v1.md,12_정답표_GPT.md,13_정답표_Gemini.md")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--go", action="store_true", help="EXAONE 실호출 (없으면 합의표만)")
    args = ap.parse_args()

    scenarios = load_scenarios()
    rubrics, directions = axis_scoring.load_rubrics()

    label_sets = {}
    for name in [s.strip() for s in args.labels.split(",") if s.strip()]:
        p = HERE / name
        if p.exists():
            label_sets[name] = load_labels(p)
        else:
            print(f"[skip] 답표 없음: {name}")
    if not label_sets:
        raise SystemExit("답표가 하나도 없음 — 최소 11_정답표_v1.md 필요")
    consensus = build_consensus(label_sets)

    n_disp = sum(1 for v in consensus.values() if v["status"] == "DISPUTE")
    n_solo = sum(1 for v in consensus.values() if v["status"] == "solo")
    print(f"라벨러 {len(label_sets)}종: {', '.join(label_sets)}")
    print(f"합의 셀 {len(consensus)}개 · 합의 {len(consensus)-n_disp-n_solo} · "
          f"solo {n_solo} · DISPUTE {n_disp}")
    if n_disp:
        print("  DISPUTE(사람 판정 대상):")
        for cell, v in consensus.items():
            if v["status"] == "DISPUTE":
                print(f"   {cell[0]} {cell[1]}: {v['votes']}")

    if not args.go:
        print("\n[드라이런] EXAONE 비교는 --go. (지금은 합의 정답표만 점검)")
        return

    from app.llm.exaone import ExaoneClient
    client = ExaoneClient()
    if getattr(client, "is_stub", False):
        raise SystemExit("EXAONE 스텁 모드 — .env 의 EXAONE_BASE_URL/MODEL/API_KEY 확인")

    n_calls = sum(len([a for a in s["axis_input"] if a in rubrics])
                  for s in scenarios.values()) * args.runs
    print(f"\nEXAONE 호출 예정: {n_calls}회 (페르소나 축 × runs {args.runs})")
    exaone = score_exaone(scenarios, args.runs, rubrics, directions, client)

    report_metrics(consensus, exaone)
    report_contrast(exaone)

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"eval_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for cell, info in consensus.items():
            f.write(json.dumps({"id": cell[0], "axis": cell[1],
                                "gold": info["choice"], "status": info["status"],
                                "votes": info["votes"],
                                "exaone": exaone.get(cell)}, ensure_ascii=False) + "\n")
    print(f"\n셀별 결과 저장: {out}")


if __name__ == "__main__":
    main()
