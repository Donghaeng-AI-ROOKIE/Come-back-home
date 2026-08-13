"""RAG 정합 검사 — 파인튜닝 답과 검색 발췌가 어긋나는 지점을 검증신호로 뽑는다.

노션 P1-4 의 "파인튜닝된 답과 RAG grounding 이 어긋나면 검증신호로 활용
(파인튜닝 환각 감지)" 항목의 구현이다.

왜 수치만 보는가:
  문장 전체의 함의를 대조하려면 판정자 모델이 필요한데, LLM 판정자는 P1-7 에서
  상관 실측 후 도입이 보류됐다. 반면 이 도메인의 환각은 **수치에서 가장 잘 드러난다**
  — 07-28 평가에서 base 모델이 내놓은 숫자 중 정답과 일치한 비율이 3.6% 였다
  (RAG+LoRA 는 30.1%). 수치 대조는 결정적이고 재현 가능하며, 가장 위험한 환각을 잡는다.

무엇을 근거로 인정하는가:
  ① 검색된 논문 발췌   ② 모델에게 준 입력(실종자 정보)
  둘 중 어디에도 없는 수치를 모델이 말했다면 지어낸 것이다.

한계 — 이건 환각 탐지기가 아니라 **신호**다:
  - 수치 없는 환각(잘못된 인과 주장)은 못 잡는다.
  - 상식적 계산(예: "절반"→"50%")을 미근거로 오판할 수 있다.
  - 그래서 이 결과로 출력을 막지 않는다. 기록하고 드러낼 뿐이다.
"""
from __future__ import annotations

import re

# 근거 없이 나와도 무해한 수치 — 순위·개수·연차 같은 서수/소수(小數)
_TRIVIAL = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "0"}

# 앞자리 0 을 생략한 소수(.51)도 잡는다 — 국내 저널·통계표에서 흔한 표기이고,
# 이걸 놓치면 원문에 있는 값을 "근거 없음"으로 잘못 신고한다(실측으로 확인됨).
_NUM = re.compile(r"\d+(?:[.,]\d+)?|\.\d+")


def _nums(text: str) -> set[str]:
    """수치 토큰 정규화 — 천단위 쉼표 제거, 앞자리 0 보정, 소수점 뒤 0 정리.

    `.51` 과 `0.51` 과 `0.510` 은 같은 값이므로 같은 토큰이 되어야 한다.
    """
    out = set()
    for m in _NUM.finditer(text or ""):
        v = m.group(0).replace(",", "")
        if v.startswith("."):
            v = "0" + v
        if "." in v:
            v = v.rstrip("0").rstrip(".")
        if v:
            out.add(v)
    return out


def check_numeric_grounding(answer: str, passages: list[str],
                            extra_context: str = "") -> dict:
    """답변의 수치가 발췌·입력에 실재하는지 대조.

    반환:
      supported    근거가 있는 수치
      unsupported  어디에도 없는 수치 (= 검증신호)
      ratio        전체 수치 중 근거 있는 비율 (수치가 없으면 None)
      flagged      근거 없는 수치가 하나라도 있으면 True
    """
    said = _nums(answer) - _TRIVIAL
    if not said:
        return {"supported": [], "unsupported": [], "ratio": None,
                "flagged": False, "checked": 0}

    evidence = set()
    for p in passages:
        evidence |= _nums(p)
    evidence |= _nums(extra_context)

    supported = sorted(said & evidence)
    unsupported = sorted(said - evidence)
    return {
        "supported": supported,
        "unsupported": unsupported,
        "ratio": len(supported) / len(said),
        "flagged": bool(unsupported),
        "checked": len(said),
    }


def summarize(report: dict) -> str:
    """사람이 읽는 한 줄 — 대시보드·로그용."""
    if not report or report.get("ratio") is None:
        return "정합 검사: 대조할 수치 없음"
    if not report["flagged"]:
        return f"정합 검사: 수치 {report['checked']}개 모두 발췌·입력에 근거함"
    return (f"⚠ 정합 검사: 수치 {report['checked']}개 중 "
            f"{len(report['unsupported'])}개가 근거 없음 "
            f"({', '.join(report['unsupported'][:5])})")
