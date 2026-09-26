import json

import pytest

from app.config import settings
from app.llm.midm import MidmClient
from app.llm import usage_ledger


@pytest.mark.parametrize("fails", [False, True])
def test_operating_midm_records_success_and_failure_without_content(
    tmp_path, monkeypatch, fails
):
    ledger = tmp_path / "usage.jsonl"
    monkeypatch.setattr(settings, "research_usage_ledger_path", str(ledger))
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
    text = ledger.read_text()
    assert "private-test-key" not in text and "private-guardian-evidence" not in text
    assert "untrusted-provider-body" not in text
    rows = [json.loads(line) for line in text.splitlines()]
    assert len(rows) == 2
    assert rows[0]["event_type"] == "api_attempt_started"
    assert rows[-1]["event_type"] == "api_attempt_finished"
    if not fails:
        assert rows[-1]["usage"]["total_tokens"] == 12
