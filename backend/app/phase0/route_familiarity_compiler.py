"""보호자 발화 → autobiographical_destination_pull 유래 끌림점별 route_familiarity 점수.

routine_destinations 유래 끌림점은 컴파일 대상에서 제외한다 — 작업4(unfamiliarity
게이지 재배치)에서 기본값 "높음"(gauges.ROUTINE_DEFAULT_FAMILIARITY=0.8)으로 이미
처리되므로 중복 채점이 불필요하다.

"list 출력" 패턴 — 기존 prior/mind 프롬프트가 "선택지 하나"만 받던 것과 다르게,
닫힌 후보 목록(끌림점 라벨) 각각에 A~E 등급을 매기는 형태로 설계한다
(goal_label 의 "실존 라벨만 인정" 가드레일 패턴을 리스트로 확장한 것). 등급 스케일은
axis_scoring 의 CHOICE_SCORE(A=0.1~E=0.9)와 동일 — 팀 확정 기준표(2026-07-20).

axis_scoring 과 달리 다수결(runs 회 반복)은 하지 않는다 — 이 컴파일러는 quote 검증도
없는 단발 호출이라, 다수결로 얻을 신뢰도 개선보다 재시도 비용이 더 크다고 판단했다.
실패 시 그냥 빈 리스트로 폴백해 unfamiliarity() 의 거리 기반 근사가 대신한다.
"""

from __future__ import annotations

import json

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
- 발화에 전혀 언급이 없는 장소는 아예 키를 넣지 마라(추측 금지).
- 값은 "A"~"F" 중 하나."""

_FEWSHOT_USER = """\
[장소 후보] 옛 직장(방직공장), 예전 살던 동네
[보호자 발화] "예전에 방직공장 다니던 길은 아직도 기억하시는지 가끔 그쪽으로 걸어가려고 하세요. \
예전 살던 동네는 재개발돼서 지금은 완전히 다른 곳이 됐는데도 가끔 거기 얘기를 하세요.\""""

_FEWSHOT_ASSISTANT = """\
{"옛 직장(방직공장)": "D", "예전 살던 동네": "A"}"""


def compile_route_familiarity(persona: Persona, client=None) -> list[RouteFamiliarity]:
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

    labels = [ap.label for ap in targets]
    prompt = "[장소 후보] " + ", ".join(labels) + "\n[보호자 발화] " + evidence_text
    try:
        raw = client.chat(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _FEWSHOT_USER},
                {"role": "assistant", "content": _FEWSHOT_ASSISTANT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=300,
            enable_thinking=False,
        )
        data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except Exception:  # noqa: BLE001 — 호출·파싱 실패는 빈 리스트로 폴백(거리근사에 위임)
        return []
    return guardrail.sanitize_route_familiarity(data, targets)
