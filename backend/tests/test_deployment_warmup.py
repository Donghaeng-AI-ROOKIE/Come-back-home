"""A service restart must not call a model in isolated deployment checks."""
from app import llm
from app.config import settings
from app.main import _warm_exaone


def test_warmup_disabled_never_calls_configured_model(monkeypatch):
    class Live:
        is_stub = False

        def chat(self, *args, **kwargs):
            raise AssertionError('disabled startup performed inference')

    monkeypatch.setattr(settings, 'exaone_warmup_enabled', False)
    monkeypatch.setattr(llm, 'exaone', Live())
    _warm_exaone()
