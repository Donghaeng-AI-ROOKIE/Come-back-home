"""1인칭(당사자) 프레임 마음 프롬프트 — A/B 실험용 변형 (운영 미적용).

가설 (2026-07-29 골드셋 dev 실측에서 출발):
  분석가 프레임("이 사람이 어디로 갈까?")은 매 호출 그럴듯한 목적지를 고르는
  과합리와 confusion "중" 고정을 낳는다. 같은 정보를 당사자 프레임("너는 지금
  어디로 가는가?")으로 주면 null(비목표)·정지·혼란 변동이 문헌에 가깝게 나오는가.

설계 원칙:
  - 관찰 논문의 발견을 2인칭 행동 제약으로 번역해 system 에 고정 주입.
    목적지 클리셰(옛집·time-shift 예시)는 넣지 않는다 — B2 오염 재발 방지.
  - RAG 날 발췌는 마음 경로에서 제거(G02 침범 원인). prior 쪽은 그대로.
  - 출력은 기존 sanitize_mind 가 그대로 검증 — inner 필드는 결정 전에 독백을
    생성시키는 비계일 뿐, 시뮬레이션은 소비하지 않는다.
  - 후보 무작위 순서(B1)·근거 병기(B3)는 당사자 어휘로 번역해 유지한다.

적용: patch(exaone_module) 호출 — _mind_system_for/_build_mind_input/_rag_block 교체.
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
    PersonaType.intellectual_disability: """\
- 좋아하는 것이 눈에 들어오면 다른 생각이 안 나고 그쪽으로 끌린다.
- 시끄럽고 복잡한 곳은 견디기 힘들어 조용한 곳으로 피하고 싶다.
- 늘 하던 순서, 늘 가던 길이 편하고, 그게 깨지면 불안해진다.
- 낯선 사람이 말을 걸어도 대답하기 어렵다.""",
}

_FP_IDENTITY = {
    PersonaType.dementia: "치매가 있는 노인",
    PersonaType.intellectual_disability: "발달장애가 있는 사람",
}

_FP_RULES = """\
너는 지금 혼자 길에 나와 있는 {identity}이다. 아래는 네 마음의 성질이다. \
이 틀 안에서, 주어진 상황 속 너의 속마음을 그대로 낸다.
{traits}

출력 규칙:
- JSON 객체 하나만 출력한다. JSON 밖에 어떤 문장도 쓰지 않는다.
- inner: 지금 머릿속에 떠오르는 생각 1~2문장 (1인칭, 꾸미지 말 것)
- status: 지금 마음 상태 한 구절
- confusion_level: 지금 얼마나 혼란스러운가 "상"/"중"/"하"
- goal_label: 지금 발걸음이 실제로 향하는 곳 — [네가 아는 장소들] 목록의 라벨 \
원문 하나만. 딱히 향하는 데가 없거나 어디로 가야 할지 모르겠으면 null. \
목록에 없는 곳을 지어내지 않는다. 뒤에 붙은 주석(끌림·익숙함)은 제외한 라벨만 쓴다."""

# 게이지 보고(관찰자 문장) → 당사자 감각 문장
_GAUGE_FEEL = {
    "귀소": "갑자기 집에 가야겠다는 생각이 강하게 밀려온다.",
    "불안": "갑자기 불안이 확 밀려와 가만히 있기 어렵다.",
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


def _fp_system_for(ptype: PersonaType) -> str:
    return _FP_RULES.format(identity=_FP_IDENTITY.get(ptype, "사람"),
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


def build_fp_mind_input(
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
    lines.append("[질문] 지금 너는 어떤 마음이고, 발걸음은 어디로 향하는가? JSON 으로만 답하라.")
    return "\n".join(lines)


def patch(ex, keep_rag: bool = False) -> None:
    """app.llm.exaone 모듈에 1인칭 변형 적용 (프로세스 한정, 운영 코드 불변).

    기본은 _rag_block 도 비운다 — 1인칭 프레임에 논문 발췌는 이물질이고,
    G02 치명(문헌 지식이 케이스 근거 침범)의 원인 경로이기도 하다.
    keep_rag=True 는 그 가정 자체를 재는 대조 셀용(1인칭+RAG 궁합 실측).
    """
    ex._mind_system_for = _fp_system_for
    ex._build_mind_input = build_fp_mind_input
    if not keep_rag:
        ex._rag_block = lambda *a, **k: ""
