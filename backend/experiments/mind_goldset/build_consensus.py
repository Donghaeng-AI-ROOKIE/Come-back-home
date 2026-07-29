"""판정자 정답표 → 합의 초안(04) 생성.

합의 규칙 (README 판정 절차의 기계화):
  R1 goal 공간 = 그 시나리오의 끌림점 라벨 ∪ {null}. '집'·동네 라벨은 후보가
     아니므로 제거 — 귀소는 goal_label 이 아니라 전략·게이지 소관(시스템 설계).
  R2 라벨 동치 — 판정자 간 표기 차이는 동치맵으로 정규화.
  R3 allowed = 교집합(둘 다 허용한 것만). R4 forbidden = 교집합(보수 원칙).
  R5 충돌(한쪽 allowed ∩ 다른쪽 forbidden) = 사람 결정 항목.
  R6 confusion_range = 구간 교집합, 비면 사람 결정.
  R7 attractions: 동치 정규화 후 둘 다 있으면 합의(evidence 다르면 사람 결정),
     한쪽만 있으면 사람 결정.

실행: python build_consensus.py  → 04_정답표_합의_draft.md
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).parent

# R2 — 라벨 동치맵 (대표라벨: 변형들)
CANON = {
    "옛 봉제공장": ["봉제공장"],
    "김포 정미소 자리": ["김포 정미소"],
    "한강 산책로(강변 벤치)": ["한강 산책로의 강변 벤치", "강변 산책로 벤치", "한강 산책로"],
    "을지로 인쇄소": ["을지로(인쇄소 방향)"],
    "예전 등굣길": ["옛 등굣길"],
    "집 앞 편의점": ["편의점"],
    "청량리 경동시장": ["경동시장"],
    "현대백화점 에스컬레이터": ["에스컬레이터"],
}
_C = {v: k for k, vs in CANON.items() for v in vs}

# R1 — goal 공간에서 제거할 비후보(귀소·행정동·집)
_HOME_PAT = re.compile(r"\(집\)|그룹홈|내부 체류|^집$")


def canon(label):
    if label is None:
        return None
    return _C.get(label, label)


def load(path: Path) -> dict[str, dict]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("{"):
            d = json.loads(line)
            out[d["id"]] = d
    return out


def goal_space(*judges_attrs) -> set:
    s = set()
    for attrs in judges_attrs:
        s |= {canon(a["label"]) for a in attrs}
    return s


def norm_goals(goals, space):
    """정규화 + R1 필터. 반환: (공간 내 goal set, 제거된 것들)"""
    kept, dropped = set(), []
    for g in goals:
        if g is None:
            kept.add(None)
            continue
        if _HOME_PAT.search(g):
            dropped.append(g)
            continue
        cg = canon(g)
        if cg in space:
            kept.add(cg)
        else:
            dropped.append(g)
    return kept, dropped


def rng_intersect(a, b):
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    return [round(lo, 2), round(hi, 2)] if lo <= hi else None


def fmt_goals(s):
    return "[" + ", ".join(sorted(("null" if g is None else g) for g in s)) + "]"


def main() -> None:
    gem = load(HERE / "03_정답표_gemini.md")
    gpt = load(HERE / "03_정답표_gpt.md")
    lines = ["# 마음 골드셋 v1 — 합의 초안 (2/2 판정자 자동 대조)",
             "",
             "판정자: Gemini·GPT (버전 미기재 — 확정 시 기입). 합의 규칙 R1~R7 은 build_consensus.py 헤더.",
             "⚖️ 표시는 판정자 불일치 = **3번째 판정자(사람) 결정 필요** 항목. 결정 전까지 골드셋 미확정.",
             ""]
    n_agree_field = n_conflict = 0
    conflicts: list[str] = []

    for gid in sorted(gem.keys()):
        a, b = gem[gid], gpt[gid]
        lines.append(f"## {gid}")

        # R7 attractions
        A = {canon(x["label"]): x["evidence"] for x in a["gold_persona"]["attractions"]}
        B = {canon(x["label"]): x["evidence"] for x in b["gold_persona"]["attractions"]}
        space = set(A) | set(B)
        lines.append("- gold_persona.attractions:")
        for lb in sorted(space):
            ea, eb = A.get(lb), B.get(lb)
            if ea and eb and ea == eb:
                lines.append(f"  - ✅ {lb} [{ea}]")
                n_agree_field += 1
            elif ea and eb:
                lines.append(f"  - ⚖️ {lb} — evidence 불일치: Gemini={ea} / GPT={eb}")
                conflicts.append(f"{gid} attractions/{lb}: evidence {ea} vs {eb}")
                n_conflict += 1
            else:
                who, ev = ("Gemini", ea) if ea else ("GPT", eb)
                lines.append(f"  - ⚖️ {lb} [{ev}] — {who}만 등재")
                conflicts.append(f"{gid} attractions/{lb}: {who}만 등재")
                n_conflict += 1

        # situations
        for sk in ("A_귀소", "B_불안"):
            sa, sb = a["situations"][sk], b["situations"][sk]
            al_a, drop_a = norm_goals(sa["allowed_goals"], space)
            al_b, drop_b = norm_goals(sb["allowed_goals"], space)
            fb_a, _ = norm_goals(sa["forbidden_goals"], space)
            fb_b, _ = norm_goals(sb["forbidden_goals"], space)
            allowed = al_a & al_b
            forbidden = fb_a & fb_b
            # R5 충돌
            cross = (al_a & fb_b) | (al_b & fb_a)
            cr = rng_intersect(sa["confusion_range"], sb["confusion_range"])
            mark = ""
            if cross:
                mark = f" ⚖️ 충돌: {fmt_goals(cross)} (한쪽 allowed·다른쪽 forbidden)"
                conflicts.append(f"{gid} {sk}: allowed/forbidden 충돌 {fmt_goals(cross)}")
                n_conflict += 1
            else:
                n_agree_field += 1
            lines.append(f"- {sk}: allowed={fmt_goals(allowed)} forbidden={fmt_goals(forbidden)}"
                         f" confusion={cr if cr else '⚖️ 교집합 없음'}{mark}")
            if cr is None:
                conflicts.append(f"{gid} {sk}: confusion 교집합 없음 "
                                 f"{sa['confusion_range']} vs {sb['confusion_range']}")
                n_conflict += 1
            dropped = drop_a + drop_b
            if dropped:
                lines.append(f"  - R1 제거(비후보): {sorted(set(dropped))}")
            # 관계·금지서사 — 자동 병합(합집합, 사람 검토 후 확정)
            lines.append(f"  - relation(Gemini): {sa['expected_relation']}")
            lines.append(f"  - relation(GPT): {sb['expected_relation']}")
        lines.append("")

    lines += ["---", f"## 집계: 자동 합의 필드 {n_agree_field} · ⚖️ 사람 결정 필요 {n_conflict}", "",
              "### ⚖️ 결정 필요 목록"] + [f"- {c}" for c in conflicts]
    out = HERE / "04_정답표_합의_draft.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"저장: {out}")
    print(f"자동 합의 {n_agree_field} / 사람 결정 {n_conflict}")
    print("\n".join("⚖️ " + c for c in conflicts))


if __name__ == "__main__":
    main()
