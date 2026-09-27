"""Real temporary SQLite, no model calls: startup and failed writes."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import threading
import time
import pytest
from app import storage
from app.config import settings


@pytest.fixture
def persisted(tmp_path, monkeypatch):
    storage.reset_for_tests()
    monkeypatch.setattr(settings, 'persist_storage', True)
    monkeypatch.setattr(settings, 'storage_db_path', str(tmp_path / 'concurrency.db'))
    yield
    storage.reset_for_tests()


def test_concurrent_first_access_uses_one_initialized_connection(persisted, monkeypatch):
    original = storage.sqlite3.connect
    calls = []
    def connect(*a, **kw):
        calls.append(1)
        time.sleep(.02)
        return original(*a, **kw)
    monkeypatch.setattr(storage.sqlite3, 'connect', connect)
    barrier = threading.Barrier(8)
    def access(i):
        barrier.wait()
        repo = storage.Repository(table=f'parallel_{i}')
        repo.save('key', i)
        return storage._db()
    with ThreadPoolExecutor(max_workers=8) as pool:
        connections = list(pool.map(access, range(8)))
    assert len(calls) == 1
    assert all(c is connections[0] for c in connections)


def test_second_reader_waits_for_complete_cache(persisted, monkeypatch):
    repo = storage.Repository(table='loading')
    repo.save('key', 42)
    repo._items.clear(); repo._loaded = False
    entered = threading.Event(); release = threading.Event()
    original = repo._decode
    def decode(raw):
        entered.set()
        assert release.wait(3)
        return original(raw)
    monkeypatch.setattr(repo, '_decode', decode)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(repo.get, 'key')
        assert entered.wait(3)
        second = pool.submit(repo.get, 'key')
        try:
            assert not second.done()
        finally:
            release.set()
        assert first.result(3) == second.result(3) == 42


def test_failed_disk_write_does_not_publish_or_remove_cache(persisted, monkeypatch):
    repo = storage.Repository(table='failed_write')
    repo.save('key', {'value':1})
    def fail(*a): raise sqlite3.OperationalError('synthetic failure')
    monkeypatch.setattr(repo, '_ensure_table', fail)
    with pytest.raises(sqlite3.OperationalError): repo.save('key', {'value':2})
    assert repo.get('key') == {'value':1}
    with pytest.raises(sqlite3.OperationalError): repo.delete('key')
    assert repo.get('key') == {'value':1}
