"""Evaluate typed personal conditions against bounded scene observations.

No text matching, invented OSM crowd levels, or mutation of shared road caches.
Unknown and conflicting observations never satisfy a positive OR negative condition.
"""
from datetime import timedelta
from app.geo.h3grid import haversine_km


def matches(clauses, signals):
    if not clauses:
        return True
    return any(all(type(signals.get(c.signal)) is bool and
                   signals[c.signal] == (c.state == "present") for c in clause)
               for clause in clauses if clause)


class SceneConditions:
    def __init__(self, net, observations, started_at):
        self.net, self.observations, self.started_at = net, observations or [], started_at
        self._nearby = {}

    def at(self, node, elapsed_minutes):
        if not self.observations or self.started_at is None:
            return {}
        if node not in self._nearby:
            location=self.net.node_location(node)
            self._nearby[node]=[o for o in self.observations
                if haversine_km(location,o.location)*1000 <= o.radius_m]
        return self._values(self._nearby[node],elapsed_minutes)

    def at_location(self,location,elapsed_minutes):
        """For a walker partway along a road, use its actual interpolated position."""
        if not self.observations or self.started_at is None:return {}
        nearby=[o for o in self.observations if haversine_km(location,o.location)*1000<=o.radius_m]
        return self._values(nearby,elapsed_minutes)

    def _values(self,nearby,elapsed_minutes):
        when=self.started_at+timedelta(minutes=elapsed_minutes)
        values={}
        for o in nearby:
            if o.valid_from <= when < o.valid_until:
                for signal in ('crowded','noisy'):
                    value=getattr(o,signal)
                    if value is not None:
                        values.setdefault(o.feature,{}).setdefault(signal,set()).add(value)
        return {feature:{key:next(iter(v)) if len(v)==1 else None
                         for key,v in signals.items()} for feature,signals in values.items()}
