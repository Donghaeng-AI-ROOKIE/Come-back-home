"""A confirmed end of a search is terminal, not a command to resume walking."""
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app import storage
from app.api import phase3
from app.config import settings
from app.phase2 import pipeline, continuous_prediction, refresher
from app.privacy import lifecycle
from app.schemas.case import Case, CaseStatus, CloseReason
from app.schemas.common import GeoPoint
from app.schemas.report import MissingReport


@pytest.fixture
def case(monkeypatch, tmp_path):
    storage.reset_for_tests()
    monkeypatch.setattr(settings, 'privacy_audit_path', str(tmp_path / 'audit.jsonl'))
    monkeypatch.setattr(lifecycle, '_audit_loaded', False)
    point = GeoPoint(lat=37.6631, lng=126.7458)
    start = datetime(2026, 10, 8, 8)
    report = MissingReport(id='terminal-report', missing_type='dementia', lkp=point, lkp_time=start)
    c = Case(id='terminal-case', report=report, status=CaseStatus.searching,
             lkp=point, lkp_time=start, current_poa={'8930e0b5b0fffff': 1.},
             last_sim_at=start+timedelta(hours=1))
    storage.cases.save(c.id, c)
    yield c
    storage.reset_for_tests()


@pytest.mark.parametrize('reason', [CloseReason.found, CloseReason.withdrawn])
def test_direct_prediction_after_closure_never_calls_model_or_map(case, monkeypatch, reason):
    lifecycle.close_case(case, reason)
    before = case.model_dump(mode='json')
    monkeypatch.setattr(pipeline.situation_link, 'cached', lambda *a: pytest.fail('work after closure'))
    with pytest.raises(lifecycle.AlreadyClosed):
        pipeline.run_prediction(case)
    assert case.model_dump(mode='json') == before


def test_stale_active_copy_cannot_reopen_stored_found_case(case, monkeypatch):
    stale = case.model_copy(deep=True)
    lifecycle.close_case(case, CloseReason.found)
    monkeypatch.setattr(pipeline.situation_link, 'cached', lambda *a: pytest.fail('stale work started'))
    with pytest.raises(lifecycle.AlreadyClosed):
        pipeline.run_prediction(stale)
    assert storage.cases.get(case.id).status is CaseStatus.found


def test_internal_preview_stops_before_prior_or_map_access(case):
    lifecycle.close_case(case, CloseReason.found)
    with pytest.raises(lifecycle.AlreadyClosed):
        pipeline.poa_at_elapsed(case, 6)


@pytest.mark.parametrize('cached', [False, True])
def test_closed_case_time_slider_rejects_cached_and_uncached_future(case, monkeypatch, cached):
    if cached:
        case.poa_by_hour['6'] = {'8930e0b5b0fffff': 1.}
    lifecycle.close_case(case, CloseReason.found)
    before = case.model_dump(mode='json')
    monkeypatch.setattr(pipeline, 'poa_at_elapsed', lambda *a: pytest.fail('preview after found'))
    with pytest.raises(HTTPException) as exc:
        phase3.get_poa(case.id, elapsed_hours=6)
    assert exc.value.status_code == 409
    assert '종결' in str(exc.value.detail)
    assert case.model_dump(mode='json') == before


def test_continuous_adapter_rejects_closed_case_before_policy_lookup(case, monkeypatch):
    lifecycle.close_case(case, CloseReason.found)
    monkeypatch.setattr(continuous_prediction.mind_preparation, 'ready', lambda *a: pytest.fail('policy after found'))
    with pytest.raises(lifecycle.AlreadyClosed):
        continuous_prediction.run_pair(case, None, None, None, 6)


def test_refresher_never_schedules_confirmed_found_case(case, monkeypatch):
    lifecycle.close_case(case, CloseReason.found)
    monkeypatch.setattr(pipeline, 'run_prediction', lambda *a, **k: pytest.fail('scheduled after found'))
    assert refresher.refresh_due_cases(now=case.lkp_time+timedelta(hours=6)) == []


@pytest.mark.parametrize('endpoint', ['predict', 'debug'])
def test_api_maps_closure_between_entry_check_and_prediction_to_conflict(case, monkeypatch, endpoint):
    from app.api import phase2, debug
    def closed_before_worker(*a, **k):
        lifecycle.close_case(case, CloseReason.found)
        raise lifecycle.AlreadyClosed('종결된 케이스')
    monkeypatch.setattr(pipeline, 'run_prediction', closed_before_worker)
    call = phase2.predict if endpoint == 'predict' else debug.predict_traced
    with pytest.raises(HTTPException) as exc:
        call(case.id)
    assert exc.value.status_code == 409
    assert storage.cases.get(case.id).status is CaseStatus.found


def test_closure_serializes_with_prediction_and_preserves_newest_snapshot(case, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from tests.kintex_fixtures import prior
    entered, finish, closing = Event(), Event(), Event()
    monkeypatch.setattr(pipeline.situation_link, 'cached', lambda *a: [])
    monkeypatch.setattr(pipeline, '_initial_prior', lambda *a: prior())
    monkeypatch.setattr(pipeline, '_load_roadnet', lambda *a: (None, 'test'))
    monkeypatch.setattr(pipeline.topdown, 'topdown_poa', lambda *a: {'8930e0b5b0fffff': 1.})
    def simulate(*a, **k):
        entered.set()
        assert finish.wait(3), 'test did not release the prediction'
        return {'8930e0b5b0fffff': 1.}
    monkeypatch.setattr(pipeline.simulation, 'run_monte_carlo', simulate)
    stale = case.model_copy(deep=True)
    def close():
        closing.set()
        return lifecycle.close_case(stale, CloseReason.found)
    with ThreadPoolExecutor(max_workers=2) as pool:
        prediction = pool.submit(pipeline.run_prediction, case, now=case.lkp_time+timedelta(hours=2))
        try:
            assert entered.wait(3)
            closed = pool.submit(close)
            assert closing.wait(3)
            assert not closed.done()  # closure is confirmed only after the in-flight publish
        finally:
            finish.set()
        prediction.result(timeout=3)
        result = closed.result(timeout=3)
    assert result.status is CaseStatus.found
    assert result.last_sim_at == case.lkp_time+timedelta(hours=2)
    monkeypatch.setattr(pipeline.situation_link, 'cached', lambda *a: pytest.fail('queued work after found'))
    with pytest.raises(lifecycle.AlreadyClosed):
        pipeline.run_prediction(stale)
