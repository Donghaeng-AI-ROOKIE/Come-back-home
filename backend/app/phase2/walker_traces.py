"""Representative personal-walker paths for the booth replay (dashboard 03).

The continuous engine walks every walker on the real road graph and already
interpolates each position along the edge geometry. This module keeps a few of
those positions for a handful of walkers, so a replay can draw computed paths
instead of straight synthetic lines, while the case row stays small.

Recording only reads positions. It draws no random numbers and changes no
walker, so the probability map and the checkpoint are identical with
recording on or off.

Data contract shared with the Dashboard repository (do not change the path or
shape without both sides): ``case.continuous_state['walker_traces']``::

    {"version": 1, "key": <continuous_state.key>, "channel": "personal",
     "total_walkers": 500, "until_minute": 240.0,
     "walkers": [{"walker_idx": 17, "strategy": "route_following",
                  "target": "일산호수공원", "starts_at_minute": 0.0,
                  "points": [[lat, lng, minute], ...]}]}

Points are real road positions, lat/lng rounded to 5 decimals, minutes to 1
decimal, strictly ascending in minute, at most 400 per walker. The key is
absent for legacy-engine cases and for cases recorded before this module.
"""
from __future__ import annotations

import logging
import math

log = logging.getLogger(__name__)

VERSION = 1
CHANNEL = 'personal'
# A point is kept when the walker moved this far from the last kept point...
MIN_STEP_M = 3.
# ...or this much time passed. The time rule is what records standing still.
MAX_GAP_MIN = 5.
SIMPLIFY_TOLERANCE_M = 3.
MAX_POINTS = 400
# Strategies whose initial target is an attachment place (Population.__init__).
TARGET_STRATEGIES = ('landmark_seeking', 'route_following')
_M_PER_DEG = 111_320.


def select(strategies, count, order=()):
    """Walker indices: largest-remainder seats over the assigned strategies.

    ``strategies`` is the strategy of each walker in creation order. Seats are
    proportional to how many walkers actually received each strategy (not to
    the prior's probabilities). Integer arithmetic keeps the remainders exact;
    ties go to the larger group, then to the engine's strategy order. Within a
    strategy the lowest indices are chosen, so the same input always gives the
    same walkers.
    """
    total = len(strategies)
    count = max(0, min(int(count), total))
    if not count:
        return []
    members = {}
    for idx, strategy in enumerate(strategies):
        members.setdefault(strategy, []).append(idx)
    order = list(order)
    kinds = sorted(members, key=lambda s: (order.index(s) if s in order else len(order), str(s)))
    seats = {s: count * len(members[s]) // total for s in kinds}
    remainders = {s: count * len(members[s]) % total for s in kinds}
    left = count - sum(seats.values())
    for s in sorted(kinds, key=lambda s: (-remainders[s], -len(members[s]), kinds.index(s)))[:left]:
        seats[s] += 1
    return sorted(i for s in kinds for i in members[s][:seats[s]])


def _meters(a, b):
    k = math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot((b[0] - a[0]) * _M_PER_DEG, (b[1] - a[1]) * _M_PER_DEG * k)


def simplify(points, tolerance=SIMPLIFY_TOLERANCE_M):
    """Douglas–Peucker on [lat, lng, minute] with the time-synchronized distance.

    Each dropped point is measured against the position interpolated *in time*
    between the kept neighbours (TD-TR). Plain spatial Douglas–Peucker would
    delete the repeated points of a walker standing still because they lie on
    the path, and a replay would then glide slowly through a stop. With the
    synchronized distance a stop's start and end stay, straight walking at the
    engine's constant speed still collapses to its corners.
    """
    n = len(points)
    if n < 3:
        return list(points)
    lat0, lng0 = points[0][0], points[0][1]
    k = math.cos(math.radians(lat0))
    xy = [((p[1] - lng0) * _M_PER_DEG * k, (p[0] - lat0) * _M_PER_DEG) for p in points]
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        s, e = stack.pop()
        if e - s < 2:
            continue
        ts, span = points[s][2], points[e][2] - points[s][2]
        (xs, ys), (xe, ye) = xy[s], xy[e]
        worst, at = -1., s
        for i in range(s + 1, e):
            r = (points[i][2] - ts) / span if span > 0 else 0.
            d = math.hypot(xy[i][0] - (xs + (xe - xs) * r), xy[i][1] - (ys + (ye - ys) * r))
            if d > worst:
                worst, at = d, i
        if worst > tolerance:
            keep[at] = True
            stack.append((s, at))
            stack.append((at, e))
    return [p for p, kept in zip(points, keep) if kept]


def thin(points, limit=None):
    """Evenly spaced subset by index; the first and last points always stay."""
    limit = MAX_POINTS if limit is None else limit
    n = len(points)
    if n <= limit:
        return list(points)
    if limit < 2:
        return [points[-1]][:limit]
    picks = sorted({(2 * i * (n - 1) + (limit - 1)) // (2 * (limit - 1)) for i in range(limit)})
    return [points[i] for i in picks]


def rounded(points):
    """Contract precision, with no two points at the same 0.1 minute.

    When rounding merges minutes the later position wins, because the final
    position is where the walker counts in the probability map. The start
    point is only replaced when it is also the last point.
    """
    out = []
    for n, (lat, lng, minute) in enumerate(points):
        q = [round(lat, 5), round(lng, 5), round(minute, 1)]
        if out and q[2] <= out[-1][2]:
            if len(out) > 1 or n == len(points) - 1:
                out[-1] = q
            continue
        out.append(q)
    return out


class Recorder:
    """Trace hook for ``Population``: records only the selected walkers.

    Build it right after the population exists (fresh or from a checkpoint),
    assign it as ``trace_hook``, advance, then call ``result``. ``previous`` is
    the committed ``walker_traces`` of the reused checkpoint, or None.
    """

    def __init__(self, pop, count, *, key, previous=None, strategy_order=()):
        particles = pop.particles
        self.key = key
        self.total = len(particles)
        self.selected = select([p.strategy for p in particles], count, strategy_order)
        self._index = {id(particles[i]): i for i in self.selected}
        self._raw = {i: [] for i in self.selected}
        self.failed = False
        start = max((particles[i].minute for i in self.selected), default=0.)
        self.previous = previous if self._continues(previous, start) else None
        # Read when recording begins: a sourced seek rule can later change the
        # walker's target, but the trace names its initial attachment place.
        self._meta = {}
        for i in self.selected:
            p = particles[i]
            loc = pop.position(p)
            self._raw[i].append((loc.lat, loc.lng, p.minute))
            self._meta[i] = {'strategy': p.strategy,
                             'target': p.target if p.strategy in TARGET_STRATEGIES else None,
                             'starts_at_minute': round(p.minute, 1)}

    def _continues(self, previous, start):
        if not isinstance(previous, dict):
            return False
        try:
            walkers = previous['walkers']
            return (previous.get('version') == VERSION and previous.get('key') == self.key
                    and previous.get('channel') == CHANNEL and previous.get('total_walkers') == self.total
                    and [w['walker_idx'] for w in walkers] == self.selected
                    and all(w['points'] for w in walkers)
                    and abs(float(previous['until_minute']) - start) <= .05 + 1e-9)
        except (KeyError, TypeError, ValueError):
            return False

    def wants(self, p):
        """Population skips the position lookup for every other walker."""
        return not self.failed and id(p) in self._index

    def __call__(self, p, loc):
        i = self._index.get(id(p))
        if i is None or self.failed:
            return
        try:
            point = (loc.lat, loc.lng, p.minute)
            raw = self._raw[i]
            last = raw[-1]
            # A skipped final position is added back in result().
            if point[2] - last[2] >= MAX_GAP_MIN - 1e-9 or _meters(last, point) >= MIN_STEP_M:
                raw.append(point)
        except Exception as exc:  # noqa: BLE001  a replay aid never changes or stops a prediction
            self._fail(exc)

    def _fail(self, exc):
        if not self.failed:
            log.warning('walker trace recording disabled for this run', exc_info=exc)
        self.failed = True

    def result(self, pop, until_minute):
        """The contract dict, or None when recording is off or failed."""
        if self.failed or not self.selected:
            return None
        try:
            previous = {w['walker_idx']: w for w in (self.previous or {}).get('walkers', [])}
            walkers = []
            for i in self.selected:
                p = pop.particles[i]
                raw = list(self._raw[i])
                loc = pop.position(p)
                final = (loc.lat, loc.lng, p.minute)
                if final[2] > raw[-1][2] + 1e-9 or (final[0], final[1]) != (raw[-1][0], raw[-1][1]):
                    raw.append(final)
                segment = rounded(simplify(raw))
                old = previous.get(i)
                if old is not None:
                    last_minute = old['points'][-1][2]
                    points = [list(x) for x in old['points']] + [q for q in segment if q[2] > last_minute]
                    entry = {'walker_idx': i, 'strategy': old['strategy'], 'target': old['target'],
                             'starts_at_minute': old['starts_at_minute']}
                else:
                    points = segment
                    entry = {'walker_idx': i, **self._meta[i]}
                entry['points'] = thin(points)
                walkers.append(entry)
            return {'version': VERSION, 'key': self.key, 'channel': CHANNEL,
                    'total_walkers': self.total, 'until_minute': round(float(until_minute), 1),
                    'walkers': walkers}
        except Exception as exc:  # noqa: BLE001  same isolation as __call__
            self._fail(exc)
            return None
