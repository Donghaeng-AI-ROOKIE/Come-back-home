"""보호자 발화 → autobiographical_destination_pull 유래 끌림점별 route_familiarity 점수.

routine_destinations 유래 끌림점은 컴파일 대상에서 제외한다 — 작업4(unfamiliarity
게이지 재배치)에서 기본값 "높음"(gauges.ROUTINE_DEFAULT_FAMILIARITY=0.8)으로 이미
처리되므로 중복 채점이 불필요하다.

"list 출력" 패턴 — 기존 prior/mind 프롬프트가 "선택지 하나"만 받던 것과 다르게,
닫힌 후보 목록(끌림점 라벨) 각각에 A~E 등급을 매기는 형태로 설계한다
(goal_label 의 "실존 라벨만 인정" 가드레일 패턴을 리스트로 확장한 것). 등급 스케일은
axis_scoring 의 CHOICE_SCORE(A=0.1~E=0.9)와 동일 — 팀 확정 기준표(2026-07-20).

신뢰도 확보 방식도 axis_scoring 과 통일한다(2026-07-20 결정 — 시스템 전체에서
LLM 판정 신뢰도 산정 방식을 하나로 맞추는 게 유지보수에 유리하다는 판단):
- quote 강제 + 실존 검증(axis_scoring._quote_exists 재사용) — 입력에 없는 근거로
  판정하는 환각을 차단한다. quote 검증에 실패한 run 의 그 라벨 투표는 버린다.
- runs 회(기본 settings.axis_scoring_runs) 반복 후 라벨별 다수결
  (axis_scoring._majority 재사용) — temp 0 에서도 비결정성이 실측된 전례를 따른다.
- 일시 장애 1회 재시도(axis_scoring.RETRY_WAIT_S) — 골든타임과 무관한 백그라운드
  작업이라 재시도 여유가 있다.
- axis_scoring 과 달리 별도의 완료/실패 상태 리포트는 남기지 않는다 — 실패해도
  unfamiliarity() 의 거리 기반 근사로 안전하게 폴백하므로 재시도 인프라(stale 감지 등)를
  둘 이유가 약하다는 기존 판단은 유지.
"""

from __future__ import annotations

import time

from app.config import settings
from app.phase0 import axis_scoring
from app.phase2 import guardrail
from app.schemas.persona import Persona, RouteFamiliarity

_SYSTEM = """\
너는 실종자 수색(SAR) 행동 분석 전문가다. 보호자 발화에서, 주어진 장소 후보 각각에 \
대해 대상자가 그 장소까지 가는 길을 얼마나 잘 아는지 아래 기준표로 분류한다.

[기준표]
A. 처음 가거나 거의 경험하지 않은 장소·경로임
B. 방문 경험은 있지만 혼자 이동한 경험은 거의 없음
C. 가끔 이용했으며 일부 랜드마크나 구간을 알아봄
D. 반복적으로 이용한 익숙한 경로이며 평소 혼자 이동한 경험이 있음
E. 일상적으로 반복 이용하고 최근까지도 독립적으로 이동한 핵심 생활경로임
F. 언급은 됐지만 이 기준표로 판정할 근거가 부족함

출력 규칙:
- JSON 객체 하나만 출력한다. JSON 밖에 어떤 문장도 쓰지 않는다.
- 키는 주어진 장소 후보 라벨 중에서만 고른다. 후보에 없는 장소를 지어내지 않는다.
- 값은 {"choice": "A~F 중 하나", "quote": "..."} 형식의 객체.
- quote: 판정의 핵심 근거인 보호자 발화를 입력에서 글자 그대로 옮겨 적는다. \
choice 가 "F" 면 빈 문자열.
- 발화에 전혀 언급이 없는 장소는 아예 키를 넣지 마라(추측 금지)."""

_FEWSHOT_USER = """\
[장소 후보] 옛 직장(방직공장), 예전 살던 동네
[보호자 발화] "예전에 방직공장 다니던 길은 아직도 기억하시는지 가끔 그쪽으로 걸어가려고 하세요. \
예전 살던 동네는 재개발돼서 지금은 완전히 다른 곳이 됐는데도 가끔 거기 얘기를 하세요.\""""

_FEWSHOT_ASSISTANT = """\
{"옛 직장(방직공장)": {"choice": "D", "quote": "방직공장 다니던 길은 아직도 기억하시는지 \
가끔 그쪽으로 걸어가려고 하세요"}, "예전 살던 동네": {"choice": "A", "quote": "재개발돼서 \
지금은 완전히 다른 곳이 됐는데도 가끔 거기 얘기를 하세요"}}"""


def compile_route_familiarity(
    persona: Persona, client=None, runs: int | None = None,
) -> list[RouteFamiliarity]:
    """autobiographical_destination_pull 유래 끌림점의 route_familiarity 를 채점.

    다음 경우 LLM 호출 없이 빈 리스트를 반환한다(호출 낭비 방지):
    - 채점 대상 끌림점이 없음(치매 외 유형, 또는 해당 슬롯에서 나온 끌림점이 없음)
    - 근거 발화(axis_quotes["route_environment_familiarity"])가 아예 없음
    - client 가 스텁 모드(API 키 없음)
    """
    targets = [ap for ap in persona.attraction_points
               if ap.origin_slot == "autobiographical_destination_pull"]
    if not targets:
        return []
    evidence_text = "\n".join(persona.axis_quotes.get("route_environment_familiarity", []))
    if not evidence_text:
        return []   # 근거 발화 자체가 없으면 컴파일 스킵 — 폴백(거리근사)에 맡김

    if client is None:
        from app.llm.exaone import ExaoneClient

        client = ExaoneClient()
    if getattr(client, "is_stub", False):
        return []

    runs = runs or settings.axis_scoring_runs
    labels = [ap.label for ap in targets]
    prompt = "[장소 후보] " + ", ".join(labels) + "\n[보호자 발화] " + evidence_text
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _FEWSHOT_USER},
        {"role": "assistant", "content": _FEWSHOT_ASSISTANT},
        {"role": "user", "content": prompt},
    ]

    votes: dict[str, list[float | None]] = {label: [] for label in labels}
    for _ in range(runs):
        raw = None
        # 일시 장애 1회 재시도 — axis_scoring 과 동일 원칙(run 유실이 점수 품질 저하로 이어짐).
        for attempt in range(2):
            try:
                raw = client.chat(messages, temperature=0.0, max_tokens=400,
                                  enable_thinking=False)
                break
            except Exception:  # noqa: BLE001 — 호출 실패는 재시도 후 이 run 만 폐기
                if attempt == 0:
                    time.sleep(axis_scoring.RETRY_WAIT_S)
        if raw is None:
            continue
        data, _strict = axis_scoring._extract_json(raw)
        if not isinstance(data, dict):
            continue
        for label, item in data.items():
            if label not in votes or not isinstance(item, dict):
                continue   # 후보 밖 라벨(환각) 또는 형식 위반 — 버림
            choice = str(item.get("choice", "")).strip().upper()[:1]
            if choice == "F":
                votes[label].append(None)
                continue
            score = guardrail.ROUTE_LEVEL_SCORES.get(choice)
            if score is None:
                continue   # 알 수 없는 등급 — 버림
            quote = str(item.get("quote") or "")
            if not axis_scoring._quote_exists(quote, evidence_text):
                continue   # 근거 미실존 — 이 run 의 이 라벨 투표는 버림(환각 방지)
            votes[label].append(score)

    majority: dict[str, float] = {}
    for label, scores in votes.items():
        if not scores:
            continue
        score, _how = axis_scoring._majority(scores)
        if score is not None:
            majority[label] = score
    return guardrail.sanitize_route_familiarity(majority, targets)
