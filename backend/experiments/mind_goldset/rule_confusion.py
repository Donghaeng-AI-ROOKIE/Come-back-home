"""혼란도 규칙 산정 실험 — LLM 없이 구조화 신호만으로 dev 범위를 맞출 수 있는가.

배경(2026-07-30 실측): 모델 4종×RAG 8셀 + 어댑터 4판 어디서도 LLM confusion
출력은 정보성이 없었다(고득점 셀은 전원-중 퇴화). 반면 판정자 3인이 혼란 범위에
2/3 합의할 수 있었다는 사실은 그 판단이 소수 요인(기능 수준·정보량·상황)으로
설명됨을 시사한다. 이 스크립트는 그 가설을 dev 16상황에서 수치로 검증한다.

규칙 요약 (파라미터 5개, 시나리오 ID 분기 금지 — 어휘는 일반 표현):
  기능수준 s = (손상 신호 수 - 명료 신호 수)   [보호자 진술 전체에서 어휘 매칭]
  정보 빈약 = '모름' 계열 표현 2회 이상
  A_귀소 기준값: 빈약→0.65(치매)/0.60(발달), s<=-2→0.40, s>=+2→0.70, 그 외 0.60
  B_불안: +0.15 (판정자 범위가 불안 상황에서 일관되게 상방)

주의: dev 를 보고 설계한 규칙이므로 dev 적합도는 일반화 증명이 아니다.
최종 판단은 봉인 test(G09~G20) 1회 측정. 운영 반영 시에는 등록 챗봇의
구조화 필드(기능 수준·정보량)를 직접 쓰므로 어휘 매칭 의존도가 낮아진다.

실행: python experiments/mind_goldset/rule_confusion.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).parent

# 인지·소통·이동 기능의 손상/명료 신호 — 일반 표현 어휘 (시나리오 특정어 금지)
IMPAIR = [
    r"못 타", r"못 외", r"못 말", r"말을 거의 안", r"대답을 잘 안",
    r"위험을 잘 몰라", r"잘 안 보고", r"중기", r"중증", r"중등도",
    r"[3-9]년 됐", r"주소.*딴 데", r"알아보지 못", r"대화가 잘 안",
]
CLEAR = [
    r"초기", r"경증", r"작년에", r"얼마 안 됐", r"대화는 아직 괜찮",
    r"말씀은 잘", r"혼자 잘 다", r"혼자 타", r"정정", r"이름[은이].*말해",
    r"성함은 대", r"간단한 대화",
]
UNKNOWN = [r"모르겠", r"잘 몰라요", r"파악을 못", r"확인해봐야", r"들은 적은 없", r"처음 겪"]


def load_scripts(split: str = "dev") -> dict[str, dict]:
    """01 대본의 해당 split 섹션을 {id: {'population':…, 'text':…}} 로 파싱."""
    text = (HERE / "01_시나리오_대화_v1.md").read_text(encoding="utf-8")
    out: dict[str, dict] = {}
    cur = None
    for line in text.splitlines():
        m = re.match(rf"## (G\d\d) \({split}\) — (치매|발달)", line)
        if m:
            cur = m.group(1)
            out[cur] = {"population": m.group(2), "text": ""}
            continue
        if line.startswith("## "):
            cur = None
        elif cur and line.startswith("- "):
            out[cur]["text"] += line + "\n"
    return out


def rule_confusion(population: str, notes_text: str, situation: str) -> float:
    unknown = sum(len(re.findall(p, notes_text)) for p in UNKNOWN)
    if unknown >= 2:
        base = 0.65 if population == "치매" else 0.60
    else:
        s = (sum(1 for p in IMPAIR if re.search(p, notes_text))
             - sum(1 for p in CLEAR if re.search(p, notes_text)))
        base = 0.40 if s <= -2 else (0.70 if s >= 2 else 0.60)
    if situation == "B_불안":
        base += 0.15
    return round(min(base, 1.0), 2)


def main(split: str = "dev", unseal: bool = False) -> None:
    if split == "test":
        if not unseal:
            raise SystemExit("test 는 봉인 — --unseal 을 명시해야 실행된다 (README 규칙)")
        from datetime import datetime
        with (HERE / "results" / "test_usage.log").open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now().isoformat()} test 실행 (rule_confusion — dev 설계 규칙 무수정 적용)\n")
    gold = {d["id"]: d for d in map(json.loads, (HERE / "04_gold.jsonl").open(encoding="utf-8"))
            if d["split"] == split}
    scripts = load_scripts(split)
    hit = total = 0
    print(f"{'ID':4} {'상황':6} {'규칙값':6} {'기대범위':12} 판정")
    for gid in sorted(gold):
        for sit in ("A_귀소", "B_불안"):
            lo, hi = gold[gid]["situations"][sit]["confusion_range"]
            v = rule_confusion(scripts[gid]["population"], scripts[gid]["text"], sit)
            ok = lo <= v <= hi
            hit += ok
            total += 1
            print(f"{gid:4} {sit:6} {v:<6} [{lo}, {hi}]{'':4} {'적합' if ok else '이탈'}")
    print(f"\n적합 {hit}/{total} = {hit/total:.0%}  (규칙은 결정론 — 반복 무의미)")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--unseal", action="store_true")
    a = ap.parse_args()
    main(a.split, a.unseal)
