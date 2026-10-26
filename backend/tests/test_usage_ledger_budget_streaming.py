"""Budget checks retain the file lock, but never materialize the ledger."""
import json
import multiprocessing
import tracemalloc
import pytest
from app.llm import usage_ledger as ledger


def _reserve(path, output):
    try:
        ledger.append_event({'event_type': 'api_attempt_started', 'run_id': 'shared'}, path, max_started=1)
        output.put('reserved')
    except ledger.CallBudgetExceeded:
        output.put('blocked')


def test_large_history_has_bounded_peak_memory_and_preserves_history(tmp_path):
    path = tmp_path / 'usage.jsonl'
    line = json.dumps({'event_type': 'api_attempt_finished', 'run_id': 'old', 'padding': 'x' * 4096}) + '\n'
    with path.open('w') as out:
        for _ in range(5000):
            out.write(line)
        out.write(json.dumps({'event_type': 'api_attempt_started', 'run_id': 'target'}) + '\n')
    before = path.stat().st_size
    tracemalloc.start()
    try:
        ledger.append_event({'event_type': 'api_attempt_started', 'run_id': 'target'}, path, max_started=2)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 2 * 1024 * 1024
    assert path.stat().st_size > before
    reserved = path.stat().st_size
    with pytest.raises(ledger.CallBudgetExceeded):
        ledger.append_event({'event_type': 'api_attempt_started', 'run_id': 'target'}, path, max_started=2)
    assert path.stat().st_size == reserved
    with path.open() as inp:
        assert inp.readline() == line


def test_concurrent_processes_cannot_exceed_budget(tmp_path):
    ctx = multiprocessing.get_context('spawn')
    output = ctx.Queue()
    path = str(tmp_path / 'usage.jsonl')
    processes = [ctx.Process(target=_reserve, args=(path, output)) for _ in range(4)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(15)
        assert process.exitcode == 0
    assert sorted(output.get(timeout=2) for _ in processes) == ['blocked'] * 3 + ['reserved']
    assert len((tmp_path / 'usage.jsonl').read_text().splitlines()) == 1


def test_malformed_history_fails_closed(tmp_path):
    path = tmp_path / 'usage.jsonl'
    original = '{broken}\n'
    path.write_text(original)
    with pytest.raises(json.JSONDecodeError):
        ledger.append_event({'event_type': 'api_attempt_started', 'run_id': 'new'}, path, max_started=1)
    assert path.read_text() == original
