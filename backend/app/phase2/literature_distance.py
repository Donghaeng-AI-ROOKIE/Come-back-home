"""Deterministic, isotropic area map of the existing ISRID Urban lognormal fit.

No persona, LLM, behavioral strategy, destination, road preference or RNG input.
Equal-CDF radial bands distribute their mass uniformly by projected area inside
that band. AEQD/WGS84 geodesic radii; overlap H3 cells integrate band polygons.
This is quadrature of a distance prior, not a trajectory or time occupancy model.
"""
import math
from statistics import NormalDist
import numpy as np
import h3
import shapely
from shapely.geometry import Point, Polygon
from shapely.ops import transform
from pyproj import CRS, Transformer

MU=.095
SIGMA=1.48
VMAX_KMH=4.32
P95_Z=1.645
VERSION='isrid-urban-distance-area-v1'

def cdf(km):
    if km<=0:return 0.
    return NormalDist().cdf((math.log(km)-MU)/SIGMA)

def support_radius_km():
    """통계 채널 원의 최대 반경(P95 거리). 경과시간이 길어져도 이보다 커지지 않는다."""
    return math.exp(MU+P95_Z*SIGMA)


def _projection(lat,lng):
    local=CRS.from_proj4(f'+proj=aeqd +lat_0={lat} +lon_0={lng} +datum=WGS84 +units=m')
    return (Transformer.from_crs('EPSG:4326',local,always_xy=True),
            Transformer.from_crs(local,'EPSG:4326',always_xy=True))


def _inside(geo_disk,coverage_bbox):
    south,west,north,east=coverage_bbox
    w,s,e,n=geo_disk.bounds
    return not (w<west or s<south or e>east or n>north)


def support_fits(lat,lng,coverage_bbox,*,circle_segments=256):
    """최대 반경의 통계 채널 원이 지도 범위 안에 들어가는가.

    들어가지 않는 지도로 시작한 사건은 원이 경계에 닿는 순간부터 distance_map 이
    계산을 거부해, 그 뒤 재예측이 모두 실패한다. 지도를 고를 때 미리 확인한다."""
    _,inverse=_projection(lat,lng)
    disk=Point(0,0).buffer(support_radius_km()*1000,quad_segs=circle_segments)
    return _inside(transform(inverse.transform,disk),coverage_bbox)


def distance_map(lat,lng,hours,*,resolution=9,bands=64,circle_segments=256,coverage_bbox=None):
    if not all(math.isfinite(x) for x in (lat,lng,hours)) or hours<0 or not -80<lat<80 or not -180<lng<180:
        raise ValueError('invalid center/time for this local geodesic prior')
    if resolution!=9 or bands<16 or circle_segments<64:raise ValueError('unsupported quadrature configuration')
    cap=min(support_radius_km(),max(.5,VMAX_KMH*hours))
    retained=cdf(cap)
    forward,inverse=_projection(lat,lng)
    disk=Point(0,0).buffer(cap*1000,quad_segs=circle_segments)
    geo_disk=transform(inverse.transform,disk)
    if coverage_bbox is not None and not _inside(geo_disk,coverage_bbox):
        raise ValueError('distance support exceeds verified KINTEX map; never clip and renormalize')
    shape=h3.LatLngPoly([(y,x) for x,y in list(geo_disk.exterior.coords)[:-1]])
    cells=sorted(h3.h3shape_to_cells_experimental(shape,resolution,contain='overlap'))
    polys=[];rmax=[]
    for cell in cells:
        x,y=forward.transform(*zip(*[(lon,lat) for lat,lon in h3.cell_to_boundary(cell)]))
        polys.append(Polygon(zip(x,y)));rmax.append(max(math.hypot(a,b) for a,b in zip(x,y)))
    polys=np.array(polys,dtype=object);rmin=shapely.distance(polys,Point(0,0));rmax=np.array(rmax)
    scores=np.zeros(len(cells));old=Point(0,0);r0=0.;nd=NormalDist()
    for j in range(1,bands+1):
        r1=cap*1000 if j==bands else 1000*math.exp(MU+SIGMA*nd.inv_cdf(retained*j/bands))
        current=disk if j==bands else Point(0,0).buffer(r1,quad_segs=circle_segments)
        ring=current if j==1 else current.difference(old)
        candidates=np.flatnonzero((rmin<r1)&(rmax>r0))
        portions=shapely.area(shapely.intersection(polys[candidates],ring))
        # Every band has 1/bands of the conditional retained mass.
        scores[candidates]+=portions/(ring.area*bands)
        old=current;r0=r1
    total=float(scores.sum())
    if abs(total-1)>1e-6:raise ValueError(f'H3 integration mass missing: {total}')
    result={c:float(s/total) for c,s in zip(cells,scores) if s>0}
    return result,{'version':VERSION,'parameter_source':'existing_repository_ISRID_Urban_lognormal_approximation',
        'mu':MU,'sigma':SIGMA,'radius_cap_km':cap,'literature_mass_retained_before_conditioning':retained,
        'excluded_distance_tail_mass':1-retained,'conditional_within_statistical_and_walk_cap':True,
        'cdf_band_count':bands,'circle_quad_segments':circle_segments,'h3_resolution':resolution,
        'integrated_mass_before_roundoff_normalization':total,'cells':len(result),
        'verified_kintex_circle_support':coverage_bbox is not None,'geography':'WGS84 AEQD distance, isotropic direction',
        'persona_or_guardian_text_used':False,'lkp_coordinates_used':True,'model_calls':0,'walk_simulations':0,'road_or_personal_destination_weighting':False}
