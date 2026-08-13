"""보호자 발화(lost_behavior / dementia_wandering_pattern) → behavior_tendency.

두 행동 슬롯은 수집만 되고 Phase2가 안 읽던 미소비 데이터였다(2026-07-24 백로그).
이 컴파일러가 둘을 단일 신호 하나로 합쳐 guardrail.apply_axis_scores 의
strategy_probs 방향 틸트로 연결한다.

우선순위(dementia_wandering_pattern > lost_behavior): 과거 실종 때 실제 관찰된
행동(재현성 높은 사실)이 있으면 그걸 쓰고, 없을 때만 일반 경향(lost_behavior,
"길을 잃으면 보통" 질문)을 백업으로 쓴다 — slots.py:286 의 설계 의도 그대로.

dementia_wandering_pattern 근거에는 발견 장소 정보가 섞여 있지만, 장소는 이미
autobiographical_destination_pull(끌림점 경로)이 처리하므로 여기서는 행동
방향만 뽑고 장소는 버린다(역할 중복 회피) — few-shot 에 장소 문구를 quote로
잡지 않는 예시를 넣어 강제한다.

신뢰도 확보는 axis_scoring·route_familiarity_compiler 와 통일: quote 실존
검증 + runs 회 다수결 + 일시 장애 1회 재시도. "해당없음" 은 axis_scoring 의
F(판정 불가)와 같은 자리 — 표에서 버리지 않고 None 으로 투표에 포함시켜,
다수가 "해당없음"이면 진짜로 판정 불가라는 결론이 다수결에 반영되게 한다.
"""

from __future__ import annotations

import time

from app.config import settings
from app.phase0 import axis_scoring
from app.schemas.persona import Persona

# 닫힌 어휘 — LLM 이 지어낸 라벨은 여기 없으면 버려진다(환각 방지).
TENDENCY_LABELS = {"머무름": "stay", "이동": "move", "왕복": "backtrack", "은신": "hide"}

_SYSTEM = """\
너는 실종자 수색(SAR) 행동 분석 전문가다. 보호자 발화에서, 대상자가 길을 잃거나 \
배회할 때 실제로 보이는 행동 경향을 아래 분류 중 하나로 판정한다. \
장소·지명 정보는 무시하고 행동 자체만 본다.

[분류]
- 머무름: 제자리에 서 있거나 주저앉아 움직이지 않음
- 이동: 방향을 유지하며 계속 걸어감
- 왕복: 같은 구간을 반복해서 오가거나 되돌아감
- 은신: 몸을 숨기거나 안 보이는 곳으로 들어감

출력 규칙:
- JSON 객체 하나만 출력한다. JSON 밖에 어떤 문장도 쓰지 않는다.
- 값은 {"tendency": "머무름|이동|왕복|은신 중 하나", "quote": "..."} 형식.
- quote: 판정의 핵심 근거인 보호자 발화를 입력에서 글자 그대로 옮겨 적는다. \
행동을 설명하는 부분만 인용하고, 장소를 설명하는 부분은 인용하지 마라.
- 발화에 행동 경향이 전혀 드러나지 않으면 tendency 를 "해당없음"으로 하고 \
quote 는 빈 문자열로 한다.
- 장소 언급만 있고 행동 묘사가 없으면 "해당없음"으로 판정한다 \
(장소 정보는 다른 경로가 처리한다)."""

# 4개 라벨 각각 1개씩 — 예시를 하나만 주면(과거엔 "왕복"만 있었음) LLM 이 그 라벨로
# 쏠릴 위험이 있다(2026-07-26 셀프리뷰 지적). 라벨당 균등하게 노출한다.
_FEWSHOT_EXAMPLES = [
    (
        "[보호자 발화]\n예전에 한 번 길을 잃었을 때, 파출소에서 발견될 때까지 그 자리에 "
        "가만히 앉아만 계셨다고 들었습니다.",
        '{"tendency": "머무름", "quote": "그 자리에 가만히 앉아만 계셨다"}',
    ),
    (
        "[보호자 발화]\n집 근처에서 없어지신 뒤로 발견될 때까지 계속 같은 방향으로 "
        "걸어가고 계셨답니다.",
        '{"tendency": "이동", "quote": "계속 같은 방향으로 걸어가고 계셨답니다"}',
    ),
    (
        "[보호자 발화]\n두 번 모두 집에서 약 1km 떨어진 시장 근처에서 발견됐고, 주변을 "
        "계속 반복해서 걷고 있었습니다.",
        '{"tendency": "왕복", "quote": "주변을 계속 반복해서 걷고 있었습니다"}',
    ),
    (
        "[보호자 발화]\n실종 당시 건물 뒤편 구석에 몸을 숨기고 계신 걸 발견했다고 합니다.",
        '{"tendency": "은신", "quote": "몸을 숨기고 계신 걸 발견했다고 합니다"}',
    ),
]


def compile_behavior_tendency(
    persona: Persona, client=None, runs: int | None = None,
) -> str | None:
    """두 행동 슬롯 근거 → 단일 behavior_tendency. 우선순위: dementia_wandering > lost_behavior.

    다음 경우 LLM 호출 없이 None 을 반환한다(호출 낭비 방지):
    - 두 슬롯의 근거 발화(axis_quotes)가 모두 없음
    - client 가 스텁 모드(API 키 없음)
    """
    dementia_text = "\n".join(persona.axis_quotes.get("dementia_wandering_pattern", []))
    lost_text = "\n".join(persona.axis_quotes.get("lost_behavior", []))
    if not dementia_text and not lost_text:
        return None

    if client is None:
        from app.llm.exaone import ExaoneClient

        client = ExaoneClient()
    if getattr(client, "is_stub", False):
        return None

    runs = runs or settings.axis_scoring_runs
    if dementia_text:
        tendency = _classify(dementia_text, client, runs)
        if tendency is not None:
            return tendency
    if lost_text:
        return _classify(lost_text, client, runs)
    return None


def _classify(evidence_text: str, client, runs: int) -> str | None:
    """근거 텍스트 하나 → quote 검증·다수결을 거친 tendency (또는 판정 불가 None)."""
    messages = [{"role": "system", "content": _SYSTEM}]
    for user_turn, assistant_turn in _FEWSHOT_EXAMPLES:
        messages.append({"role": "user", "content": user_turn})
        messages.append({"role": "assistant", "content": assistant_turn})
    messages.append({"role": "user", "content": "[보호자 발화]\n" + evidence_text})

    votes: list[str | None] = []
    for _ in range(runs):
        raw = None
        # 일시 장애 1회 재시도 — axis_scoring 과 동일 원칙(run 유실 방지).
        for attempt in range(2):
            try:
                raw = client.chat(messages, temperature=0.0, max_tokens=200,
                                  enable_thinking=False)
                break
            except Exception:  # noqa: BLE001 — 재시도 후에도 실패하면 이 run 만 폐기
                if attempt == 0:
                    time.sleep(axis_scoring.RETRY_WAIT_S)
        if raw is None:
            continue
        data, _strict = axis_scoring._extract_json(raw)
        if not isinstance(data, dict):
            continue
        label = str(data.get("tendency", "")).strip()
        if label == "해당없음":
            votes.append(None)   # axis_scoring 의 F 처리와 동일 — 버리지 않고 투표에 포함
            continue
        tendency = TENDENCY_LABELS.get(label)
        if tendency is None:
            continue   # 어휘 밖 라벨(환각) — 버림
        quote = str(data.get("quote") or "")
        if not axis_scoring._quote_exists(quote, evidence_text):
            continue   # 근거 미실존 — 이 run 의 투표는 버림(환각 방지)
        votes.append(tendency)

    tendency, how = axis_scoring._majority(votes)
    # tendency 는 순서형이 아니라 명목형(어느 쪽이 "더 크다"는 의미가 없음)이라,
    # _majority 의 "다수결 불성립 — 중앙값" 폴백(정렬 후 가운데 값)은 axis_scoring
    # 의 등급(A~E, 실제 순서형)에서는 의미가 있지만 여기서는 알파벳 순서에 따른
    # 임의의 타이브레이크에 불과하다 — 그 경우는 그냥 판정 불가(None)로 처리한다.
    if how == "다수결 불성립 — 중앙값":
        return None
    return tendency
