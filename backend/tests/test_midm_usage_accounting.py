import json

import pytest

from app.config import settings
from app.llm.midm import MidmClient
from app.llm import usage_ledger


@pytest.mark.parametrize("fails", [False, True])
def test_operating_midm_records_success_and_failure_without_content(
    tmp_path, monkeypatch, caplog, fails
):
    ledger = tmp_path / "usage.jsonl"
    monkeypatch.setattr(settings, "research_usage_ledger_path", str(ledger))
    monkeypatch.setattr(settings, "midm_timeout", 12.0)
    monkeypatch.setattr(settings, "llm_timeout", 30.0)
    calls=[]
    client = MidmClient()
    client.api_key = "private-test-key"
    client.base_url = "https://invalid.test"
    client.model = "test-model"

    class Reply:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps(
                {
                    "choices": [{"message": {"content": "yes"}}],
                    "usage": {
                        "prompt_tokens": 11,
                        "completion_tokens": 1,
                        "total_tokens": 12,
                    },
                }
            ).encode()

    def request(*args, **kwargs):
        calls.append(kwargs)
        assert kwargs["timeout"] == 12.0
        if fails:
            raise TimeoutError("untrusted-provider-body")
        return Reply()

    monkeypatch.setattr(usage_ledger, "urlopen", request)
    if fails:
        with pytest.raises(TimeoutError):
            client.chat([{"role": "user", "content": "private-guardian-evidence"}])
    else:
        assert (
            client.chat([{"role": "user", "content": "private-guardian-evidence"}])
            == "yes"
        )
    assert len(calls)==1  # Mi:dm 2.5 diagnostics must not add a second transport request.
    assert "untrusted-provider-body" not in caplog.text
    if fails:
        assert "TimeoutError" in caplog.text
    text = ledger.read_text()
    assert "private-test-key" not in text and "private-guardian-evidence" not in text
    assert "untrusted-provider-body" not in text
    rows = [json.loads(line) for line in text.splitlines()]
    assert len(rows) == 2
    assert rows[0]["event_type"] == "api_attempt_started"
    assert rows[-1]["event_type"] == "api_attempt_finished"
    if not fails:
        assert rows[-1]["usage"]["total_tokens"] == 12


@pytest.mark.parametrize("endpoint", ["https://midm.kt.com", "https://midm.kt.com/v1", "https://midm.kt.com/v1/chat/completions"])
def test_kt_endpoint_normalization(endpoint):
    client=MidmClient()
    client.base_url=endpoint
    assert client._chat_url()=="https://midm.kt.com/v1/chat/completions"
