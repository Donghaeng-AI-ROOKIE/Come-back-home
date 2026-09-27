"""Purge batches must not rewrite the entire database for every case."""
from datetime import datetime,timedelta
import pytest
from app import storage
from app.config import settings
from app.privacy import worker,lifecycle
from app.schemas.case import Case,CaseStatus
from app.schemas.common import GeoPoint
from app.schemas.persona import PersonaType
from app.schemas.report import MissingReport


@pytest.fixture
def database(tmp_path,monkeypatch):
    storage.reset_for_tests()
    monkeypatch.setattr(settings,'persist_storage',True)
    monkeypatch.setattr(settings,'storage_db_path',str(tmp_path/'batch.db'))
    monkeypatch.setattr(settings,'privacy_audit_path',str(tmp_path/'audit.jsonl'))
    monkeypatch.setattr(lifecycle,'_audit_loaded',False)
    statements=[]
    storage._db().set_trace_callback(lambda s: statements.append(s) if s=='VACUUM' else None)
    yield statements
    storage.reset_for_tests()


def test_ten_expired_cases_compact_once_and_empty_run_does_not(database):
    now=datetime.now(); point=GeoPoint(lat=37.55,lng=126.94)
    for i in range(10):
        r=MissingReport(id=f'r{i}',missing_type=PersonaType.dementia,lkp=point,lkp_time=now)
        c=Case(id=f'c{i}',report=r,status=CaseStatus.closed,lkp=point,lkp_time=now,closed_at=now-timedelta(days=10))
        storage.cases.save(c.id,c)
    run=worker.run_once(now=now)
    assert run.success_count==10
    assert len(database)==1
    assert storage.cases.list()==[]
    worker.run_once(now=now)
    assert len(database)==1


def test_partial_failed_batch_still_compacts_deleted_bytes(database):
    repo=storage.Repository(table='temporary_secret')
    marker='synthetic-private-marker-0987654321'
    repo.save('key',marker)
    with pytest.raises(RuntimeError):
        with storage.batch_compaction():
            repo.delete('key'); storage.vacuum()
            raise RuntimeError('synthetic subsequent failure')
    assert len(database)==1
    from pathlib import Path
    assert marker.encode() not in Path(settings.storage_db_path).read_bytes()
