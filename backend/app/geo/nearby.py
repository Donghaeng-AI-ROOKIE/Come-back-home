"""Retired nearby-walk lookup. Keep a no-I/O response for older clients.

Overpass timeouts occupied the shared compute queue ahead of predictions.
Nearby recommendations are disabled; prediction road networks are separate.
"""
from __future__ import annotations

from app.schemas.common import GeoPoint


def nearby_walks(center: GeoPoint, limit: int = 4, timeout: float = 15.0) -> list[dict]:
    """Return immediately without reading caches or contacting map providers."""
    return []
