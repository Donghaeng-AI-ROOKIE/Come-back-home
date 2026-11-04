"""Retired recommendations must never hold up predictions or contact Overpass."""
import asyncio
import socket
import urllib.request

import httpx
import pytest
from fastapi.testclient import TestClient

from app.geo import nearby
from app.main import app
from app.schemas.common import GeoPoint

CENTER = GeoPoint(lat=37.6689, lng=126.7457)


@pytest.fixture
def forbid_lookup(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Retired nearby recommendations performed I/O")
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    from app import storage
    monkeypatch.setattr(storage.nearby_walks_cache, "get", forbidden)
    monkeypatch.setattr(storage.nearby_walks_cache, "save", forbidden)


def test_direct_lookup_does_not_touch_network_or_cache(forbid_lookup):
    for _ in range(3):
        assert nearby.nearby_walks(CENTER) == []


def test_legacy_http_requests_return_empty_without_retry_errors(forbid_lookup):
    client = TestClient(app)
    for _ in range(3):
        response = client.get('/geo/nearby-walks', params={'lat': CENTER.lat, 'lng': CENTER.lng})
        assert response.status_code == 200
        assert response.json() == []


def test_legacy_lookup_does_not_hold_compute_consumer(forbid_lookup, monkeypatch):
    from app.cloud_bridge import worker
    from types import SimpleNamespace
    # Authorization is covered by test_cloud_bridge; this test exercises the
    # deployed ASGI transport and two sequential compute dispatches, without LLMs.
    monkeypatch.setattr(worker, 'authorize', lambda owner, method, path, body:
                        SimpleNamespace(method=method, path=path, body=body))

    async def scenario():
        transport = worker.EarlyResponseTransport(app)
        async with httpx.AsyncClient(transport=transport, base_url='http://private-engine') as api:
            job = {'owner_id': 'offline', 'method': 'GET',
                   'path': f'/geo/nearby-walks?lat={CENTER.lat}&lng={CENTER.lng}'}
            for _ in range(4):
                assert await worker.dispatch(api, job, enabled=True) == (200, [])
            # The following compute request can run immediately; substitute only
            # its handler to avoid executing a real prediction.
            calls = []
            async def prediction(method, path, **kwargs):
                calls.append(path)
                return httpx.Response(200, json={'prediction_reached': True})
            monkeypatch.setattr(api, 'request', prediction)
            result = await worker.dispatch(api, {**job, 'method': 'POST',
                'path': '/phase2/cases/offline/predict'}, enabled=True)
            assert result == (200, {'prediction_reached': True})
            assert calls == ['/phase2/cases/offline/predict']
            if transport.pending:
                await asyncio.gather(*transport.pending)

    async def bounded():
        await asyncio.wait_for(scenario(), timeout=2)
    asyncio.run(bounded())


def test_geo_query_bounds_still_reject_invalid_input():
    client = TestClient(app)
    for params in [{'lat': 91, 'lng': 126}, {'lat': 37, 'lng': 181}, {'lat': 37, 'lng': 126, 'limit': -1}]:
        assert client.get('/geo/nearby-walks', params=params).status_code == 422
