"""Named OSM POIs from the same preloaded region, without network lookup.

Only candidate search uses this cache. It never picks a home coordinate or
relabels an area centre as a named destination. The existing chooser still
compares candidates with the guardian's source.
"""
import json
import re
from pathlib import Path


class NamedPlaceCache:
    source = 'osm_cache'

    def __init__(self, cache_dir):
        self.path = Path(cache_dir) / 'bundles' / 'named-places.json'

    def locate(self, query, anchor=None):
        return None

    def home_alternatives(self, res, text):
        return None

    def keyword_candidates(self, query, anchor=None, size=5):
        from app.geo.geocode import GeoResult, ANCHOR_MAX_KM
        from app.geo.h3grid import haversine_km
        from app.schemas.persona import GeoPoint
        # Unanchored queries must use an address provider, not the first region.
        if anchor is None or not query or not self.path.is_file():
            return []
        try:
            if self.path.stat().st_size > 16 * 1024 * 1024:
                return []
            data = json.loads(self.path.read_text())
            if data.get('schema_version') != 1 or not re.fullmatch(r'[0-9a-f]{64}', data.get('source_sha256', '')):
                return []
            south, west, north, east = data['bbox_south_west_north_east']
            if not (south <= anchor.lat <= north and west <= anchor.lng <= east):
                return []
            q = re.sub(r'\s+', '', query)
            hits = []
            for row in data['places']:
                name = row['name']
                normalized = re.sub(r'\s+', '', name)
                if len(normalized) < 2 or not q.endswith(normalized):
                    continue
                point = GeoPoint(lat=row['lat'], lng=row['lng'])
                if not (south <= point.lat <= north and west <= point.lng <= east):
                    continue
                distance = haversine_km(anchor, point)
                if distance > ANCHOR_MAX_KM:
                    continue
                hits.append((distance, GeoResult(point, precision=row['precision'],
                    source=self.source, matched=name,
                    detail={'osm_type': row['osm_type'], 'osm_id': row['osm_id'],
                            'source_sha256': data['source_sha256']})))
            return [hit for _, hit in sorted(hits, key=lambda item: item[0])[:max(0, min(size, 10))]]
        except (OSError, ValueError, KeyError, TypeError):
            return []
