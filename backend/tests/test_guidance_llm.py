"""수색 안내 문구 LLM 다듬기 — 다듬기가 안전 계약을 못 뚫는지.

템플릿판 검증은 test_storytelling.py. 여기는 **LLM 을 붙였을 때 새로 생기는
위험**만 본다:
  - 안내가 늦지 않는다 (템플릿 즉시, 다듬기는 나중)
  - 다듬은 문구도 같은 검증기를 통과해야만 쓰인다
  - 실패·스텁이면 조용히 템플릿으로 남는다
  - 사건당 1회 (죽은 엔드포인트에 조회마다 스레드를 띄우지 않는다)
"""

import threading
from datetime import datetime, timedelta

import pytest

from app import llm, storage
from app.llm.copy_llm import clean_line
from app.phase3 import storytelling
from app.privacy import lifecycle
from app.schemas.case import Case, CaseStatus, CloseReason
from app.schemas.common import GeoPoint
from app.schemas.persona import Persona, PersonaType
from app.schemas.report import Appearance, MissingReport

LKP = GeoPoint(lat=37.6061, lng=127.0106)
NOW = datetime(2026, 8, 5, 18, 0)

#: 다듬은 결과 예시 — **볼 곳(골목·벤치·건물 그늘)을 그대로 살린** 문장이어야 한다.
#: 빠뜨리면 _kept_all_places 가 되돌린다(test_dropped_place_falls_back_to_template).
#: 성공 경로를 테스트하려던 픽스처가 장소를 빼먹으면 조용히 폴백 경로를 재게 된다.
REFINED = "김순자 님은 가까운 골목이나 벤치, 건물 그늘에 머물러 계실 수 있어요."


def _case(cid: str = "c1") -> Case:
    report = MissingReport(
        id="r1", persona_id="p1", missing_type=PersonaType.dementia, lkp=LKP,
        lkp_time=NOW - timedelta(hours=2),
        appearance=Appearance(summary="회색 점퍼·검은 바지"),
    )
    return Case(
        id=cid, report=report, status=CaseStatus.searching,
        lkp=LKP, lkp_time=report.lkp_time,
        current_poa={f"cell{i}": 0.01 for i in range(100)},
    )


def _persona() -> Persona:
    return Persona(
        id="p1", type=PersonaType.dementia, name="김순자", age=78, home=LKP,
        behavior_tendency="stay",
    )


@pytest.fixture(autouse=True)
def _clean():
    storage.reset_for_tests()
    storytelling._refined.clear()
    storytelling._refining.clear()
    yield
    storage.reset_for_tests()
    storytelling._refined.clear()
    storytelling._refining.clear()


def _refine_with(monkeypatch, fn):
    """copy_llm 을 실동작으로 위장하고 refine 을 fn 으로 바꾼다.

    엔드포인트가 없어도(그리고 있어도) 테스트가 네트워크를 타지 않게 한다 —
    실호출을 섞으면 모델 응답에 따라 테스트가 흔들린다.
    """
    monkeypatch.setattr(type(llm.copy_llm), "is_stub", property(lambda self: False))
    monkeypatch.setattr(llm.copy_llm, "refine", fn)


def _settled(case, persona=None, timeout=5.0):
    """다듬기가 끝날 때까지 기다린 뒤 최종 문구. 백그라운드라 폴링해야 한다."""
    deadline = threading.Event()
    for _ in range(int(timeout * 100)):
        text, pending = storytelling.guidance_with_refine(case, persona)
        if not pending:
            return text
        deadline.wait(0.01)
    raise AssertionError("다듬기가 끝나지 않았다")


# ── 안내가 늦지 않는다 ───────────────────────────────────────


def test_first_call_returns_template_immediately(monkeypatch):
    """🚨 골든타임 계약 — LLM 을 기다리지 않는다.

    다듬기가 오래 걸려도 첫 응답은 즉시 나가야 한다. 여기서 블로킹하면
    수색 탭이 그동안 비어 있다.
    """
    started, release = threading.Event(), threading.Event()

    def slow(baseline, persona_type=None):
        started.set()
        # 스레드를 sleep 으로 묶어두면 테스트가 끝난 **뒤에** 캐시에 써서 다음
        # 테스트를 오염시킨다(실제로 그렇게 됐다). 테스트가 놓아줄 때 끝내게 한다.
        release.wait(5.0)
        return REFINED

    _refine_with(monkeypatch, slow)
    case, persona = _case(), _persona()
    try:
        text, pending = storytelling.guidance_with_refine(case, persona)

        assert text == storytelling.guidance_for(case, persona)  # 템플릿 원문
        assert pending is True
        assert started.wait(1.0), "백그라운드 다듬기가 시작되긴 해야 한다"
    finally:
        release.set()
        _settled(case, persona)  # 스레드가 캐시에 쓰는 것까지 보고 나간다


def test_refined_text_replaces_template(monkeypatch):
    _refine_with(monkeypatch, lambda b, p=None: REFINED)
    case, persona = _case(), _persona()

    assert _settled(case, persona) == REFINED


def test_pending_false_when_stub(monkeypatch):
    """스텁이면 다듬을 게 없으니 앱이 다시 물을 이유도 없다."""
    monkeypatch.setattr(type(llm.copy_llm), "is_stub", property(lambda self: True))
    case, persona = _case(), _persona()
    text, pending = storytelling.guidance_with_refine(case, persona)
    assert pending is False
    assert text == storytelling.guidance_for(case, persona)


# ── 다듬은 문구도 검증을 통과해야 한다 ──────────────────────


@pytest.mark.parametrize("bad", [
    "김순자 님은 정릉시장에 있습니다.",          # 확정 표현
    "치매가 있는 어르신을 찾고 있어요.",          # 진단명 노출
    "가" * 250,                                    # 길이 초과
])
def test_rejected_refinement_falls_back_to_template(monkeypatch, bad):
    """🚨 검증기가 LLM 판에도 그대로 걸린다.

    템플릿 시절 세워둔 방어선이 실제로 재사용되는지 확인한다 — 이게 뚫리면
    "프롬프트를 지켰는가"에 법적 방어선이 걸리게 된다.
    """
    _refine_with(monkeypatch, lambda b, p=None: bad)
    case, persona = _case(), _persona()
    baseline = storytelling.guidance_for(case, persona)

    assert _settled(case, persona) == baseline


def test_dropped_place_falls_back_to_template(monkeypatch):
    """🚨 다듬기의 진짜 실패 양상은 '덧붙임'이 아니라 '빠뜨림'이다.

    검증기는 확정 표현·진단명 같은 덧붙임만 본다. 요약하면서 볼 곳을 조용히
    빼면 문구는 예뻐지는데 **기능이 사라진다** — 장소가 이 안내의 본체다.
    (가짜 Mi:dm 서버로 실제 재현된 양상)
    """
    # 원문의 볼 곳은 골목·벤치·건물 그늘(stay 경향). 그중 둘만 남긴 응답.
    _refine_with(monkeypatch, lambda b, p=None: "김순자 님은 가까운 곳에 계실 수 있어요. 골목과 벤치를 살펴봐 주세요.")
    case, persona = _case(), _persona()
    baseline = storytelling.guidance_for(case, persona)

    assert _settled(case, persona) == baseline


def test_every_multiword_place_has_an_anchor():
    """🚨 여러 어절짜리 볼 곳은 닻이 있어야 한다.

    닻이 없으면 표기 전체를 찾는데, 다듬으면 조사가 끼거나("주변**의** 길목")
    수식어가 떨어져서("**최종** 목격 장소" → "목격 장소") 멀쩡한 문구가 거절된다.
    볼 곳을 새로 추가할 때 조용히 그 상태가 되는 걸 여기서 막는다.
    """
    all_places = {p for _, spots in storytelling._TENDENCY_HINT.values() for p in spots}
    all_places |= {p for _, spots in storytelling._ENV_HINT.values() for p in spots}

    for place in all_places:
        if len(place.split()) > 1:
            assert place in storytelling._PLACE_ANCHOR, f"닻 없는 복합 볼 곳: {place}"


def test_anchors_are_distinctive():
    """닻이 '주변'·'근처' 같은 일반어면 아무 문장이나 통과한다."""
    generic = {"주변", "근처", "사이", "아래", "곳", "쪽"}
    for place, anchor in storytelling._PLACE_ANCHOR.items():
        assert anchor not in generic, f"변별력 없는 닻: {place} → {anchor}"
        assert anchor in place, f"닻이 볼 곳에 없는 말: {place} → {anchor}"


def test_particle_and_modifier_drift_is_accepted():
    """실측에서 나온 실제 표현들 — 갈 곳은 그대로이므로 통과해야 한다."""
    places = ["최종 목격 장소 주변 길목", "공원 숲길", "산책로"]
    for text in [
        "최종 목격 장소 주변의 길목, 공원 숲길, 산책로를 넓게 살펴봐 주세요.",   # 조사 끼임
        "목격 장소 주변 길목, 공원 숲길, 산책로를 중심으로 살펴봐 주세요.",       # 수식어 탈락
    ]:
        assert storytelling._kept_essentials(text, places, needs_avoid=False), text

    # 진짜 누락은 여전히 걸려야 한다.
    dropped = "나무가 우거진 곳과 최종 목격 장소 주변을 중심으로 넓게 살펴봐 주세요."
    assert not storytelling._kept_essentials(dropped, places, needs_avoid=False)


def test_paraphrased_place_is_accepted(monkeypatch):
    """반대로 장소를 살린 채 늘려 쓴 것은 통과해야 한다 — 너무 빡빡하면 어떤
    다듬기도 못 통과해서 LLM 을 붙인 의미가 없어진다."""
    refined = "김순자 님은 가까운 곳에 계실 수 있어요. 골목길, 벤치, 건물 그늘진 곳을 먼저 살펴봐 주세요."
    _refine_with(monkeypatch, lambda b, p=None: refined)
    case, persona = _case(), _persona()

    assert _settled(case, persona) == refined


def test_llm_failure_falls_back_to_template(monkeypatch):
    def boom(baseline, persona_type=None):
        raise RuntimeError("엔드포인트 죽음")

    _refine_with(monkeypatch, boom)
    case, persona = _case(), _persona()
    baseline = storytelling.guidance_for(case, persona)

    assert _settled(case, persona) == baseline


def test_no_guidance_means_no_llm_call(monkeypatch):
    """템플릿이 빈 문자열이면 다듬을 것도 없다 — 빈 입력으로 호출하지 않는다."""
    calls = []
    _refine_with(monkeypatch, lambda b, p=None: calls.append(b) or "x")
    monkeypatch.setattr(storytelling, "guidance_for", lambda *a, **k: "")

    assert storytelling.guidance_with_refine(_case(), _persona()) == ("", False)
    assert calls == []


# ── 사건당 1회 ───────────────────────────────────────────────


def test_refines_once_per_case(monkeypatch):
    """🚨 조회마다 스레드를 띄우면 죽은 엔드포인트가 곧 부하가 된다."""
    calls = []

    def counting(baseline, persona_type=None):
        calls.append(baseline)
        return REFINED

    _refine_with(monkeypatch, counting)
    case, persona = _case(), _persona()
    _settled(case, persona)
    for _ in range(5):
        storytelling.guidance_with_refine(case, persona)

    assert len(calls) == 1


def test_failure_is_not_retried(monkeypatch):
    """실패도 캐시한다 — 재시도하면 엔드포인트가 죽은 동안 계속 두드린다."""
    calls = []

    def boom(baseline, persona_type=None):
        calls.append(baseline)
        raise RuntimeError("죽음")

    _refine_with(monkeypatch, boom)
    case, persona = _case(), _persona()
    _settled(case, persona)
    for _ in range(5):
        storytelling.guidance_with_refine(case, persona)

    assert len(calls) == 1


def test_cases_are_cached_separately(monkeypatch):
    _refine_with(monkeypatch, lambda b, p=None: f"[{b[:2]}] 다듬음")
    a, b = _case("ca"), _case("cb")
    persona = _persona()
    assert _settled(a, persona) == _settled(b, persona)  # 같은 입력 → 같은 결과
    assert set(storytelling._refined) == {"ca", "cb"}


# ── 파기 ─────────────────────────────────────────────────────


def test_closing_case_clears_refined(monkeypatch):
    """다듬은 문구에는 인상착의가 들어 있다 — 사건과 함께 사라져야 한다."""
    _refine_with(monkeypatch, lambda b, p=None: REFINED)
    case, persona = _case(), _persona()
    storage.cases.save(case.id, case)
    _settled(case, persona)
    assert case.id in storytelling._refined

    lifecycle.close_case(case, CloseReason.found)
    assert case.id not in storytelling._refined


def test_purging_case_clears_refined(monkeypatch):
    """종결을 거치지 않고 바로 파기되는 경로도 있다."""
    _refine_with(monkeypatch, lambda b, p=None: REFINED)
    case, persona = _case(), _persona()
    storage.cases.save(case.id, case)
    _settled(case, persona)

    lifecycle.purge_case(case, cause="test")
    assert case.id not in storytelling._refined


def test_refinement_in_flight_does_not_resurrect_after_purge(monkeypatch):
    """🚨 다듬는 **도중에** 파기되면 결과를 버려야 한다.

    안 버리면 인상착의가 들어 있는 문구가 파기 뒤에 캐시로 되살아난다.
    (테스트 격리 실패로 드러난 실제 버그 — 늦게 끝난 스레드가 지워진 캐시에 썼다)
    """
    started, release = threading.Event(), threading.Event()

    def slow(baseline, persona_type=None):
        started.set()
        release.wait(5.0)
        return REFINED

    _refine_with(monkeypatch, slow)
    case, persona = _case(), _persona()
    storage.cases.save(case.id, case)

    storytelling.guidance_with_refine(case, persona)   # 다듬기 시작
    assert started.wait(1.0)
    lifecycle.purge_case(case, cause="test")           # 진행 중에 파기
    release.set()

    for _ in range(500):
        if not storytelling._refining:
            break
        threading.Event().wait(0.01)
    assert case.id not in storytelling._refined, "파기된 사건의 문구가 되살아났다"


# ── 진단명을 모델에 주지 않는다 ──────────────────────────────


def test_condition_word_never_enters_the_prompt():
    """🚨 persona_type 은 입력 전용이지만, 그래도 "치매"라는 단어 자체를 모델에
    주지 않는다. 받은 적 없는 것은 샐 수 없다 — 검증기에만 기대지 않는다.

    검사 대상은 **페르소나에 따라 갈리는 부분(_TONE)뿐**이다. 고정 시스템 프롬프트는
    "질환·장애·진단명을 쓰지 않는다"라는 금지 지시를 담고 있어서 그 어휘가 나오는
    게 맞다 — 금지하려면 무엇을 금지하는지 말해야 한다.
    """
    # `from app.llm import copy_llm` 은 싱글턴 인스턴스를 준다(모듈명과 이름이 같다).
    # 모듈 상수를 보려면 전체 경로로 임포트해야 한다.
    from app.llm.copy_llm import _TONE, _TONE_DEFAULT

    persona_derived = "".join(_TONE.values()) + _TONE_DEFAULT
    for token in storytelling._FORBIDDEN_CONDITION:
        assert token not in persona_derived, f"어조 매핑에 질환·장애 어휘: {token}"


def test_tone_axis_exists_for_every_persona_type():
    """유형이 늘었는데 어조 매핑을 빠뜨리면 조용히 기본 어조로 떨어진다."""
    from app.llm.copy_llm import _TONE

    for ptype in PersonaType:
        assert ptype.value in _TONE, f"어조 매핑 없음: {ptype.value}"


# ── 출력 정리 ────────────────────────────────────────────────


@pytest.mark.parametrize("raw,expected", [
    ("다듬은 문구:  김순자 님은 가까이 계실 수 있어요.", "김순자 님은 가까이 계실 수 있어요."),
    ('"김순자 님은 가까이 계실 수 있어요."', "김순자 님은 가까이 계실 수 있어요."),
    ("김순자 님은 가까이 계실 수 있어요.\n\n설명: 어조를 부드럽게 했습니다.",
     "김순자 님은 가까이 계실 수 있어요."),
    ("", ""),
])
def test_clean_line_strips_wrapping(raw, expected):
    """모델이 머리말·따옴표를 붙이는 건 흔하다. 내용이 멀쩡한데 껍데기 때문에
    폴백하면 LLM 을 붙인 의미가 없다."""
    assert clean_line(raw) == expected


def test_clean_line_keeps_colon_inside_sentence():
    """문장 안의 콜론까지 머리말로 오인해 잘라내면 안 된다."""
    text = "지금 시각 기준: 최종 목격 장소 주변을 먼저 살펴봐 주세요."
    assert clean_line(text) == text


def test_refine_returns_baseline_when_stub():
    """스텁 클라이언트는 원문을 그대로 돌려준다(빈 문구를 만들지 않는다)."""
    from app.llm.copy_llm import CopyLLMClient

    client = CopyLLMClient()
    object.__setattr__(client, "api_key", "")  # 스텁 강제
    assert client.refine("원문이에요.", "dementia") == "원문이에요."
