"""04 확정 — 사람 판정자(3번째)의 결정 5건을 두 판정표 위에 적용해 골드셋을 확정한다.

결정 기록 (2026-07-29, 판정자: 조대흠):
  D1 일상 장소 등재: 시스템(Phase 0)이 routine_destinations 를 끌림점으로 등록하므로
     GPT안 채택 — 일상 장소를 caregiver_report 로 등재.
  D2 발견 지점 literal: evidence 정의("과거 실종 때 실제 발견된 곳")를 문자 적용.
     목적지(정미소·인쇄소·경동시장)는 caregiver_report 로, 실제 발견 지점
     (G14 106번 정류장, G12 정류장·역입구)은 previous_missing_found 로 등재.
  D3 위치 특정 불가 제외: G13 친정, G19 PC방 — 끌림점 제외(forbidden 유지).
  D4 G16 에스컬레이터 제외: 장소 미특정 + 보호자가 이동 연결을 명시 부정 →
     abstract_preferences 로만. (대조쌍 약 케이스는 후보 부재가 대조 성립 조건)
  D5 G20 B_불안 문구점: allowed 포함 — forbidden 은 치명 채점이라 보수 원칙,
     우열은 expected_relation 이 담당.

allowed 는 두 판정자 교집합(보수), forbidden 도 교집합. 교집합 밖 attraction 은
'중립'(비권장·비치명)으로 남는다 — eval 이 별도 집계한다.

산출: 04_정답표_합의.md (사람용) + 04_gold.jsonl (eval 소비용)
"""
from __future__ import annotations

import json
from pathlib import Path

from build_consensus import canon, load, norm_goals, rng_intersect

HERE = Path(__file__).parent

PROVENANCE = {
    "judges": ["GPT-5.6 Sol", "Gemini (버전 미상 — 사용자 확인 불가)",
               "사람 3판정: 조대흠 (결정 D1~D5)"],
    "instruction": "02_판정_지시서.md v1.0",
    "date": "2026-07-29",
    "note": "합의 규칙: attractions=결정 적용 / allowed·forbidden=교집합 / confusion=교집합",
}

# D1·D2·D3·D4 — 시나리오별 attractions 확정 오버라이드 {gid: {label: evidence|None(제외)}}
ATTR_OVERRIDE: dict[str, dict[str, str | None]] = {
    "G05": {"복지관": "caregiver_report"},
    "G06": {"학교": "caregiver_report"},
    "G09": {"김포 정미소 자리": "caregiver_report"},
    "G11": {"한강 산책로(강변 벤치)": "previous_missing_found"},
    "G12": {"을지로 인쇄소": "caregiver_report",
            "큰길 버스정류장": "previous_missing_found",
            "지하철역 입구": "previous_missing_found"},
    "G13": {"친정": None},
    "G14": {"106번 버스 정류장": "previous_missing_found",
            "경동시장": "caregiver_report"},
    "G15": {"학교": "caregiver_report", "치료실": "caregiver_report"},
    "G16": {"학교": "caregiver_report", "치료실": "caregiver_report",
            "에스컬레이터": None},
    "G17": {"학교": "caregiver_report", "복지관": "caregiver_report"},
    "G19": {"PC방": None},
}

# D5 — 상황 allowed 추가 {(gid, situation): [labels]}
ALLOWED_ADD = {("G20", "B_불안"): ["문구점"]}


def main() -> None:
    gem = load(HERE / "03_정답표_gemini.md")
    gpt = load(HERE / "03_정답표_gpt.md")
    gold: list[dict] = []
    md = ["# 마음 골드셋 v1 — 확정 합의표 (04)", "",
          f"판정: {' / '.join(PROVENANCE['judges'])} · {PROVENANCE['date']}",
          "결정 D1~D5 상세는 apply_decisions.py 헤더. ⚠ dev=G01~G08 / test=G09~G20 봉인.", ""]

    for gid in sorted(gem.keys()):
        a, b = gem[gid], gpt[gid]
        A = {canon(x["label"]): x["evidence"] for x in a["gold_persona"]["attractions"]}
        B = {canon(x["label"]): x["evidence"] for x in b["gold_persona"]["attractions"]}
        attrs: dict[str, str] = {}
        # 오버라이드 키도 판정표와 같은 정규화를 거친다 ("김포 정미소 자리"≡"김포 정미소")
        ov = {canon(k): v for k, v in ATTR_OVERRIDE.get(gid, {}).items()}
        for lb in sorted(set(A) | set(B)):
            if lb in ov:
                if ov[lb] is not None:
                    attrs[lb] = ov[lb]
                continue
            ea, eb = A.get(lb), B.get(lb)
            if ea and eb and ea == eb:
                attrs[lb] = ea
            elif ea and eb:
                raise SystemExit(f"미해결 evidence 충돌: {gid}/{lb} — 오버라이드 필요")
            else:
                raise SystemExit(f"미해결 단독 등재: {gid}/{lb} — 오버라이드 필요")

        space = set(attrs)
        abstract = sorted(set(a["gold_persona"].get("abstract_preferences", []))
                          | set(b["gold_persona"].get("abstract_preferences", [])))
        situations = {}
        for sk in ("A_귀소", "B_불안"):
            sa, sb = a["situations"][sk], b["situations"][sk]
            al_a, _ = norm_goals(sa["allowed_goals"], space)
            al_b, _ = norm_goals(sb["allowed_goals"], space)
            fb_a, _ = norm_goals(sa["forbidden_goals"], space)
            fb_b, _ = norm_goals(sb["forbidden_goals"], space)
            allowed = al_a & al_b
            for extra in ALLOWED_ADD.get((gid, sk), []):
                allowed.add(extra)
            forbidden = (fb_a & fb_b) - allowed
            cr = rng_intersect(sa["confusion_range"], sb["confusion_range"])
            if cr is None:
                raise SystemExit(f"confusion 교집합 없음: {gid}/{sk}")
            situations[sk] = {
                "allowed_goals": sorted((g for g in allowed if g), key=str) + ([None] if None in allowed else []),
                "forbidden_goals": sorted(g for g in forbidden if g),
                "confusion_range": cr,
                "expected_relation": b["situations"][sk].get("expected_relation", ""),
                "forbidden_narratives": sorted(set(sa.get("forbidden_narratives", []))
                                               | set(sb.get("forbidden_narratives", []))),
            }
        gold.append({"id": gid, "split": "dev" if gid <= "G08" else "test",
                     "attractions": [{"label": lb, "evidence": ev} for lb, ev in attrs.items()],
                     "abstract_preferences": abstract,
                     "situations": situations})
        md.append(f"## {gid} ({gold[-1]['split']})")
        for lb, ev in attrs.items():
            md.append(f"- 끌림점: {lb} [{ev}]")
        for sk, s in situations.items():
            md.append(f"- {sk}: allowed={s['allowed_goals']} forbidden={s['forbidden_goals']} "
                      f"confusion={s['confusion_range']}")
        md.append("")

    (HERE / "04_gold.jsonl").write_text(
        "\n".join(json.dumps(g, ensure_ascii=False) for g in gold), encoding="utf-8")
    (HERE / "04_정답표_합의.md").write_text("\n".join(md), encoding="utf-8")
    print(f"확정 {len(gold)}건 → 04_정답표_합의.md / 04_gold.jsonl")


if __name__ == "__main__":
    main()
