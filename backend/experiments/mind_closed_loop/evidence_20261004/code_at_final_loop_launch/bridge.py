"""Fresh-state decision bridge and honest probability accounting.

No guardian text-to-action parsing. A cache hit requires an identical full model
request. A stopped diagnostic walker is unresolved mass, never a stationary person.
"""
import copy
import hashlib
import json
from app.geo import h3grid
from app.schemas.common import GeoPoint


class MeteredDecisionBridge:
    def __init__(self, build_request, decode, request, *, max_calls):
        if not isinstance(max_calls, int) or max_calls < 0:
            raise ValueError('invalid call limit')
        self.build_request, self.decode, self.request = build_request, decode, request
        self.max_calls = max_calls
        self.calls = 0
        self.cache = {}
        self.audit = []
        self.stop_reason = None
        self.last_response = None

    def __call__(self, context):
        body = self.build_request(context)
        serialized = json.dumps(body, ensure_ascii=False, sort_keys=True, allow_nan=False)
        key = hashlib.sha256(serialized.encode()).hexdigest()
        self.stop_reason = None
        if key in self.cache:
            raw = copy.deepcopy(self.cache[key]); source = 'identical_request_cache'
        else:
            if self.calls >= self.max_calls:
                self.stop_reason = 'call_budget_exhausted_without_equivalent_context'
                self.audit.append({'request_sha256':key, 'source':'unresolved_budget'})
                return None
            self.calls += 1  # Failures consume a slot; no automatic retry.
            raw = self.request(body)
            self.cache[key] = copy.deepcopy(raw); source = 'fresh_request'
        self.last_response = copy.deepcopy(raw)
        try:
            value = self.decode(raw, context)
        except (ValueError, TypeError, KeyError) as exc:
            self.stop_reason = 'invalid_model_decision'
            self.audit.append({'request_sha256':key, 'source':source, 'error_type':type(exc).__name__})
            return None
        self.audit.append({'request_sha256':key, 'source':source, 'decision':copy.deepcopy(value)})
        if value is None: self.stop_reason = 'model_abstained'
        return value


def position(net, snapshot):
    node, target = snapshot['node'], snapshot['edge_to']
    if target is None: return net.node_location(node)
    attrs = net.edge_attrs(node, target)
    length = float(attrs['length'])
    fraction = min(1., max(0., snapshot['edge_progress_m']/length))
    geometry = attrs.get('geometry')
    if geometry is not None:
        # OSM polylines can be stored opposite to the directed edge.
        start = net.node_location(node)
        first, last = geometry.coords[0], geometry.coords[-1]
        d1 = (first[0]-start.lng)**2+(first[1]-start.lat)**2
        d2 = (last[0]-start.lng)**2+(last[1]-start.lat)**2
        p = geometry.interpolate(1-fraction if d2 < d1 else fraction, normalized=True)
        return GeoPoint(lat=p.y, lng=p.x)
    a,b = net.node_location(node),net.node_location(target)
    return GeoPoint(lat=a.lat+(b.lat-a.lat)*fraction,lng=a.lng+(b.lng-a.lng)*fraction)


def probability_snapshot(net, snapshots, minute):
    if not snapshots: raise ValueError('empty population')
    cells={}; unresolved=0
    for s in snapshots:
        if s['termination_reason'] or abs(s['state']['elapsed_minutes']-minute)>1e-7:
            unresolved+=1; continue
        cell=h3grid.cell_of(position(net,s))
        cells[cell]=cells.get(cell,0)+1/len(snapshots)
    return {'minute':minute,'cells':cells,'resolved_mass':sum(cells.values()),
            'unresolved_mass':unresolved/len(snapshots),'walkers':len(snapshots),
            'conditional_renormalization':False}
