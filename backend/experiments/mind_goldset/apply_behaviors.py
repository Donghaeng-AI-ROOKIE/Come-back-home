"""v1.1 행동 라벨 합의 — 판정자 3인(2/3 다수결)으로 확정해 04_gold.jsonl 에 병합.

왜 별도 스크립트인가: 목적지 라벨(v1.0)은 apply_decisions.py 로 이미 확정·봉인됐다.
행동 라벨은 그 위에 얹는 델타라, v1.0 을 재실행(재판정 유발)하지 않고 04 를
제자리 갱신한다.

합의 규칙 (판정자 3인이라 v1.0 의 2인 교집합 대신 다수결):
  각 (시나리오, 상황, 행동)에 대해 판정자 입장 ∈ {allowed, forbidden, 무언급}.
  allowed  = 2인 이상이 allowed
  forbidden = 2인 이상이 forbidden (allowed 와 동시 성립 불가 — 입장은 배타)
  1 allowed vs 1 forbidden vs 1 무언급 = 다수 없음 → 중립 처리하되 사람 결정
  항목으로 출력. OVERRIDE 로 확정 후 재실행.

실행: python apply_behaviors.py
입력: 03b_행동정답표_{grok,gemini,gpt}.md (05 프롬프트로 생성)
출력: 04_gold.jsonl (allowed_behaviors/forbidden_behaviors 필드 추가),
      04b_행동_합의.md (사람용 표 + 판정자별 원본 입장)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent

JUDGES = ["grok", "gemini", "gpt"]
BEHAVIORS = ["끌림점 접근", "귀소 시도", "은신·멈춤", "계속 배회"]
# 판정자 표기 변형 → 정본 (닫힌 어휘 밖 표기는 오류로 중단)
_B_CANON = {
    "은신/멈춤": "은신·멈춤", "은신 멈춤": "은신·멈춤", "은신,멈춤": "은신·멈춤",
    "끌림점접근": "끌림점 접근", "계속배회": "계속 배회",
}

# 다수 없음(1a vs 1f vs 1무언급) 시 사람 결정 (판정자: 조대흠, 2026-07-29)
# 3건 모두 중립 — 다수 없는 갈림은 라벨 없이 두는 보수 원칙 일관 적용.
# {(gid, situation, behavior): "allowed"|"forbidden"|"neutral"}
OVERRIDE: dict[tuple[str, str, str], str] = {
    ("G15", "B_불안", "계속 배회"): "neutral",
    ("G17", "B_불안", "은신·멈춤"): "neutral",
    ("G20", "B_불안", "은신·멈춤"): "neutral",
}

PROVENANCE = ("행동 라벨 v1.1 — 판정: Grok/Gemini/GPT (버전 미상, 03b, 05 프롬프트) "
              "2/3 다수결 + 다수 없음은 사람 결정(조대흠, OVERRIDE). 2026-07-29.")


def canon_b(name: str) -> str:
    n = _B_CANON.get(name.strip(), name.strip())
    if n not in BEHAVIORS:
        sys.exit(f"닫힌 어휘 밖 행동명: {name!r} — 판정표 수정 또는 _B_CANON 추가 필요")
    return n


def load_flexible(path: Path) -> dict[str, dict]:
    """03b 판정표 로더 — 한 줄 JSON 과 ```json 펜스 블록(여러 줄) 모두 허용."""
    if not path.exists():
        sys.exit(f"판정표 없음: {path.name} — 05_행동판정_프롬프트.md 로 생성 후 저장할 것")
    text = path.read_text(encoding="utf-8")
    out: dict[str, dict] = {}
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if not blocks:  # 펜스가 없으면 {"id" 로 시작하는 균형 중괄호 블록을 스캔
        dec = json.JSONDecoder()
        i = 0
        while (j := text.find('{"id"', i)) != -1:
            try:
                d, end = dec.raw_decode(text[j:])
                blocks.append(text[j:j + end])
                i = j + end
            except json.JSONDecodeError:
                i = j + 1
    for b in blocks:
        d = json.loads(b)
        out[d["id"]] = d
    if not out:
        sys.exit(f"{path.name} 에서 시나리오 JSON 을 하나도 못 읽음 — 형식 확인")
    return out


def stance(judge_situation: dict, behavior: str) -> str:
    if behavior in {canon_b(b) for b in judge_situation.get("allowed_behaviors", [])}:
        return "a"
    if behavior in {canon_b(b) for b in judge_situation.get("forbidden_behaviors", [])}:
        return "f"
    return "-"


def main() -> None:
    tables = {j: load_flexible(HERE / f"03b_행동정답표_{j}.md") for j in JUDGES}
    gold = [json.loads(line) for line in (HERE / "04_gold.jsonl").open(encoding="utf-8")]
    missing = [(j, g["id"]) for g in gold for j in JUDGES if g["id"] not in tables[j]]
    if missing:
        sys.exit(f"판정 누락: {missing}")

    undecided: list[str] = []
    md = ["# 행동 라벨 합의 (04b) — v1.1", "", PROVENANCE, "",
          "입장 표기: a=allowed, f=forbidden, -=무언급 (순서: grok/gemini/gpt)", "",
          "| 시나리오 | 상황 | 행동 | 입장 | 합의 |", "|---|---|---|---|---|"]

    for g in gold:
        gid = g["id"]
        for sk, s in g["situations"].items():
            allowed, forbidden = set(), set()
            for beh in BEHAVIORS:
                st = [stance(tables[j][gid]["situations"][sk], beh) for j in JUDGES]
                n_a, n_f = st.count("a"), st.count("f")
                if n_a >= 2:
                    verdict = "allowed"
                    allowed.add(beh)
                elif n_f >= 2:
                    verdict = "forbidden"
                    forbidden.add(beh)
                elif n_a == 1 and n_f == 1:
                    ov = OVERRIDE.get((gid, sk, beh))
                    if ov == "allowed":
                        allowed.add(beh)
                    elif ov == "forbidden":
                        forbidden.add(beh)
                    elif ov is None:
                        undecided.append(f"{gid}/{sk}/{beh} ({'/'.join(st)})")
                    verdict = ov or "미결"
                else:
                    verdict = "중립"
                md.append(f"| {gid} | {sk} | {beh} | {'/'.join(st)} | {verdict} |")
            s["allowed_behaviors"] = sorted(allowed)
            s["forbidden_behaviors"] = sorted(forbidden)

    if undecided:
        print("다수 없음 — OVERRIDE 에 사람 결정 기입 후 재실행:")
        print("\n".join(f"  {u}" for u in undecided))
        sys.exit(1)

    (HERE / "04_gold.jsonl").write_text(
        "\n".join(json.dumps(g, ensure_ascii=False) for g in gold), encoding="utf-8")
    (HERE / "04b_행동_합의.md").write_text("\n".join(md), encoding="utf-8")
    print(f"행동 라벨 병합 완료 — 시나리오 {len(gold)}건 → 04_gold.jsonl / 04b_행동_합의.md")


if __name__ == "__main__":
    main()
