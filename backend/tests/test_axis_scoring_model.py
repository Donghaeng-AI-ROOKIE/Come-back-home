"""축 채점 전용 모델 분리 — 지식 주입 LoRA 가 축 채점을 망가뜨리는 문제 대응.

2026-07-28 골드셋 실측: exaone-sar 를 전역으로 쓰면 축 채점 정확일치가
0.88 → 0.74, κ_qw 0.96 → 0.86 으로 떨어졌다. JSON 파싱은 통과하므로
형식 검사로는 안 잡히고, 판단 품질을 따로 재야 드러난다.
"""


from app.config import settings
from app.llm.exaone import ExaoneClient
from app.phase0 import axis_scoring


def test_모델을_주면_그_모델로_호출한다():
    assert ExaoneClient(model="어떤모델").model == "어떤모델"


def test_안_주면_전역_설정을_따른다(monkeypatch):
    monkeypatch.setattr(settings, "exaone_model", "전역모델")
    assert ExaoneClient().model == "전역모델"


def test_축_채점은_전용_모델을_쓴다(monkeypatch):
    """운영 경로가 실제로 분리된 모델을 잡는지 — 설정만 있고 안 쓰면 의미가 없다."""
    monkeypatch.setattr(settings, "exaone_model", "파인튜닝본")
    monkeypatch.setattr(settings, "axis_scoring_model", "축채점용")
    monkeypatch.setattr(settings, "exaone_api_key", "k")
    monkeypatch.setattr(settings, "exaone_base_url", "http://x/v1")

    seen = {}

    class _Spy(ExaoneClient):
        def __init__(self, model=None):
            super().__init__(model)
            seen["model"] = self.model

        @property
        def is_stub(self):          # 실호출 없이 여기서 끊는다
            return True

    # 문자열 경로로 잡으면 app.llm.__init__ 이 같은 이름으로 내보내는 싱글턴
    # 인스턴스가 잡힌다. 모듈 객체를 직접 가져와 패치한다.
    import importlib
    monkeypatch.setattr(importlib.import_module("app.llm.exaone"),
                        "ExaoneClient", _Spy)

    from app.schemas.common import GeoPoint
    from app.schemas.persona import Persona, PersonaType
    p = Persona(id="p", name="n", type=PersonaType.dementia, age=80,
                home=GeoPoint(lat=37.6, lng=127.0))
    axis_scoring.score_axes_for(p)
    assert seen["model"] == "축채점용"


def test_전용_모델이_비어_있으면_전역을_쓴다(monkeypatch):
    """기존 배포(분리 안 한 상태)가 그대로 돌아야 한다 — 하위호환."""
    monkeypatch.setattr(settings, "exaone_model", "전역모델")
    monkeypatch.setattr(settings, "axis_scoring_model", "")
    assert ExaoneClient(model=settings.axis_scoring_model or None).model == "전역모델"
