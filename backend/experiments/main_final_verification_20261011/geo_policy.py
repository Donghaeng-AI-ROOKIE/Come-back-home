"""Offline KINTEX alert-policy candidates; no push or production mutation.

Mass is spread uniformly inside each res9 cell, then divided by geographic
overlap with the device's true res7 cells. This is an approximation when raw
walker endpoints are unavailable; it is NOT a calibrated probability.
"""
from functools import lru_cache
import math
import h3
from pyproj import Transformer
from shapely.geometry import Polygon
from shapely.ops import transform

PROJECT=Transformer.from_crs('EPSG:4326','EPSG:5179',always_xy=True).transform
@lru_cache(maxsize=40000)
def geometry(cell):
    points=[(lon,lat) for lat,lon in h3.cell_to_boundary(cell)]
    if any(not (124<lon<130 and 33<lat<40) for lon,lat in points):
        raise ValueError('This experiment projection is restricted to Korea')
    return transform(PROJECT,Polygon(points))

@lru_cache(maxsize=40000)
def overlap_weights(cell):
    if h3.get_resolution(cell)!=9:raise ValueError('Expected res9 map')
    fine=geometry(cell)
    # Do not rely on H3's experimental polygon-overlap enumeration: a stored
    # KINTEX cell returned a wrong neighbor and omitted its containing cell.
    # Two coarse rings conservatively cover this fine cell; clipping below
    # removes non-overlapping neighbors and verifies the complete partition.
    candidates=h3.grid_disk(h3.cell_to_parent(cell,7),2)
    parts=[(c,fine.intersection(geometry(c)).area) for c in sorted(candidates)]
    parts=[(c,a) for c,a in parts if a>1e-8]
    total=sum(a for _,a in parts)
    if not parts or abs(total/fine.area-1)>0.005:raise ValueError('Incomplete geographic partition')
    return tuple((c,a/total) for c,a in parts)

def geographic_scores(poa):
    result={}
    for cell,mass in poa.items():
        if not math.isfinite(mass) or mass<0:raise ValueError('Invalid probability mass')
        if mass==0:continue
        for parent,weight in overlap_weights(cell):result[parent]=result.get(parent,0)+mass*weight
    if not math.isclose(sum(result.values()),sum(poa.values()),abs_tol=1e-9):raise AssertionError('Mass lost')
    return result

def select_by_area(scores,budget_km2,coverage=None):
    if not math.isfinite(budget_km2) or budget_km2<=0:raise ValueError('Positive area budget required')
    if coverage is not None and not 0<coverage<=1:raise ValueError('Invalid coverage')
    chosen=set();used=mass=0.;total=sum(scores.values())
    for cell,value in sorted(scores.items(),key=lambda x:(-x[1],x[0])):
        if value<=0:continue
        size=h3.cell_area(cell,unit='km^2')
        if used+size>budget_km2+1e-10:break
        chosen.add(cell);used+=size;mass+=value
        if coverage is not None and mass>=coverage*total:break
    return chosen
