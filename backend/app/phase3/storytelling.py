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

## 템플릿과 LLM 의 관계 (2026-08-06 LLM 부착)
템플릿은 LLM 의 임시방편이 아니라 **영구적으로 필요한 경로**다. 골든타임에 LLM
지연·실패로 안내가 늦으면 최악이므로, 템플릿으로 즉시 내보내고 다듬은 문구는
다음 조회부터 교체한다(`guidance_with_refine`). 결정론적이라 테스트도 된다.

LLM 이 하는 일은 **어조뿐이다.** 페르소나를 주고 짓게 하지 않고 이미 검증을 통과한
문장을 주고 고쳐 쓰게 한다 — 그러면 없는 장소·시간을 지어낼 재료가 애초에 없다.
모델은 Mi:dm 2.0 Mini(근거: llm/copy_llm.py).

## 노출 범위
현재 소비처는 **수색 탭뿐**이다. 푸시 본문에는 넣지 않는다 — 잠금화면은 폰을 집어든
누구나 보고, 그 알림은 구 단위 수천 명에게 간다. 같은 문장이라도 노출 범위가 달라
최소성 심사 난이도가 달라진다(검토 결과 문서 참고).
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime

from app.schemas.case import Case
from app.schemas.persona import Persona

log = logging.getLogger(__name__)

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


def _states_and_places(params: ToneParams) -> tuple[list[str], list[str]]:
    """톤 파라미터 → (상태 문장들, 볼 곳들).

    조립(build_guidance)과 다듬기 검증(_kept_all_places)이 **같은 출처**를 봐야
    해서 뽑아 뒀다. 각자 계산하면 둘이 조용히 어긋난다.

    환경 반응이 여러 개면 **첫 하나만** 쓴다 — 지시를 여러 개 주면 시민이
    어디부터 갈지 못 정한다.
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

    return states, places[:MAX_PLACES]


def build_guidance(params: ToneParams) -> str:
    """톤 파라미터 → 수색 안내 문구.

    구조: [상태 문장들] + [볼 곳 한 문장]
    행동 경향이 가장 구체적인 지시라 앞에 온다.

    범위(spread)는 별도 문장이 아니라 **맺음말**로만 반영한다. 수색 탭에는 이미
    지도와 누적 확률이 있어 범위를 문장으로 또 말하면 중복이다.
    """
    states, places = _states_and_places(params)

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
        closing = "중심으로 넓게" if params.spread == "wide" else "먼저"
        text += f" {', '.join(places)}{_eul_reul(places[-1])} {closing} 살펴봐 주세요."
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
    """수색 안내 문구(템플릿) — 검증 실패 시 빈 문자열.

    안내가 없다고 수색 화면이 깨지면 안 되므로 예외를 밖으로 던지지 않는다.
    """
    params = to_tone_params(case, persona, now)
    text = build_guidance(params)
    try:
        validate(text, persona)
    except GuidanceRejected:
        return ""
    return text


# ── LLM 다듬기 ───────────────────────────────────────────────
#
# 템플릿 문구를 Mi:dm 2.0 Mini 가 한 번 더 다듬는다(2026-08-06). 왜 처음부터
# 짓게 하지 않고 다듬게만 하는지는 llm/copy_llm.py 의 refine() 주석 참고 —
# 요약하면 **모델에 지어낼 재료를 주지 않기 위해서**다.

#: case_id → 다듬은 문구. 실패했으면 템플릿 원문이 그대로 들어간다(재시도 안 함).
_refined: dict[str, str] = {}
#: 지금 다듬는 중인 case_id — 같은 사건에 스레드가 겹쳐 뜨지 않게.
_refining: set[str] = set()
_refine_lock = threading.Lock()


def _kept_all_places(text: str, places: list[str]) -> bool:
    """다듬은 문구가 볼 곳을 하나도 빠뜨리지 않았는가.

    🚨 검증기(validate)는 **덧붙임**만 본다 — 확정 표현, 진단명, 차단 필드 유출.
    그런데 다듬기의 실제 실패 양상은 반대쪽이었다: 요약하면서 장소를 조용히
    빠뜨린다(가짜 서버로 재현). 장소가 이 기능의 본체라 그건 문구가 예뻐지는 대신
    **기능이 사라지는** 것이다.

    부분 문자열로 보는 이유: 다듬으면서 "골목"이 "골목길"이 되는 건 괜찮고
    통과해야 한다. 반대 방향(줄여 쓰기)은 걸리는데, 볼 곳은 짧은 명사라 드물다.
    """
    return all(p in text for p in places)


def _refine_worker(case_id: str, baseline: str, persona: Persona | None,
                   persona_type: str | None, places: list[str]) -> None:
    """백그라운드 다듬기 1회. 결과가 검증을 통과할 때만 교체한다."""
    from app import llm

    try:
        text = llm.copy_llm.refine(baseline, persona_type)
        if not _kept_all_places(text, places):
            log.warning("[guidance] 다듬기가 볼 곳을 빠뜨림 (%s): %s", case_id, places)
            text = baseline
        try:
            validate(text, persona)
        except GuidanceRejected as e:
            # 🚨 실패를 삼키지 않고 남긴다 — 검증기가 계속 걸러내고 있으면
            # 프롬프트나 모델이 잘못된 것인데, 조용하면 "LLM 을 붙였는데 왜
            # 문구가 그대로지?"로만 보인다.
            log.warning("[guidance] 다듬기 거절 (%s): %s", case_id, e)
            text = baseline
    except Exception:  # noqa: BLE001 — 어떤 실패도 안내를 없애면 안 된다
        log.exception("[guidance] 다듬기 실패 (%s)", case_id)
        text = baseline
    with _refine_lock:
        # 🚨 다듬는 도중에 사건이 종결·파기됐으면 결과를 버린다.
        # clear_refined() 가 _refining 에서 뺐는데 여기서 그냥 쓰면, 인상착의가
        # 들어 있는 문구가 **파기 뒤에 되살아난다**(테스트가 잡은 실제 버그).
        if case_id not in _refining:
            return
        _refined[case_id] = text
        _refining.discard(case_id)


def guidance_with_refine(
    case: Case,
    persona: Persona | None = None,
    now: datetime | None = None,
) -> tuple[str, bool]:
    """수색 안내 문구 + **아직 다듬는 중인가**.

    ## 왜 기다리지 않는가
    골든타임에 LLM 응답을 기다리면 그동안 수색 탭이 비어 있다. 템플릿을 즉시
    돌려주고, 다듬은 문구는 다음 조회부터 나간다 — 안내가 늦는 것보다 한 번
    덜 다듬어져 나가는 편이 훨씬 낫다. 앱은 pending 이 True 인 동안만 다시 묻는다.

    ## 사건당 1회
    같은 사건의 문구는 한 번만 다듬는다. 실패해도 재시도하지 않는다 —
    엔드포인트가 죽어 있을 때 조회마다 스레드를 띄우면 그게 곧 부하다.

    @return (문구, pending). pending=True 면 더 나은 문구가 곧 준비된다.
    """
    baseline = guidance_for(case, persona, now)
    if not baseline:
        return "", False

    from app import llm

    if llm.copy_llm.is_stub:
        return baseline, False

    with _refine_lock:
        if case.id in _refined:
            return _refined[case.id], False
        if case.id in _refining:
            return baseline, True
        _refining.add(case.id)

    _, places = _states_and_places(to_tone_params(case, persona, now))
    threading.Thread(
        target=_refine_worker,
        args=(case.id, baseline, persona,
              persona.type.value if persona else None, places),
        name=f"guidance-refine-{case.id}",
        daemon=True,
    ).start()
    return baseline, True


def clear_refined(case_id: str) -> None:
    """사건 종결·파기 시 캐시 제거. 문구에는 인상착의가 들어 있어 사건과 함께 사라져야 한다.

    `_refining` 에서도 빼는 것이 중요하다 — 그게 진행 중인 다듬기에게 "결과를
    버려라"라고 알리는 신호다(_refine_worker 참고). 안 그러면 파기 직후에
    문구가 되살아난다.
    """
    with _refine_lock:
        _refined.pop(case_id, None)
        _refining.discard(case_id)
