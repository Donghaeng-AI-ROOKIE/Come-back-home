"""Reunion ends the case: a family-present observation is not report input (2026-10-11)."""
from datetime import datetime

import pytest
from fastapi import HTTPException

from app import storage
from app.phase1 import intake
from app.schemas.common import GeoPoint
from app.schemas.environment import BehaviorObservation
from app.schemas.persona import PersonaType

LKP = GeoPoint(lat=37.6652, lng=126.7483)


@pytest.fixture(autouse=True)
def isolated():
    storage.reset_for_tests()
    yield
    storage.reset_for_tests()


def _obs(value):
    now = datetime(2026, 10, 10, 10)
    return BehaviorObservation(fact="family_present", value=value, source="guardian_report",
                               valid_from=now, valid_until=datetime(2026, 10, 10, 16))


def _create(observations):
    return intake.create_report(missing_type=PersonaType.dementia, lkp=LKP,
                                lkp_time=datetime(2026, 10, 10, 10), behavior_observations=observations)


def test_reunion_observation_is_rejected_with_closure_guidance():
    before = len(storage.cases.list())
    with pytest.raises(HTTPException) as err:
        _create([_obs(True)])
    assert err.value.status_code == 422
    assert isinstance(err.value.detail, str) and "종결" in err.value.detail
    assert len(storage.cases.list()) == before  # nothing stored, no alert sent


def test_family_absent_observation_is_still_accepted():
    case = _create([_obs(False)])
    assert case.report.behavior_observations[0].value is False


def test_report_api_returns_plain_text_guidance():
    from fastapi.testclient import TestClient
    from app.main import app
    body = {"missing_type": "dementia", "lkp": {"lat": 37.6652, "lng": 126.7483},
            "lkp_time": "2026-10-10T10:00:00+09:00",
            "behavior_observations": [{"fact": "family_present", "value": True, "source": "guardian_report",
                                       "valid_from": "2026-10-10T10:00:00+09:00",
                                       "valid_until": "2026-10-10T16:00:00+09:00"}]}
    with TestClient(app) as client:
        res = client.post("/phase1/reports", json=body)
    assert res.status_code == 422 and isinstance(res.json()["detail"], str)
