"""v1.1 행동 라벨 합의 — 03b 행동정답표 2부를 교집합으로 확정해 04_gold.jsonl 에 병합.

왜 별도 스크립트인가: 목적지 라벨(v1.0)은 apply_decisions.py 로 이미 확정·봉인됐다.
행동 라벨은 그 위에 얹는 델타라, v1.0 을 재실행(재판정 유발)하지 않고 04 를
제자리 갱신한다. 합의 규칙은 v1.0 과 동일 철학:
  allowed = 두 판정자 교집합(둘 다 그럴듯하다고 본 행동만)
  forbidden = 교집합 - allowed (보수 원칙 — 위반은 치명 채점)
  충돌(한쪽 allowed ∩ 다른쪽 forbidden) = 사람 결정 항목으로 출력, OVERRIDE 로 확정

실행: python apply_behaviors.py
입력: 03b_행동정답표_gpt.md, 03b_행동정답표_gemini.md (05 프롬프트로 생성)
출력: 04_gold.jsonl (allowed_behaviors/forbidden_behaviors 필드 추가),
      04b_행동_합의.md (사람용 표 + 충돌 목록)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent

BEHAVIORS = ["끌림점 접근", "귀소 시도", "은신·멈춤", "계속 배회"]
# 판정자 표기 변형 → 정본 (닫힌 어휘 밖 표기는 오류로 중단)
_B_CANON = {
    "은신/멈춤": "은신·멈춤", "은신 멈춤": "은신·멈춤", "은신,멈춤": "은신·멈춤",
    "끌림점접근": "끌림점 접근", "계속배회": "계속 배회",
}

# 충돌 시 사람 결정 (판정자: 조대흠) — {(gid, situation, behavior): "allowed"|"forbidden"|"neutral"}
OVERRIDE: dict[tuple[str, str, str], str] = {}

PROVENANCE = ("행동 라벨 v1.1 — 판정: GPT / Gemini (03b, 05 프롬프트) + 사람 결정 OVERRIDE. "
              "합의: allowed=교집합, forbidden=교집합-allowed.")


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


def main() -> None:
    gpt = load_flexible(HERE / "03b_행동정답표_gpt.md")
    gem = load_flexible(HERE / "03b_행동정답표_gemini.md")
    gold = [json.loads(line) for line in (HERE / "04_gold.jsonl").open(encoding="utf-8")]
    missing = [g["id"] for g in gold if g["id"] not in gpt or g["id"] not in gem]
    if missing:
        sys.exit(f"판정 누락 시나리오: {missing}")

    conflicts: list[str] = []
    md = ["# 행동 라벨 합의 (04b) — v1.1", "", PROVENANCE, "",
          "| 시나리오 | 상황 | allowed | forbidden |", "|---|---|---|---|"]

    for g in gold:
        gid = g["id"]
        for sk, s in g["situations"].items():
            aa = {canon_b(b) for b in gpt[gid]["situations"][sk].get("allowed_behaviors", [])}
            ab = {canon_b(b) for b in gpt[gid]["situations"][sk].get("forbidden_behaviors", [])}
            ba = {canon_b(b) for b in gem[gid]["situations"][sk].get("allowed_behaviors", [])}
            bb = {canon_b(b) for b in gem[gid]["situations"][sk].get("forbidden_behaviors", [])}
            allowed = aa & ba
            forbidden = (ab & bb) - allowed
            for beh in (aa & bb) | (ba & ab):    # 한쪽 allowed ∩ 다른쪽 forbidden
                ov = OVERRIDE.get((gid, sk, beh))
                if ov == "allowed":
                    allowed.add(beh)
                elif ov == "forbidden":
                    forbidden.add(beh)
                elif ov is None:
                    conflicts.append(f"{gid}/{sk}/{beh} (gpt {'a' if beh in aa else 'f'} vs gemini {'a' if beh in ba else 'f'})")
            s["allowed_behaviors"] = sorted(allowed)
            s["forbidden_behaviors"] = sorted(forbidden)
            md.append(f"| {gid} | {sk} | {', '.join(sorted(allowed)) or '—'} "
                      f"| {', '.join(sorted(forbidden)) or '—'} |")

    if conflicts:
        print("사람 결정 필요한 충돌 — OVERRIDE 에 기입 후 재실행:")
        print("\n".join(f"  {c}" for c in conflicts))
        sys.exit(1)

    (HERE / "04_gold.jsonl").write_text(
        "\n".join(json.dumps(g, ensure_ascii=False) for g in gold), encoding="utf-8")
    (HERE / "04b_행동_합의.md").write_text("\n".join(md), encoding="utf-8")
    print(f"행동 라벨 병합 완료 — 시나리오 {len(gold)}건 → 04_gold.jsonl / 04b_행동_합의.md")


if __name__ == "__main__":
    main()
