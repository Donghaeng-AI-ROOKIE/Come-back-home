"""마음 재해석 1인칭 v2 계약 — 운영 정본 (2026-07-30 모델 확정으로 승격).

실험 모듈 `experiments/mind_goldset/first_person.py` 의 v2 빌더를 운영으로
옮긴 것. **문구 하나라도 달라지면 학습 형식 ≠ 서빙 형식이 되어 v5 어댑터
성능이 무효화된다** — tests/test_mind_v2_integration.py 가 실험 모듈과의
문자열 동일성을 회귀로 강제한다. 수정할 일이 생기면 실험 모듈과 함께 바꾸고
어댑터를 재학습·재게이트해야 한다.

확정 근거(전 과정): experiments/mind_tuning/결과_20260730_행동LoRA_게이트_8셀비교.md
- 어댑터 = **exaone-mind-dem3** (2026-08-04 치매 단독 재학습본으로 교체.
  봉인 test 144회: 행동 98%·목표 89%·혼란도 88%·치명 0·어휘 밖 0).
  종전 exaone-mind-v5 는 치매+발달장애 혼합 학습본이라 대상 축소와 함께 폐기.
  **이 계약 문구는 dem 계열도 그대로 물려받았다** — 여기를 고치면 dem3 도 무효다.
- RAG 는 마음 경로에서 제외 (형식 파괴·가짜 점수 실측)
- guided decoding 은 JSON 구조·필수 필드만 강제 (한글 enum 문법 강제 금지 —
  xgrammar 가 UTF-8 바이트 단위로 컴파일해 출력 분포가 붕괴한다)
"""
from __future__ import annotations

import random
import re

from app.schemas.persona import Persona, PersonaType
from app.schemas.prediction import PriorParams

# 관찰 문헌 → 2인칭 행동 제약 (유형별 고정). 장소를 암시하는 문장 금지.
_FP_TRAITS = {
    PersonaType.dementia: """\
- 오래전 기억은 생생하지만 방금 일은 잘 잊는다.
- 낯선 사람에게 먼저 도움을 청할 생각이 들지 않는다.
- 길이 막히거나 여기가 어디인지 모르면 되돌아가지 못하고 멈추거나 헤맨다.
- 늘 다니던 길, 익숙한 곳이 편하다.""",
}

_FP_IDENTITY = {
    PersonaType.dementia: "치매가 있는 노인",
}

# 계약 v2 — 목적지 대신 행동 의도를 1차 출력으로 (골드셋 v1.1 행동 라벨과 짝)
_FP_RULES_V2 = """\
너는 지금 혼자 길에 나와 있는 {identity}이다. 아래는 네 마음의 성질이다. \
이 틀 안에서, 주어진 상황 속 너의 속마음을 그대로 낸다.
{traits}

출력 규칙:
- JSON 객체 하나만 출력한다. JSON 밖에 어떤 문장도 쓰지 않는다.
- inner: 지금 머릿속에 떠오르는 생각 1~2문장 (1인칭, 꾸미지 말 것)
- status: 지금 마음 상태 한 구절
- confusion_level: 지금 얼마나 혼란스러운가 "상"/"중"/"하"
- behavior: 지금 몸이 실제로 하는 행동 — 반드시 다음 넷 중 하나의 원문:
  "끌림점 접근" (목록의 특정 장소로 향한다) / "귀소 시도" (오직 '집'으로 가려 \
한다 — 길을 못 찾아도 된다. 집이 아닌 익숙한 장소로 가는 것은 "끌림점 접근"이다) / \
"은신·멈춤" (숨거나 그 자리에 멈춘다) / "계속 배회" (딱히 갈 곳 없이 계속 걷는다)
- goal_label: behavior 가 "끌림점 접근"일 때만 [네가 아는 장소들] 목록의 라벨 \
원문 하나. 그 외 행동이면 반드시 null. 목록에 없는 곳을 지어내지 않는다."""

# 게이지 보고(관찰자 문장) → 당사자 감각 문장
_GAUGE_FEEL = {
    "귀소": "갑자기 집에 가야겠다는 생각이 강하게 밀려온다.",
    "불안": "갑자기 불안이 확 밀려온다.",
    "피로": "갑자기 다리에 힘이 빠지고 너무 지친다.",
    "혼란": "갑자기 여기가 어디인지 알 수 없어진다.",
}

# 근거 태그(관찰자 어휘) → 당사자 어휘. 정보량은 동일하게 유지한다.
_FP_EVIDENCE = {
    "previous_missing_found": "전에도 발길이 저절로 향했던 곳",
    "caregiver_report": "자주 가는 익숙한 곳",
    "mention_only": "이야기만 하던 곳",
}

_GRADE = {"상": "강함", "중": "보통", "하": "약함"}

# guided decoding — JSON 구조·필수 필드만 강제. 값 enum 은 넣지 않는다(위 주의).
GUIDED_JSON = {
    "type": "object",
    "properties": {
        "inner": {"type": "string"},
        "status": {"type": "string"},
        "confusion_level": {"type": "string"},
        "behavior": {"type": "string"},
        "goal_label": {"type": ["string", "null"]},
    },
    "required": ["inner", "status", "confusion_level", "behavior", "goal_label"],
}
REP_PENALTY = 1.05   # "집에 가고 싶다" 반복 루프 실측의 처방


def system_for(ptype: PersonaType) -> str:
    return _FP_RULES_V2.format(identity=_FP_IDENTITY.get(ptype, "사람"),
                               traits=_FP_TRAITS.get(ptype, ""))


def _translate_report(report: str) -> str:
    """표준 게이지 보고를 2인칭 감각 서술로 변환. 형식이 어긋나면 원문 유지."""
    out = report
    out = re.sub(r"집을 나선 지 (\d+)분 경과\.?", r"너는 집을 나선 지 \1분쯤 됐다.", out)
    out = re.sub(r"피로도: ([가-힣]+),?", r"몸의 피로는 \1,", out)
    out = re.sub(r"혼란도: ([가-힣]+),?", r"정신의 혼란은 \1,", out)
    out = re.sub(r"귀소 충동: ([가-힣]+),?", r"집에 가고 싶은 마음은 \1,", out)
    out = re.sub(r"불안: ([가-힣]+)\.?", r"불안은 \1이다.", out)
    m = re.search(r"방금 (\S+) 게이지가 임계를 넘었다", out)
    if m:
        feel = _GAUGE_FEEL.get(m.group(1), "")
        out = re.sub(r"방금 \S+ 게이지가 임계를 넘었다\.?", feel, out)
    return out


def build_input(
    persona: Persona,
    gauge_report: str,
    labels: list[str],
    prior: PriorParams | None = None,
    scene: str | None = None,
    rng: random.Random | None = None,
) -> str:
    lines = [f"[너는 이런 사람이다] (나이 {persona.age}세)"]
    lines += [f"- {note}" for note in (persona.behavior_notes or [])]
    lines.append(f"[지금 상황] {_translate_report(gauge_report)}")
    if scene:
        lines.append(f"[지금 눈앞에 보이는 것] {scene}")
    if labels:
        ev_by_label = {ap.label: ap.evidence for ap in persona.attraction_points}
        weights = (prior.attraction_weights or {}) if prior is not None else {}
        order = list(labels)
        (rng or random).shuffle(order)
        lines.append("[네가 아는 장소들] (나열 순서에 의미 없음)")
        for lb in order:
            parts = [lb]
            if lb in weights:
                w = weights[lb]
                g = "상" if w >= 0.45 else ("중" if w >= 0.25 else "하")
                parts.append(f"끌림 {_GRADE[g]}")
            ev = _FP_EVIDENCE.get(ev_by_label.get(lb, ""), None)
            if ev:
                parts.append(ev)
            lines.append("  - " + " — ".join(parts))
    else:
        lines.append("[네가 아는 장소들] (지금 떠오르는 곳이 없다)")
    lines.append("[질문] 지금 너는 어떤 마음이고, 몸은 어떻게 움직이는가? JSON 으로만 답하라.")
    return "\n".join(lines)
