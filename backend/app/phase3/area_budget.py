"""Select probability density under the area actually eligible for delivery."""
from functools import lru_cache
import math
import h3
from pyproj import Geod
from shapely.geometry import Polygon
from app.geo import h3cover
_GEOD = Geod(ellps='WGS84')

@lru_cache(maxsize=100000)
def cell_area_km2(cell: str) -> float:
    polygon = Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(cell)])
    return abs(_GEOD.geometry_area_perimeter(polygon)[0]) / 1e6

def select(poa, budget, max_cells, target_res):
    if not math.isfinite(budget) or budget < 0:
        raise ValueError('area budget must be finite and nonnegative')
    if target_res not in (7, 8, 9):
        raise ValueError('unsupported delivery resolution')
    if budget == 0 or max_cells <= 0:
        return []
    # The density ranking is deterministic. Geographic cover at coarser H3
    # resolution can add multiple cells; charge their union, never fine-cell area.
    ranked = sorted(((c,p) for c,p in poa.items() if math.isfinite(p) and p > 0),
                    key=lambda item: (-item[1]/cell_area_km2(item[0]), item[0]))
    selected=[]; targets=set(); used=0.
    for cell,prob in ranked:
        if len(selected) >= max_cells:
            break
        added=h3cover.cover([cell],target_res)-targets
        cost=sum(cell_area_km2(c) for c in sorted(added))
        if used+cost <= budget+1e-12:
            selected.append(cell);targets.update(added);used+=cost
    return selected
