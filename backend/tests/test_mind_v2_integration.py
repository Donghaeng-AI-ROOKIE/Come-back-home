"""마음 재해석 1인칭 v2 통합 — 학습 형식=서빙 형식 드리프트 가드 + 경로 검증.

v5 어댑터는 experiments/mind_goldset/first_person.py 의 v2 빌더 출력으로
학습됐다. 운영 정본(app/llm/mind_v2.py)이 그 문구에서 한 글자라도 어긋나면
어댑터 성능 실측(행동 95%·goal 100%)이 무효가 되므로, 두 모듈의 출력
동일성을 회귀로 강제한다.
"""
from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path

from app.config import settings
from app.llm import mind_v2
from app.llm.exaone import ExaoneClient, _fix_mojibake
from app.phase2.guardrail import sanitize_mind
from app.schemas.common import GeoPoint
from app.schemas.persona import AttractionPoint, Persona, PersonaType
from app.schemas.prediction import LognormalParams, MindState, PriorParams

_GOLDSET = Path(__file__).parents[1] / "experiments" / "mind_goldset"


def _load_experiment_module():
    sys.path.insert(0, str(_GOLDSET))  # first_person 이 없는 환경 대비 절대 로드
    spec = importlib.util.spec_from_file_location("_fp_exp", _GOLDSET / "first_person.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _persona() -> Persona:
    return Persona(
        id="t", name="t", age=78, type=PersonaType.dementia,
        home=GeoPoint(lat=37.55, lng=127.0),
        attraction_points=[
            AttractionPoint(label="시장", location=GeoPoint(lat=37.55, lng=127.0),
                            weight=0.9, evidence="previous_missing_found"),
            AttractionPoint(label="약국", location=GeoPoint(lat=37.55, lng=127.0),
                            weight=0.3, evidence="mention_only"),
        ],
        behavior_notes=["과거 두 차례 시장에서 발견됐다."],
    )


def _prior() -> PriorParams:
    return PriorParams(strategy_probs={"route_following": 1.0},
                       attraction_weights={"시장": 0.7, "약국": 0.3},
                       radius_lognormal=LognormalParams(mu=0.1, sigma=1.5))


REPORT = ("집을 나선 지 90분 경과. 피로도: 중간, 혼란도: 중간, 귀소 충동: 높음, "
          "불안: 낮음. 방금 귀소 게이지가 임계를 넘었다.")


def test_v2_builders_identical_to_experiment_module():
    """운영 mind_v2 == 실험 first_person(v2 계약) — 시스템·입력 문자열 완전 일치."""
    fp = _load_experiment_module()
    fp._CONTRACT = "v2"
    for ptype in PersonaType:
        assert mind_v2.system_for(ptype) == fp._fp_system_v2_for(ptype)
    ops = mind_v2.build_input(_persona(), REPORT, ["시장", "약국"], _prior(),
                              scene="골목 입구의 빨간 우체통", rng=random.Random(7))
    exp = fp.build_fp_mind_input(_persona(), REPORT, ["시장", "약국"], _prior(),
                                 scene="골목 입구의 빨간 우체통", rng=random.Random(7))
    assert ops == exp


def test_reinterpret_mind_v2_routes_model_and_guided(monkeypatch):
    """v2 계약: mind 전용 모델명·guided 스키마·RAG 미주입이 실제 호출에 반영된다."""
    monkeypatch.setattr(settings, "mind_contract", "v2")
    monkeypatch.setattr(settings, "mind_model", "exaone-mind-v5")
    live = ExaoneClient()
    live.api_key, live.base_url, live.model = "k", "https://x", "exaone-base"
    captured = {}

    def fake_chat(messages, **kwargs):
        captured["messages"] = messages
        captured.update(kwargs)
        return ('{"inner": "시장 쪽이 익숙하다.", "status": "이동", '
                '"confusion_level": "중", "behavior": "끌림점 접근", "goal_label": "시장"}')

    monkeypatch.setattr(live, "chat", fake_chat)
    mind, goal = live.reinterpret_mind(_persona(), MindState(), REPORT, ["시장", "약국"], _prior())
    assert captured["model"] == "exaone-mind-v5"
    assert captured["guided_json"] == mind_v2.GUIDED_JSON
    assert captured["repetition_penalty"] == mind_v2.REP_PENALTY
    assert len(captured["messages"]) == 2          # system+user — RAG 턴 없음
    assert "[네가 아는 장소들]" in captured["messages"][-1]["content"]
    assert goal == "시장" and mind.confusion == 0.6


def test_reinterpret_mind_v1_rollback_path(monkeypatch):
    """mind_contract=v1 이면 종전 분석가 경로 그대로 (모델 오버라이드 없음)."""
    monkeypatch.setattr(settings, "mind_contract", "v1")
    live = ExaoneClient()
    live.api_key, live.base_url, live.model = "k", "https://x", "exaone-base"
    captured = {}

    def fake_chat(messages, **kwargs):
        captured.update(kwargs)
        return '{"status": "이동 중", "confusion_level": "중", "goal_label": null}'

    monkeypatch.setattr(live, "chat", fake_chat)
    live.reinterpret_mind(_persona(), MindState(), REPORT, ["시장"], _prior())
    assert captured["model"] is None
    assert captured["guided_json"] is None


def test_sanitize_ignores_v2_extra_fields_and_maps_levels():
    """v2 출력의 여분 키(inner/behavior)는 무시, 하/중/상 → 숫자 매핑."""
    cur = MindState(confusion=0.5)
    mind, goal = sanitize_mind(
        {"inner": "…", "behavior": "계속 배회", "status": "배회",
         "confusion_level": "하", "goal_label": None}, cur, ["시장"])
    assert mind.confusion == 0.35 and goal is None


def test_fix_mojibake_repairs_byte_escapes_only():
    """xgrammar 바이트 이스케이프만 복원 — 정상 한글·None 은 무변경."""
    broken = "귀소 시도".encode("utf-8").decode("latin-1")
    assert _fix_mojibake(broken) == "귀소 시도"
    assert _fix_mojibake("끌림점 접근") == "끌림점 접근"
    assert _fix_mojibake(None) is None
