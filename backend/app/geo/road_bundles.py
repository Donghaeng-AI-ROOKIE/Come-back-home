"""Verified regional road bundles, prepublished in private Supabase Storage.

The deployment syncs a small index into ROADNET_CACHE_DIR/bundles/index.json.
Graphs are immutable, addressed by SHA-256, and downloaded only on cache miss.
No guardian data or report coordinates are sent to Storage.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

from app.config import settings
from app.llm.usage_ledger import append_event

_LOCK = threading.Lock()
_LOADED = {}
_MAX_COMPRESSED = 48 * 1024 * 1024
_MAX_GRAPH = 256 * 1024 * 1024


def _download(object_key: str) -> bytes:
    url = os.environ.get('SUPABASE_URL', '').rstrip('/')
    key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
    parts = urlsplit(url)
    if parts.scheme != 'https' or not (parts.hostname or '').endswith('.supabase.co') or parts.path or parts.query or parts.fragment or not key:
        raise ValueError('Private Supabase Storage connection unavailable')
    meta = {'run_id': 'regional_road_bundle', 'attempt_id': str(uuid.uuid4()),
            'provider': 'Supabase', 'role': 'road_bundle_download',
            'actual_cost': None, 'cost_status': 'unconfirmed'}
    ledger = settings.research_usage_ledger_path
    append_event({**meta, 'event_type': 'transport_attempt_started'}, ledger)
    started = time.monotonic()
    status, error = None, None
    try:
        with httpx.stream('GET', url + '/storage/v1/object/authenticated/road-network-cache/' + quote(object_key, safe='/'),
                          headers={'apikey': key, 'Authorization': 'Bearer ' + key},
                          timeout=30, follow_redirects=False) as response:
            status = response.status_code
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > _MAX_COMPRESSED or time.monotonic() - started > 60:
                    raise ValueError('Road bundle download limit exceeded')
            return bytes(data)
    except Exception as exc:
        error = type(exc).__name__
        raise
    finally:
        append_event({**meta, 'event_type': 'transport_attempt_finished',
                      'http_status': status, 'error_type': error,
                      'duration_ms': round((time.monotonic()-started)*1000, 2)}, ledger)


def get_preloaded_network(center, radius_m: int):
    """Return a bundle covering the requested area, or None for an unprepared area."""
    import osmnx as ox
    from app.geo.roadnet import OSMnxNetwork

    root = Path(settings.roadnet_cache_dir) / 'bundles'
    index_path = root / 'index.json'
    if not index_path.is_file():
        return None
    index = json.loads(index_path.read_text())
    west, south, east, north = ox.utils_geo.bbox_from_point((center.lat, center.lng), dist=radius_m)
    candidates = []
    for item in index.get('bundles', []):
        s, w, n, e = item['bbox_south_west_north_east']
        if s <= south and w <= west and n >= north and e >= east:
            candidates.append(item)
    if not candidates:
        return None
    item = min(candidates, key=lambda x: x['radius_m'])
    digest = item['sha256']
    if not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('Invalid road bundle digest')
    object_key = item['object_key']
    if not re.fullmatch(r'[A-Za-z0-9_/-]+\.graphml\.gz', object_key) or '..' in object_key:
        raise ValueError('Invalid road bundle object key')
    with _LOCK:
        if digest in _LOADED:
            return _LOADED[digest]
        path = root / (digest + '.graphml')
        valid = path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest
        if not valid:
            import io
            with gzip.GzipFile(fileobj=io.BytesIO(_download(object_key))) as stream:
                raw = stream.read(_MAX_GRAPH + 1)
            if len(raw) > _MAX_GRAPH or hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError('Road bundle integrity check failed')
            root.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix('.tmp')
            tmp.write_bytes(raw)
            tmp.replace(path)
        net = OSMnxNetwork.from_graphml(path)
        net.coverage_bbox = item['bbox_south_west_north_east']
        net.bundle_source = 'supabase_storage'
        net.bundle_sha256 = digest
        _LOADED[digest] = net
        return net
