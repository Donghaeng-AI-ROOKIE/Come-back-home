import gzip
import hashlib
import json
from pathlib import Path

import pytest
from app.config import settings
from app.geo import road_bundles
from app.schemas.common import GeoPoint

FIXTURE = Path(__file__).parent / 'fixtures' / 'jeongneung_walk_800m.graphml'
CENTER = GeoPoint(lat=37.6061, lng=127.0106)


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'roadnet_cache_dir', str(tmp_path))
    road_bundles._LOADED.clear()
    raw = FIXTURE.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    root = tmp_path / 'bundles'; root.mkdir()
    item = {'sha256': digest, 'object_key': 'regions/reference.graphml.gz',
            'radius_m': 3000, 'bbox_south_west_north_east': [37.5,126.9,37.7,127.1]}
    (root/'index.json').write_text(json.dumps({'bundles':[item]}))
    return root, raw, digest


def test_download_then_disk_cache_without_storage_or_overpass(bundle, monkeypatch):
    root, raw, digest = bundle
    calls=[]
    monkeypatch.setattr(road_bundles, '_download', lambda key: calls.append(key) or gzip.compress(raw))
    first = road_bundles.get_preloaded_network(CENTER, 1000)
    assert first.road_distance_km(CENTER, CENTER) == 0
    assert (root/(digest+'.graphml')).read_bytes() == raw
    road_bundles._LOADED.clear()  # simulate a fresh worker
    second = road_bundles.get_preloaded_network(CENTER, 1000)
    assert set(first.graph.edges) == set(second.graph.edges)
    assert calls == ['regions/reference.graphml.gz']


def test_outside_bundle_never_downloads(bundle, monkeypatch):
    monkeypatch.setattr(road_bundles, '_download', lambda _: pytest.fail('unexpected Storage request'))
    assert road_bundles.get_preloaded_network(GeoPoint(lat=37.67,lng=126.75),3000) is None
    assert road_bundles.get_preloaded_network(CENTER,30000) is None


def test_tampered_bundle_not_used_or_cached(bundle, monkeypatch):
    root, raw, digest = bundle
    monkeypatch.setattr(road_bundles, '_download', lambda _: gzip.compress(b'wrong data'))
    with pytest.raises(ValueError, match='integrity'):
        road_bundles.get_preloaded_network(CENTER,1000)
    assert not (root/(digest+'.graphml')).exists()


def test_corrupt_local_cache_recovered_from_verified_storage(bundle, monkeypatch):
    root, raw, digest = bundle
    path=root/(digest+'.graphml'); path.write_bytes(b'incomplete')
    monkeypatch.setattr(road_bundles, '_download', lambda _: gzip.compress(raw))
    assert road_bundles.get_preloaded_network(CENTER,1000) is not None
    assert path.read_bytes() == raw
