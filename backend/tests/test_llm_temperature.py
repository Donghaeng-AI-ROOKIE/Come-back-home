"""LLM 호출 온도 — P1-3 실측으로 확정된 값이 코드 경로에 실제로 닿는지.

2026-07-30 실측(experiments/temp_sweep/결과_20260730_온도스윕.md):
정확도는 0.0~0.4 구간에서 평평했고(수집 2%p 차이), 같은 설정 재실행 노이즈가
6~7%p 로 그보다 3배 컸다. 반면 결정성은 또렷했다 — 같은 입력 5회 완전일치가
0.0 에서 100%, 0.4 에서 27%. 그래서 추출·구조화는 0.0 으로 고정한다.

이 테스트가 지키는 것은 두 가지다:
  (1) 확정값이 근거 없이 되돌아가지 않는 것 — 값을 바꾸려면 이 테스트를 고쳐야 하고,
      그때 위 문서를 다시 보게 된다.
  (2) 설정이 **실제 호출에 주입되는지** — 하드코딩을 설정으로 뺐으니, 설정만 있고
      호출부가 안 읽으면 스윕도 운영 확정도 전부 무의미해진다(axis_scoring_model 과 같은 함정).
"""

from app.config import settings
from app.llm.midm import MidmClient
from app.llm.tip_llm import TipLLMClient
from app.phase0.slots import SLOTS


def test_확정_온도_기본값():
    """추출·구조화 = 0.0(결정성), 질문 작문 = 0.4(전 구간 평평해 현행 유지)."""
    assert settings.midm_temp_extract == 0.0
    assert settings.midm_temp_correction == 0.0
    assert settings.tip_llm_temp_structure == 0.0
    assert settings.midm_temp_phrase == 0.4


def _spy_chat(client, monkeypatch, seen: dict):
    """chat() 을 가로채 온도만 기록하고 빈 응답 반환 — 실호출 없이 주입 경로만 본다."""
    def fake(messages, *, temperature, max_tokens=0, **kw):
        seen["temperature"] = temperature
        return "{}"
    monkeypatch.setattr(client, "chat", fake)


def test_추출_호출이_설정_온도를_쓴다(monkeypatch):
    monkeypatch.setattr(settings, "midm_api_key", "k")
    monkeypatch.setattr(settings, "midm_base_url", "http://x/v1")
    monkeypatch.setattr(settings, "midm_model", "m")
    monkeypatch.setattr(settings, "midm_temp_extract", 0.33)

    client = MidmClient()
    seen: dict = {}
    _spy_chat(client, monkeypatch, seen)

    slot = (SLOTS if isinstance(SLOTS, list) else list(SLOTS.values()))[0]
    client.extract_answer(slot, [{"role": "user", "text": "아무 말"}])
    assert seen["temperature"] == 0.33


def test_정정_호출이_설정_온도를_쓴다(monkeypatch):
    monkeypatch.setattr(settings, "midm_api_key", "k")
    monkeypatch.setattr(settings, "midm_base_url", "http://x/v1")
    monkeypatch.setattr(settings, "midm_model", "m")
    monkeypatch.setattr(settings, "midm_temp_correction", 0.44)

    client = MidmClient()
    seen: dict = {}
    _spy_chat(client, monkeypatch, seen)

    client.extract_correction(["어떤장소"], "빼주세요")
    assert seen["temperature"] == 0.44


def test_질문_작문이_설정_온도를_쓴다(monkeypatch):
    from app.schemas.persona import PersonaType

    monkeypatch.setattr(settings, "midm_api_key", "k")
    monkeypatch.setattr(settings, "midm_base_url", "http://x/v1")
    monkeypatch.setattr(settings, "midm_model", "m")
    monkeypatch.setattr(settings, "midm_temp_phrase", 0.55)

    client = MidmClient()
    seen: dict = {}
    _spy_chat(client, monkeypatch, seen)

    slot = (SLOTS if isinstance(SLOTS, list) else list(SLOTS.values()))[0]
    client.phrase_question(PersonaType.dementia, slot, False, [])
    assert seen["temperature"] == 0.55


def test_제보_구조화가_설정_온도를_쓴다(monkeypatch):
    monkeypatch.setattr(settings, "tip_llm_api_key", "k")
    monkeypatch.setattr(settings, "tip_llm_base_url", "http://x/v1")
    monkeypatch.setattr(settings, "tip_llm_model", "m")
    monkeypatch.setattr(settings, "tip_llm_temp_structure", 0.22)

    client = TipLLMClient()
    seen: dict = {}
    _spy_chat(client, monkeypatch, seen)

    client.structure_tip("방금 편의점 앞에서 봤어요")
    assert seen["temperature"] == 0.22
