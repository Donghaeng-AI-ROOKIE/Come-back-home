"""보호자 발화(behavior_notes) → 개인 환경 반응(EnvResponse).

PR #21 과제1 "페르소나 컴파일". 문제의식 원문:

    인터뷰에서 "물가만 보면 다가간다"를 받아도, 코드의 물끌림은 7세 미만 아동
    하드코딩이라 치매 노인의 물끌림 정보는 죽는다.

아동 제거(PR #47)로 그 하드코딩마저 사라져 water 는 envlayer 가 수집만 하고
소비처가 0건이 됐다. 이 컴파일러가 그 자리를 개인화된 형태로 채운다.

축(axis_scores)과의 역할 분담 — 겹치지 않는다:
- 축은 "얼마나" 반응하는가의 눈금 → 게이지 계수로 소비 (PR #55 스키마)
- 이 목록은 "무엇에" 반응하는가 → 이동 확률로 소비 (gauges.env_response_weight)
기준표 10축 어디에도 대상별 반응을 담는 자리가 없어 별도 경로가 필요하다.

장면 텍스트(PR #53)와도 층이 다르다: 저쪽은 마음 트리거 발동 시 LLM 이 맥락으로
해석하는 희소·비결정 경로, 이쪽은 온보딩 1회 컴파일 후 매 스텝 전 워커에
적용되는 알고리즘 경로다 (realism 무게중심 = 알고리즘 원칙).

신뢰도 확보는 axis_scoring·route_familiarity_compiler 와 통일한다:
quote 실존 검증 + runs 회 다수결 + 일시 장애 1회 재시도. LLM 은 닫힌 어휘의
등급만 내고 숫자는 코드가 매핑한다.
"""

from __future__ import annotations

import time

from app.config import settings
from app.phase0 import axis_scoring
from app.phase2 import guardrail
from app.schemas.persona import EnvResponse, Persona

_SYSTEM = """\
너는 실종자 수색(SAR) 행동 분석 전문가다. 보호자 발화에서, 대상자가 특정 환경 \
요소에 어떻게 반응하는지 판정한다.

[판정 대상] water(물가·하천·호수), forest(수풀·숲), park(공원), market(시장·상가)

[방향]
- 접근: 그 대상이 보이면 다가가거나 그쪽으로 가려 한다
- 회피: 그 대상을 피하거나 그쪽을 꺼린다

[강도]
- 상: 실제로 그 대상 때문에 이동하거나 발견된 적이 있다
- 중: 그런 반응을 자주 보인다고 보호자가 관찰했다
- 하: 그런 경향이 있다는 정도의 언급이다

출력 규칙:
- JSON 객체 하나만 출력한다. JSON 밖에 어떤 문장도 쓰지 않는다.
- 키는 water, forest, park, market 중에서만 고른다. 다른 대상을 지어내지 않는다.
- 값은 {"direction": "접근|회피", "strength": "상|중|하", "quote": "..."} 형식.
- quote: 판정의 핵심 근거인 보호자 발화를 입력에서 글자 그대로 옮겨 적는다.
- 발화에 반응이 드러나지 않은 대상은 아예 키를 넣지 마라(추측 금지).
- 판정 근거가 애매하면 그 대상은 빼라. 없는 반응을 만들어내는 것보다 낫다."""

_FEWSHOT_USER = """\
[보호자 발화]
- 물가만 보면 자꾸 다가가려고 하세요. 작년에도 개천 옆에서 발견됐어요.
- 사람 많은 시장은 질색하셔서 늘 돌아가세요.
- 아침에는 산책을 좋아하세요."""

_FEWSHOT_ASSISTANT = """\
{"water": {"direction": "접근", "strength": "상", "quote": "물가만 보면 자꾸 \
다가가려고 하세요. 작년에도 개천 옆에서 발견됐어요"}, "market": {"direction": \
"회피", "strength": "중", "quote": "사람 많은 시장은 질색하셔서 늘 돌아가세요"}}"""


def compile_env_responses(
    persona: Persona, client=None, runs: int | None = None,
) -> list[EnvResponse]:
    """behavior_notes 에서 개인 환경 반응을 컴파일.

    다음 경우 LLM 호출 없이 빈 리스트를 반환한다(호출 낭비 방지):
    - behavior_notes 가 비어 있음
    - client 가 스텁 모드(API 키 없음)

    실패해도 빈 리스트로 안전 폴백한다 — 소비처(env_response_weight)가
    빈 목록이면 중립 1.0 을 돌려주므로 예측이 도입 이전과 같아진다.
    """
    evidence_text = "\n".join(f"- {n}" for n in persona.behavior_notes)
    if not evidence_text:
        return []

    if client is None:
        from app.llm.exaone import ExaoneClient

        client = ExaoneClient()
    if getattr(client, "is_stub", False):
        return []

    runs = runs or settings.axis_scoring_runs
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _FEWSHOT_USER},
        {"role": "assistant", "content": _FEWSHOT_ASSISTANT},
        {"role": "user", "content": "[보호자 발화]\n" + evidence_text},
    ]

    # feature → [(direction, strength) | None] — 다수결 입력
    votes: dict[str, list] = {f: [] for f in guardrail.ENV_FEATURES}
    for _ in range(runs):
        raw = None
        for attempt in range(2):   # 일시 장애 1회 재시도 (axis_scoring 과 동일 원칙)
            try:
                raw = client.chat(messages, temperature=0.0, max_tokens=400,
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
        for feature, item in data.items():
            if feature not in votes or not isinstance(item, dict):
                continue   # 어휘 밖 대상(환각) 또는 형식 위반 — 버림
            direction = str(item.get("direction", "")).strip()
            score = guardrail.ENV_STRENGTH_SCORES.get(
                str(item.get("strength", "")).strip())
            if direction not in guardrail.ENV_DIRECTIONS or score is None:
                continue
            if not axis_scoring._quote_exists(str(item.get("quote") or ""), evidence_text):
                continue   # 근거 미실존 — 이 run 의 이 대상 투표는 버림(환각 방지)
            votes[feature].append((direction, score))

    # 다수결 — (방향, 강도) 쌍 단위. 방향이 갈리면 그 대상은 버린다(모순 판정).
    majority: dict[str, tuple[str, float]] = {}
    for feature, cast in votes.items():
        if not cast:
            continue
        directions = {d for d, _ in cast}
        if len(directions) > 1:
            continue   # 접근·회피가 섞임 — 근거가 불안정하다고 보고 채택하지 않음
        direction = directions.pop()
        score, _how = axis_scoring._majority([s for _, s in cast])
        if score is not None:
            majority[feature] = (direction, score)
    return guardrail.sanitize_env_responses(majority)
