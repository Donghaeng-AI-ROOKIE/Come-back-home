"""Geographic coarse cover of fine H3 polygons; devices stay coarse."""
from functools import lru_cache
import h3
from shapely.geometry import Polygon
from shapely.ops import unary_union


def _polygon(cell, origin):
    # Unwrap around the fine cell so dateline polygons remain local.
    return Polygon([(origin + (lon-origin+180)%360-180, lat)
                    for lat,lon in h3.cell_to_boundary(cell)])


@lru_cache(maxsize=40000)
def overlapping_cells(cell: str, res: int) -> frozenset[str]:
    fine_res=h3.get_resolution(cell)
    if not 0 <= res <= fine_res:
        raise ValueError('coarse cover resolution must not exceed source resolution')
    if res == fine_res:
        return frozenset([cell])
    origin=h3.cell_to_latlng(cell)[1]
    fine=_polygon(cell,origin)
    parent=h3.cell_to_parent(cell,res)
    polygons={c:_polygon(c,origin) for c in h3.grid_disk(parent,2)}
    # Verify complete cover rather than assuming the candidate rings suffice.
    if fine.difference(unary_union(list(polygons.values()))).area > fine.area*1e-8:
        raise ValueError('incomplete geographic coarse cover')
    return frozenset(c for c,p in polygons.items()
                     if fine.intersection(p).area > fine.area*1e-10)


def cover(cells, res):
    return set().union(*(overlapping_cells(c,res) for c in cells)) if cells else set()
