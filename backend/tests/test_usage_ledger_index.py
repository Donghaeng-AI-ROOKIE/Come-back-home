"""Capped checks must not hold the ledger lock while counting old history.

The cloud worker records every Supabase RPC in the same ledger from its event
loop. A capped model call that scans the whole history under the file lock
froze the worker for ~30 s per SAR call on the 2.3 GB production ledger.
"""
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.llm import usage_ledger as ledger


class _JsonProbe:
    """Stands in for the module's json: counts parses and can pause the first one."""

    JSONDecodeError = json.JSONDecodeError

    def __init__(self, pause_first=False):
        self.calls = 0
        self.ledger_lines = 0
        self.pause_first = pause_first
        self.scanning = threading.Event()
        self.release = threading.Event()

    def loads(self, text, *args, **kwargs):
        self.calls += 1
        self.ledger_lines += (b'"event_type"' if isinstance(text, bytes) else '"event_type"') in text
        if self.pause_first and self.calls == 1:
            self.scanning.set()
            self.release.wait(10)
        return json.loads(text, *args, **kwargs)

    def dumps(self, *args, **kwargs):
        return json.dumps(*args, **kwargs)


def _history(path, lines=500, run_id='old'):
    with path.open('w') as out:
        for i in range(lines):
            kind = 'api_attempt_started' if i % 2 == 0 else 'api_attempt_finished'
            out.write(json.dumps({'event_type': kind, 'run_id': f'{run_id}-{i}'}) + '\n')


def _lines(path):
    return path.read_text().splitlines()


def test_other_writers_are_not_blocked_while_history_is_counted(tmp_path, monkeypatch):
    path = tmp_path / 'usage.jsonl'
    _history(path)
    probe = _JsonProbe(pause_first=True)
    monkeypatch.setattr(ledger, 'json', probe)
    writer_done = threading.Event()

    def transport_write():
        ledger.append_event({'event_type': 'transport_attempt_started', 'run_id': 'cloud_worker_transport'}, path)
        writer_done.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        capped = pool.submit(ledger.append_event,
                             {'event_type': 'api_attempt_started', 'run_id': 'sar'}, path, max_started=1)
        try:
            assert probe.scanning.wait(5)
            writer = pool.submit(transport_write)
            assert writer_done.wait(2), 'transport write waited for the capped call to finish counting history'
        finally:
            probe.release.set()
        capped.result(10)
        writer.result(10)
    events = [json.loads(line)['event_type'] for line in _lines(path)[500:]]
    assert sorted(events) == ['api_attempt_started', 'transport_attempt_started']


def test_repeat_checks_only_read_history_written_since_the_last_check(tmp_path, monkeypatch):
    path = tmp_path / 'usage.jsonl'
    _history(path)
    ledger.append_event({'event_type': 'api_attempt_started', 'run_id': 'prep'}, path, max_started=4)
    probe = _JsonProbe()
    monkeypatch.setattr(ledger, 'json', probe)
    ledger.append_event({'event_type': 'transport_attempt_started', 'run_id': 'cloud_worker_transport'}, path)
    ledger.append_event({'event_type': 'api_attempt_started', 'run_id': 'prep'}, path, max_started=4)
    assert probe.calls == 2


def test_prewarmed_index_leaves_first_capped_call_only_the_tail(tmp_path, monkeypatch):
    path = tmp_path / 'usage.jsonl'
    _history(path)
    ledger.warm_started_index(path)
    probe = _JsonProbe()
    monkeypatch.setattr(ledger, 'json', probe)
    ledger.append_event({'event_type': 'api_attempt_started', 'run_id': 'sar'}, path, max_started=1)
    assert probe.calls == 0


def test_prewarm_parses_history_outside_this_process(tmp_path, monkeypatch):
    # Parsing 2.3 GB in a worker thread held the GIL: after a restart the
    # worker's first request came 38.6 s late instead of ~2 s.
    path = tmp_path / 'usage.jsonl'
    _history(path)
    probe = _JsonProbe()
    monkeypatch.setattr(ledger, 'json', probe)
    ledger.warm_started_index(path)
    assert probe.ledger_lines == 0
    with pytest.raises(ledger.CallBudgetExceeded):
        ledger.append_event({'event_type': 'api_attempt_started', 'run_id': 'old-0'}, path, max_started=1)
    ledger.append_event({'event_type': 'api_attempt_started', 'run_id': 'old-1'}, path, max_started=1)
    assert probe.ledger_lines == 0


def test_prewarm_on_malformed_history_fails_and_capped_calls_still_fail_closed(tmp_path):
    path = tmp_path / 'usage.jsonl'
    path.write_text('{broken}\n')
    with pytest.raises(ValueError):
        ledger.warm_started_index(path)
    with pytest.raises(json.JSONDecodeError):
        ledger.append_event({'event_type': 'api_attempt_started', 'run_id': 'new'}, path, max_started=1)
    assert path.read_text() == '{broken}\n'


def test_counts_include_events_written_outside_this_process(tmp_path):
    path = tmp_path / 'usage.jsonl'
    _history(path)
    ledger.append_event({'event_type': 'api_attempt_started', 'run_id': 'shared'}, path, max_started=3)
    with path.open('a') as other_process:
        for _ in range(2):
            other_process.write(json.dumps({'event_type': 'api_attempt_started', 'run_id': 'shared'}) + '\n')
    reserved = path.stat().st_size
    with pytest.raises(ledger.CallBudgetExceeded):
        ledger.append_event({'event_type': 'api_attempt_started', 'run_id': 'shared'}, path, max_started=3)
    assert path.stat().st_size == reserved


def test_unfinished_line_from_a_concurrent_writer_is_counted_once_complete(tmp_path):
    path = tmp_path / 'usage.jsonl'
    started = json.dumps({'event_type': 'api_attempt_started', 'run_id': 'r'})
    path.write_text(started + '\n' + started[:20])
    ledger.warm_started_index(path)
    with path.open('a') as writer:
        writer.write(started[20:] + '\n')
    with pytest.raises(ledger.CallBudgetExceeded):
        ledger.append_event({'event_type': 'api_attempt_started', 'run_id': 'r'}, path, max_started=2)
    ledger.append_event({'event_type': 'api_attempt_started', 'run_id': 'r'}, path, max_started=3)
    assert len(_lines(path)) == 3


@pytest.mark.parametrize('rewrite', ['replace', 'truncate'])
def test_replaced_or_rewritten_ledger_is_counted_again(tmp_path, rewrite):
    path = tmp_path / 'usage.jsonl'
    _history(path)
    ledger.append_event({'event_type': 'api_attempt_started', 'run_id': 'r'}, path, max_started=1)
    with pytest.raises(ledger.CallBudgetExceeded):
        ledger.append_event({'event_type': 'api_attempt_started', 'run_id': 'r'}, path, max_started=1)
    fresh = json.dumps({'event_type': 'api_attempt_finished', 'run_id': 'new-history'}) + '\n'
    if rewrite == 'replace':
        other = tmp_path / 'replacement.jsonl'
        other.write_text(fresh)
        os.replace(other, path)
    else:
        path.write_text(fresh * 2000)
    ledger.append_event({'event_type': 'api_attempt_started', 'run_id': 'r'}, path, max_started=1)
