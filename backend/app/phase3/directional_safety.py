"""Counterfactual direction scores for alert allocation, never calibrated POA.
Only onset information, personal predictions and a verified directed road graph
are inputs. A future truth position or observed future path is not accepted.
"""
import math
import h3
import networkx as nx
from pyproj import Geod
from app.geo import h3cover
from app.phase3.area_budget import cell_area_km2, select
_GEOD=Geod(ellps="WGS84")

def heading(personal, origin, attractions=()):
    sx=sy=radius=0.
    for cell,mass in personal.items():
        if not math.isfinite(mass) or mass<=0:continue
        lat,lng=h3.cell_to_latlng(cell)
        bearing,_,distance=_GEOD.inv(origin.lng,origin.lat,lng,lat)
        angle=math.radians(bearing)
        sx+=mass*distance*math.sin(angle);sy+=mass*distance*math.cos(angle)
        radius+=mass*distance
    norm=math.hypot(sx,sy)
    if norm>=150 and radius>0 and norm/radius>=.2:
        return math.degrees(math.atan2(sx,sy)), "personal_displacement"
    sx=sy=0.
    for point,weight in attractions:
        if weight<=0:continue
        bearing,_,distance=_GEOD.inv(origin.lng,origin.lat,point.lng,point.lat)
        sx+=weight*distance*math.sin(math.radians(bearing))
        sy+=weight*distance*math.cos(math.radians(bearing))
    if math.hypot(sx,sy)<150:return None,"no_reliable_heading"
    return math.degrees(math.atan2(sx,sy)),"onboarding_attractions"

def reachable_features(graph, origin, max_distance_m, *, source_node=None, return_distances=False):
    if source_node is None:
        source_node=min(graph.nodes,key=lambda n:
            _GEOD.inv(origin.lng,origin.lat,graph.nodes[n]["x"],graph.nodes[n]["y"])[2])
    _,_,snap=_GEOD.inv(origin.lng,origin.lat,graph.nodes[source_node]["x"],graph.nodes[source_node]["y"])
    if snap>150:
        result=([],{"status":"origin_outside_verified_roads","snap_m":snap})
        return (*result,{}) if return_distances else result
    distances=nx.single_source_dijkstra_path_length(graph,source_node,cutoff=max_distance_m,weight="length")
    points=[]
    for node,road_distance in distances.items():
        d=graph.nodes[node]
        bearing,_,radial=_GEOD.inv(origin.lng,origin.lat,d["x"],d["y"])
        points.append((h3.latlng_to_cell(d["y"],d["x"],9),bearing,float(road_distance),radial))
    result=(points,{"status":"verified_directed_road_nodes","snap_m":snap,"source_node":str(source_node),
                   "max_distance_m":max_distance_m,"reachable_nodes":len(points)})
    return (*result,distances) if return_distances else result

def reachable_place_guards(graph, places, node_distances, budget_m, target_res):
    """Snap only for reachability; cover both the reported place and road node.

    A road node can be just across an H3 boundary from a valid reported address.
    Requiring a node inside its exact H3 cell incorrectly discards that place.
    """
    cells=set();diagnostics=[]
    for point in places:
        node=min(graph.nodes,key=lambda n:_GEOD.inv(point.lng,point.lat,
                 graph.nodes[n]["x"],graph.nodes[n]["y"])[2])
        d=graph.nodes[node];snap=_GEOD.inv(point.lng,point.lat,d["x"],d["y"])[2]
        reachable=snap<=150 and node_distances.get(node,math.inf)+snap<=budget_m
        diagnostics.append({"snap_m":snap,"reachable":reachable})
        if reachable:
            cells.add(h3.latlng_to_cell(point.lat,point.lng,target_res))
            cells.add(h3.latlng_to_cell(d["y"],d["x"],target_res))
    return sorted(cells),diagnostics

def opposite_scores(personal, origin, road_features, elapsed_hours, walk_bout_min,
                    rest_min, *, attractions=(), planning_speed_m_min=35.,
                    progress=.65, angular_sigma_deg=40., literature=None):
    if elapsed_hours<0 or walk_bout_min<=0 or rest_min<0:
        raise ValueError("invalid time or physical walking capacity")
    if not all(math.isfinite(v) for v in (elapsed_hours,walk_bout_min,rest_min,
                                         planning_speed_m_min,progress,angular_sigma_deg)):
        raise ValueError("nonfinite directional parameters")
    if planning_speed_m_min<=0 or not 0<progress<=1 or angular_sigma_deg<=0:
        raise ValueError("invalid directional score parameters")
    direction,source=heading(personal,origin,attractions)
    budget=elapsed_hours*60*planning_speed_m_min*walk_bout_min/(walk_bout_min+rest_min)
    meta={"heading_source":source,"heading_deg":direction,"budget_m":budget,
          "progress":progress,"angular_sigma_deg":angular_sigma_deg,
          "calibrated_probability":False,"truth_used":False}
    if direction is None or budget<=0:return {},meta
    reverse=(direction+180)%360;target=budget*progress;sigma=max(250.,budget*.18)
    score={}
    for cell,bearing,road_distance,radial in road_features:
        if road_distance>budget or radial<150:continue
        error=(bearing-reverse+180)%360-180
        if abs(error)>90:continue
        value=math.exp(-.5*(error/angular_sigma_deg)**2-.5*((road_distance-target)/sigma)**2)
        # A weak literature density factor keeps the broad counterfactual tied
        # to the sourced population prior; these remain allocation scores.
        if literature is not None:
            prior=literature.get(cell,0.)
            value*=math.sqrt(prior) if math.isfinite(prior) and prior>0 else 0.
        if value>0:score[cell]=max(value,score.get(cell,0.))
    total=sum(score.values())
    meta.update(reverse_heading_deg=reverse,score_cells=len(score))
    return ({c:v/total for c,v in score.items()} if total>0 else {}),meta

def select_with_safety(poa, safety, budget, max_cells, target_res, *, fraction, mode):
    if not math.isfinite(fraction) or not 0<=fraction<=.3:
        raise ValueError("invalid directional area fraction")
    if mode not in ("additional","reserved"):raise ValueError("invalid directional allocation")
    core_budget=budget if mode=="additional" else budget*(1-fraction)
    core=select(poa,core_budget,max_cells,target_res)
    result,meta=add_safety_to_core(core,safety,budget*fraction,max_cells,target_res)
    meta.update(core_budget_km2=core_budget,mode=mode)
    return result,meta

def select_core_with_places(poa, budget, max_cells, target_res, place_cells=()):
    """Keep supplied, reachable onset places within the same geographic budget."""
    core=[];targets=set();used=0.
    for cell in sorted(set(place_cells)):
        added=h3cover.cover([cell],target_res)-targets
        cost=sum(cell_area_km2(c) for c in added)
        if used+cost>budget+1e-12 or len(core)>=max_cells:
            raise ValueError("confirmed personal places exceed alert budget")
        if added:core.append(cell);targets.update(added);used+=cost
    ranked=sorted(((c,p) for c,p in poa.items() if math.isfinite(p) and p>0),
                  key=lambda z:(-z[1]/cell_area_km2(z[0]),z[0]))
    for cell,_ in ranked:
        if len(core)>=max_cells:break
        added=h3cover.cover([cell],target_res)-targets
        cost=sum(cell_area_km2(c) for c in added)
        if added and used+cost<=budget+1e-12:
            core.append(cell);targets.update(added);used+=cost
    return core

def add_safety_to_core(core, safety, safety_budget, max_cells, target_res, *, min_outside_score_mass=0.0):
    if not math.isfinite(safety_budget) or safety_budget<0:
        raise ValueError("invalid safety budget")
    targets=h3cover.cover(core,target_res);result=list(core);extra=[];used=0.
    if not math.isfinite(min_outside_score_mass) or not 0<=min_outside_score_mass<=1:
        raise ValueError("invalid outside score gate")
    total=sum(p for p in safety.values() if math.isfinite(p) and p>0)
    outside=sum(p for c,p in safety.items() if math.isfinite(p) and p>0
                and h3cover.cover([c],target_res)-targets)
    outside_fraction=outside/total if total>0 else 0.
    if outside_fraction < min_outside_score_mass:
        return result,{"core_cells":core,"safety_cells":[],
                       "total_area_km2":sum(cell_area_km2(c) for c in targets),
                       "safety_budget_km2":safety_budget,"outside_score_fraction":outside_fraction,
                       "gate_skipped":True}
    ranked=sorted(((c,p) for c,p in safety.items() if math.isfinite(p) and p>0),
                  key=lambda z:(-z[1]/cell_area_km2(z[0]),z[0]))
    for cell,_ in ranked:
        if len(result)>=max_cells:break
        added=h3cover.cover([cell],target_res)-targets
        cost=sum(cell_area_km2(c) for c in added)
        if added and used+cost<=safety_budget+1e-12:
            result.append(cell);extra.append(cell);targets.update(added);used+=cost
    return result,{"core_cells":core,"safety_cells":extra,
                  "total_area_km2":sum(cell_area_km2(c) for c in targets),
                  "safety_budget_km2":safety_budget,"outside_score_fraction":outside_fraction,
                  "gate_skipped":False}
