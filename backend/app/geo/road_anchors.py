"""Connect place centroids to existing road geometry without increasing snap limits.

Simplified OSM edges may be hundreds of metres long. A nearby point can be far
from both endpoints even though it is inside the permitted road snap distance.
Split only that existing edge (and its matching reverse), never add a shortcut.
The verified source graph and its provenance file remain immutable.
"""
from hashlib import sha256
import math


def connect_anchors(net, points):
    from pyproj import CRS, Transformer
    from shapely.geometry import LineString, Point
    from shapely.ops import substring, transform
    from app.geo.roadnet import OSMnxNetwork, _SNAP_SLACK_KM

    points = list(points)
    key = tuple((float(p.lat), float(p.lng)) for p in points)
    cache = getattr(net, '_anchor_networks', {})
    if key in cache:
        return cache[key]
    result = net
    connections = []
    for point in points:
        south, west, north, east = net.coverage_bbox
        if not (south <= point.lat <= north and west <= point.lng <= east):
            continue  # Never pull an out-of-region report into the cached map.
        if result.road_distance_km(point, point) is not None:
            continue
        crs = CRS.from_proj4(f'+proj=aeqd +lat_0={point.lat} +lon_0={point.lng} +datum=WGS84 +units=m')
        forward = Transformer.from_crs('EPSG:4326', crs, always_xy=True).transform
        backward = Transformer.from_crs(crs, 'EPSG:4326', always_xy=True).transform
        target = Point(0, 0)
        limit = _SNAP_SLACK_KM * 1000
        dlat = _SNAP_SLACK_KM / 110.5
        dlng = dlat / max(.01, math.cos(math.radians(point.lat)))
        best = None
        g = result.graph
        for u, v, k, data in g.edges(keys=True, data=True):
            if u == v:
                continue
            line = data.get('geometry')
            if line is None:
                line = LineString([(g.nodes[u]['x'], g.nodes[u]['y']), (g.nodes[v]['x'], g.nodes[v]['y'])])
            minx, miny, maxx, maxy = line.bounds
            if maxx < point.lng-dlng or minx > point.lng+dlng or maxy < point.lat-dlat or miny > point.lat+dlat:
                continue
            projected = transform(forward, line)
            distance = projected.distance(target)
            if distance <= limit and (best is None or distance < best[0]):
                best = (distance, u, v, k, line)
        if best is None:
            continue
        distance, u, v, k, line = best
        if result is net:
            result = OSMnxNetwork()
            result.graph = net.graph.copy()
            result.coverage_bbox = list(net.coverage_bbox)
            result.node_env = dict(net.node_env)
            g = result.graph
        directed = [(u, v, k, dict(g[u][v][k]))]
        for rk, data in list((g.get_edge_data(v, u) or {}).items()):
            reverse = data.get('geometry')
            if reverse is None:
                reverse = LineString([(g.nodes[v]['x'], g.nodes[v]['y']), (g.nodes[u]['x'], g.nodes[u]['y'])])
            if reverse.equals(line):
                directed.append((v, u, rk, dict(data)))
        anchor_projected = transform(forward, line).interpolate(transform(forward, line).project(target))
        anchor = transform(backward, anchor_projected)
        node = -int(sha256(f'{u}:{v}:{k}:{point.lat}:{point.lng}'.encode()).hexdigest()[:15], 16)
        while node in g:
            node -= 1
        g.add_node(node, x=anchor.x, y=anchor.y, synthetic_road_anchor=True)
        # Environmental observations are not invented at the inserted road point.
        result.node_env[node] = {}
        for a, b, edge_key, data in directed:
            geometry = data.get('geometry')
            if geometry is None:
                geometry = LineString([(g.nodes[a]['x'], g.nodes[a]['y']), (g.nodes[b]['x'], g.nodes[b]['y'])])
            start = Point(g.nodes[a]['x'], g.nodes[a]['y'])
            if Point(geometry.coords[-1]).distance(start) < Point(geometry.coords[0]).distance(start):
                geometry = LineString(list(geometry.coords)[::-1])
            metric = transform(forward, geometry)
            along = metric.project(anchor_projected)
            if not 0 < along < metric.length:
                raise ValueError('road anchor must lie inside an existing edge')
            first = dict(data, length=float(data['length'])*along/metric.length,
                         geometry=transform(backward, substring(metric, 0, along)))
            second = dict(data, length=float(data['length'])-first['length'],
                          geometry=transform(backward, substring(metric, along, metric.length)))
            g.remove_edge(a, b, edge_key)
            g.add_edge(a, node, key=edge_key, **first)
            g.add_edge(node, b, key=edge_key, **second)
        connections.append({'snap_distance_m':round(distance, 3), 'source':'existing_osm_edge', 'limit_m':limit})
    result.anchor_connections = connections
    if len(cache) >= 4:
        cache.clear()
    cache[key] = result
    net._anchor_networks = cache
    return result
