"""수색 안내 문구 — 페르소나별로 "어디를 봐야 하는지"를 다르게 말한다.

## 판정 기준
검토 결론의 실무 테스트 한 문장이 이 모듈 전체의 기준이다.

    이 문장을 빼면 시민이 다른 곳을 보게 되는가?

    "물가 쪽으로 향하셨을 가능성, 하천변을 봐주세요"  → ✅ 수색 지시
    "물가를 좋아하세요"                                 → ❌ 앞 문장이 이미 그 역할

같은 정보라도 **수색 지시로 쓰면 통과하고 인물 묘사로 쓰면 안 된다.**
개인정보보호법 제18조2항(급박한 생명·신체 이익)이 근거인데, 그 근거는 목적에
기여하는 범위까지만 정당화한다 — 기여하지 않는 노출은 최소성 심사를 통과하지 못한다.

## 제약을 프롬프트가 아니라 입력에 건다
`to_tone_params()` 가 유일한 관문이고, 여기서 **닫힌 어휘 필드만** 통과시킨다.
자유 텍스트(behavior_notes·axis_quotes 등)는 아예 이 아래로 내려오지 않는다.
받은 적 없는 것은 샐 수 없다 — 나중에 LLM 을 붙일 때도 같은 관문을 쓰므로,
법적 방어선이 "모델이 지시를 지켰는가"에 걸리지 않는다.

## 왜 템플릿인가 (LLM 이전에)
LLM 판의 임시방편이 아니라 **영구적으로 필요한 경로**다. 골든타임에 LLM 지연·실패로
안내가 늦으면 최악이므로 실서비스에서도 템플릿으로 즉시 내보내고 LLM 문구는 나중에
교체한다. 결정론적이라 테스트도 된다.

## 노출 범위
현재 소비처는 **수색 탭뿐**이다. 푸시 본문에는 넣지 않는다 — 잠금화면은 폰을 집어든
누구나 보고, 그 알림은 구 단위 수천 명에게 간다. 같은 문장이라도 노출 범위가 달라
최소성 심사 난이도가 달라진다(검토 결과 문서 참고).
"""

from dataclasses import dataclass, field
from datetime import datetime

from app.schemas.case import Case
from app.schemas.persona import Persona

# ── 닫힌 어휘 ────────────────────────────────────────────────

# 각 항목은 (상태 문장, 볼 장소들)로 쪼개 둔다. 완성된 문장으로 두면 여러 개를
# 붙였을 때 "살펴봐 주세요"가 두세 번 반복되고 장소가 중복된다("정류장 주변"이
# 경향과 범위 안내 양쪽에 나오던 문제). 상태는 이어 말하고 장소는 한 번에 모아
# 말하는 게 한국어로도 자연스럽고 짧다.

#: 행동 경향 → (상태, 볼 곳). behavior_compiler 가 채우는 4종 + None.
_TENDENCY_HINT: dict[str, tuple[str, list[str]]] = {
    "stay": ("멀리 가지 못하고 한자리에 머물러 계실 수 있어요", ["골목", "벤치", "건물 그늘"]),
    "move": ("쉬지 않고 걷고 계실 수 있어요", ["큰길", "정류장 주변"]),
    "backtrack": ("왔던 길을 되짚어 걷고 계실 수 있어요", ["최종 목격 장소 주변 길목"]),
    "hide": ("사람 눈에 잘 띄지 않는 곳에 계실 수 있어요", ["건물 사이", "주차장", "계단 아래"]),
}

#: 환경 반응 → (상태, 볼 곳). envlayer 카테고리 4종 × 접근/회피.
#: 회피도 지시로 유효하다 — 시민이 볼 곳을 바꾸게 하므로. 다만 "가지 말라"는
#: 장소를 볼 곳 목록에 넣을 수는 없으므로 상태 문장만 남는다.
_ENV_HINT: dict[tuple[str, str], tuple[str, list[str]]] = {
    ("water", "접근"): ("물가 쪽으로 향하셨을 가능성이 있어요", ["하천변", "다리 근처"]),
    ("water", "회피"): ("물가 쪽은 피하셨을 가능성이 있어요", []),
    ("forest", "접근"): ("나무가 우거진 곳으로 향하셨을 가능성이 있어요", ["공원 숲길", "산책로"]),
    ("forest", "회피"): ("숲이나 어두운 산책로는 피하셨을 가능성이 있어요", []),
    ("park", "접근"): ("공원 쪽으로 향하셨을 가능성이 있어요", ["공원 벤치", "정자 주변"]),
    ("park", "회피"): ("공원처럼 트인 곳은 피하셨을 가능성이 있어요", []),
    ("market", "접근"): ("사람이 많은 곳으로 향하셨을 가능성이 있어요", ["시장", "상가 주변"]),
    ("market", "회피"): ("번잡한 시장이나 상가는 피하셨을 가능성이 있어요", []),
}

#: 볼 곳 상한. 넷 이상 나열하면 어디부터 갈지 못 정한다.
MAX_PLACES = 3

#: 경과시간 구간 → 범위 안내. 페르소나가 없어도 쓸 수 있는 유일한 축.
_ELAPSED_HINT = (
    (2.0, "아직 멀리 가지 못하셨을 거예요. 최종 목격 장소에서 걸어서 10분 안쪽을 먼저 봐주세요."),
    (6.0, "시간이 지나 이동 범위가 넓어졌어요."),
    (float("inf"), "시간이 많이 지나 이동 범위가 상당히 넓어졌어요. 큰길과 정류장 주변도 함께 봐주세요."),
)

#: POA 셀 수가 이보다 많으면 "넓게 퍼짐". 검토안 실측(경과 1h ≈ 159셀) 기준으로 잡은 잠정값.
WIDE_SPREAD_CELLS = 300


@dataclass
class ToneParams:
    """LLM·템플릿이 볼 수 있는 **전부**. 이 dataclass 밖의 것은 내려오지 않는다.

    자유 텍스트 필드가 하나도 없다는 점이 핵심이다 — 필드를 추가할 때는
    "닫힌 어휘인가"를 먼저 물어야 한다.
    """

    #: 어조 축. **입력 전용 — 결과 문장에 드러나면 안 된다**(제23조 민감정보).
    persona_type: str | None = None
    #: 실명. **노출 허용 항목**이다 — 경찰 실종경보가 이미 실명을 공개하고 있어
    #: 베이스라인이 "공개"이고, 무엇보다 **호명하면 반응할 수 있어** 수색에 실질
    #: 기여를 한다("이 문장을 빼면 시민이 다른 곳을 보게 되는가" 테스트 통과).
    #: 진단명(cognition)과는 성격이 다르다 — 그쪽은 불러도 수색이 안 바뀐다.
    name: str | None = None
    tendency: str | None = None
    #: (feature, direction) 쌍. 닫힌 어휘라 가드레일이 지어낸 값을 버린다.
    env: list[tuple[str, str]] = field(default_factory=list)
    elapsed_h: float = 0.0
    spread: str = "narrow"  # narrow | wide
    #: 이미 시민 노출이 승인된 항목(인상착의 요약).
    appearance: str = ""


def to_tone_params(
    case: Case,
    persona: Persona | None = None,
    now: datetime | None = None,
) -> ToneParams:
    """페르소나·사건 → 톤 파라미터. **자유 텍스트는 여기서 전부 탈락한다.**

    통과: type(입력 전용) / behavior_tendency / env_responses(feature·direction) /
          경과시간 / POA 집중도 / 인상착의 요약
    차단: name · home · behavior_notes · attraction_points.label ·
          axis_quotes · axis_evidence · axis_scores
    """
    now = now or datetime.now()
    elapsed_h = max(0.0, (now - case.lkp_time).total_seconds() / 3600)
    spread = "wide" if len(case.current_poa or {}) > WIDE_SPREAD_CELLS else "narrow"
    appearance = case.report.appearance.summary if case.report.appearance else ""

    if persona is None:
        return ToneParams(elapsed_h=round(elapsed_h, 1), spread=spread, appearance=appearance)

    return ToneParams(
        persona_type=persona.type.value,
        name=persona.name or None,
        tendency=persona.behavior_tendency,
        # strength 는 넘기지 않는다 — 0.1~0.9 연속값이라 닫힌 어휘가 아니고,
        # 문구를 가르는 데도 쓰이지 않는다.
        env=[(e.feature, e.direction) for e in persona.env_responses],
        elapsed_h=round(elapsed_h, 1),
        spread=spread,
        appearance=appearance,
    )


def _elapsed_hint(elapsed_h: float) -> str:
    for upper, hint in _ELAPSED_HINT:
        if elapsed_h < upper:
            return hint
    return _ELAPSED_HINT[-1][1]


def _eul_reul(word: str) -> str:
    """목적격 조사 — "골목를"처럼 어색해지지 않도록 받침으로 고른다."""
    last = word[-1]
    if not ("가" <= last <= "힣"):
        return "를"
    return "을" if (ord(last) - 0xAC00) % 28 else "를"


def build_guidance(params: ToneParams) -> str:
    """톤 파라미터 → 수색 안내 문구.

    구조: [상태 문장들] + [볼 곳 한 문장]
    행동 경향이 가장 구체적인 지시라 앞에 온다. 환경 반응이 여러 개면 **첫
    하나만** 쓴다 — 지시를 여러 개 주면 시민이 어디부터 갈지 못 정한다.

    범위(spread)는 별도 문장이 아니라 **맺음말**로만 반영한다. 수색 탭에는 이미
    지도와 누적 확률이 있어 범위를 문장으로 또 말하면 중복이다.
    """
    states: list[str] = []
    places: list[str] = []

    if params.tendency in _TENDENCY_HINT:
        state, spots = _TENDENCY_HINT[params.tendency]
        states.append(state)
        places.extend(spots)

    for feature, direction in params.env:
        hint = _ENV_HINT.get((feature, direction))
        if hint:
            state, spots = hint
            states.append(state)
            places.extend(spots)
            break

    # 경향·환경이 하나도 없으면 경과시간만으로라도 방향을 준다.
    if not states:
        return _elapsed_hint(params.elapsed_h)

    # 실명을 첫 상태 문장의 주어로 세운다. 이름이 있으면 시민이 불러볼 수 있고,
    # 그게 이름을 노출하는 근거다 — 장식이 아니라 수색 도구.
    # "님"은 항상 "은"을 받으므로 조사 계산이 필요 없다.
    if params.name:
        states[0] = f"{params.name} 님은 {states[0]}"

    # 상태 문장들은 각각 종결어미로 끝나므로 마침표로 이어야 한다
    # (공백으로만 이으면 "있어요 물가 쪽으로…" 처럼 한 문장으로 읽힌다).
    text = ". ".join(states) + "."
    if places:
        picked = places[:MAX_PLACES]
        closing = "중심으로 넓게" if params.spread == "wide" else "먼저"
        text += f" {', '.join(picked)}{_eul_reul(picked[-1])} {closing} 살펴봐 주세요."
    return text


# ── 출력 검증 ────────────────────────────────────────────────

#: 확률분포를 확정으로 말하는 표현. 한 번 틀린 확정 표현이 나가면 이후 모든
#: 안내의 신뢰가 같이 떨어진다.
_FORBIDDEN_CERTAINTY = ("에 있습니다", "에 있어요", "임이 확실", "분명히", "틀림없")

#: 질환·장애가 문장에서 추론되면 안 된다(제23조 민감정보). 수색에는 진단명이
#: 필요 없다 — "길을 찾지 못하고 계세요"면 행동 지침으로 충분하다.
_FORBIDDEN_CONDITION = ("치매", "발달장애", "지적장애", "인지저하", "질환", "장애를")


class GuidanceRejected(Exception):
    """검증 실패 — 호출부는 안내 없이(또는 폴백으로) 진행한다."""


def validate(text: str, persona: Persona | None = None, max_len: int = 200) -> None:
    """생성 문구 검증. 템플릿이라 지금은 통과가 당연하지만, **LLM 판이 붙을 때
    그대로 재사용할 방어선**이라 미리 세워둔다.

    n-gram 대조는 심층 방어다 — 자유 텍스트를 애초에 안 넘기므로 나올 리 없지만,
    관문이 뚫렸을 때 마지막으로 걸린다.
    """
    if len(text) > max_len:
        raise GuidanceRejected(f"너무 김: {len(text)}자 > {max_len}")

    for token in _FORBIDDEN_CERTAINTY:
        if token in text:
            raise GuidanceRejected(f"확정 표현: {token}")

    for token in _FORBIDDEN_CONDITION:
        if token in text:
            raise GuidanceRejected(f"질환·장애 노출: {token}")

    if persona is None:
        return

    # 실명은 검사하지 않는다 — 노출 허용 항목이다(ToneParams.name 주석 참고).
    # 진단명과 달리 호명이 수색 행동을 바꾸고, 경찰 실종경보가 이미 공개한다.

    # 차단 필드의 어절이 생성문에 나타나면 관문이 뚫린 것이다.
    leaked_sources: list[str] = list(persona.behavior_notes)
    for quotes in persona.axis_quotes.values():
        leaked_sources.extend(quotes)
    for evidences in persona.axis_evidence.values():
        leaked_sources.extend(evidences)
    for point in persona.attraction_points:
        leaked_sources.append(point.label)

    for source in leaked_sources:
        for word in source.split():
            # 2자 이하는 조사·일반어와 충돌해 오탐이 난다.
            if len(word) > 2 and word in text:
                raise GuidanceRejected(f"차단 필드 어절 노출: {word}")


def guidance_for(
    case: Case,
    persona: Persona | None = None,
    now: datetime | None = None,
) -> str:
    """수색 안내 문구 — 외부 진입점. 검증 실패 시 빈 문자열.

    안내가 없다고 수색 화면이 깨지면 안 되므로 예외를 밖으로 던지지 않는다.
    """
    params = to_tone_params(case, persona, now)
    text = build_guidance(params)
    try:
        validate(text, persona)
    except GuidanceRejected:
        return ""
    return text
