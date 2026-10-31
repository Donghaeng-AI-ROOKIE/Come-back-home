"""Measure walker traces on real cases from a COPY of the production storage.db.

Read-only by construction:
- the database is opened with SQLite ``mode=ro`` and must be a copy
  (``sqlite3 storage.db ".backup /tmp/.../storage.db"``), never the live file;
- storage persistence stays off, so nothing is written anywhere;
- model credentials are blanked and every socket connection raises, so no
  K-EXAONE, Mi:dm, EXAONE, Supabase or OSM request can leave the process;
- closed or withdrawn cases are reopened only in memory to recompute them.

For each case the personal channel is recomputed from minute 0 to the stored
checkpoint horizon twice, traces off and on, with the stored seed and prior.
The report carries only sizes, counts, timings and equality checks, never
coordinates, place labels or other personal data.

Usage (inside the worker image, branch code mounted over /app/app):
    python scripts/measure_walker_traces.py --db /work/storage.db \\
        --case 204b970e5f6a --case 1761a4dea91d --out /work/walker_traces_report.json
"""
import os

# Keys and endpoints only. Model names stay: mind_policy.revision() hashes
# KEXAONE_MODEL, so blanking it marks every prepared policy 'stale' and the
# measurement silently falls back to the legacy engine (10-31 server run).
for _key in ('EXAONE_API_KEY', 'EXAONE_BASE_URL', 'MIDM_API_KEY', 'MIDM_BASE_URL',
             'KEXAONE_API_KEY', 'KEXAONE_BASE_URL'):
    os.environ[_key] = ''
os.environ['PERSIST_STORAGE'] = 'false'
os.environ['REVERSE_GEOCODE_ON_INTAKE'] = 'false'
os.environ['ROADNET_PRELOAD'] = 'false'

import argparse
import json
import math
import socket
import sqlite3
import statistics
import sys
import time
from collections import Counter
from pathlib import Path


def _no_network(*_a, **_k):
    raise RuntimeError('network disabled for read-only measurement')


socket.socket.connect = _no_network
socket.create_connection = _no_network

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.llm.initial_behavior import simulation_persona
from app.phase2 import continuous_prediction, pipeline
from app.schemas.case import Case, CaseStatus
from app.schemas.persona import Persona

PUBLIC_EXCLUDE = {'continuous_state', 'prior_context_key', 'alert_delivery'}


def _row(db, table, ident):
    rows = db.execute(f'SELECT id, data FROM {table} WHERE id = ? OR id LIKE ?',
                      (ident, ident + '%')).fetchall()
    if len(rows) != 1:
        raise SystemExit(f'{table}: {len(rows)} rows match {ident!r}')
    return rows[0]


def _road_distance(net):
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree
    south, west, north, east = net.coverage_bbox
    lat0, lng0 = (south + north) / 2, (west + east) / 2
    k = math.cos(math.radians(lat0))

    def local(lng, lat):
        return ((lng - lng0) * 111_320 * k, (lat - lat0) * 111_320)
    lines = []
    for u, v, data in net.graph.edges(data=True):
        coords = (list(data['geometry'].coords) if data.get('geometry') is not None else
                  [(net.graph.nodes[u]['x'], net.graph.nodes[u]['y']),
                   (net.graph.nodes[v]['x'], net.graph.nodes[v]['y'])])
        lines.append(LineString([local(x, y) for x, y in coords]))
    tree = STRtree(lines)

    def distance(lat, lng):
        point = Point(local(lng, lat))
        return point.distance(lines[tree.nearest(point)])
    return distance


def measure(db, ident, repeat, hours_override):
    case_id, raw = _row(db, 'cases', ident)
    stored = Case.model_validate(json.loads(raw))
    persona_id = stored.report.persona_id
    if not persona_id:
        return {'case': case_id[:12], 'skipped': 'no registered persona'}
    _, praw = _row(db, 'personas', persona_id)
    persona = Persona.model_validate(json.loads(praw))
    state = stored.continuous_state or {}
    particles = (state.get('checkpoint') or {}).get('particles') or []
    hours = hours_override or (max(p['minute'] for p in particles) / 60 if particles else None)
    if hours is None and stored.last_sim_at is not None:
        hours = (stored.last_sim_at - stored.lkp_time).total_seconds() / 3600
    if not hours or stored.prior is None:
        return {'case': case_id[:12], 'skipped': 'no stored prediction horizon or prior'}
    status_before = getattr(stored.status, 'value', str(stored.status))
    stored.status = CaseStatus.predicted  # in memory only: recompute a withdrawn case
    prior = stored.prior
    net, fallback = pipeline._load_roadnet(stored, prior, simulation_persona(persona, prior), hours)
    seed = state.get('seed')
    out = {'case': case_id[:12], 'stored_status': status_before, 'hours': round(hours, 3),
           'seed': seed, 'roadnet': net is not None, 'roadnet_fallback': fallback,
           'stored_has_walker_traces': 'walker_traces' in state,
           'stored_row_bytes': len(raw.encode()),
           'stored_public_response_bytes': len(stored.model_dump_json(exclude=PUBLIC_EXCLUDE).encode())}
    runs = {}
    for count in (0, settings.walker_trace_count or 8):
        settings.walker_trace_count = count
        times = []
        for _ in range(repeat):
            c = stored.model_copy(deep=True)
            c.continuous_state = {}  # walk from minute 0 to get the whole path
            t0 = time.perf_counter()
            bu, stat, q = continuous_prediction.run_pair(c, persona, prior, net, hours, seed=seed)
            times.append(time.perf_counter() - t0)
        runs[count] = (bu, stat, q, c, times)
    (bu0, st0, q0, c0, t_off), (bu1, st1, q1, c1, t_on) = runs.values()
    traces = c1.continuous_state.get('walker_traces')
    out.update(engine=q1.get('engine'), committed=q1.get('checkpoint_committed'),
               unresolved_mass=q1.get('unresolved_mass'),
               personal_map_identical=bu0 == bu1, statistical_map_identical=st0 == st1,
               quality_identical=q0 == q1,
               checkpoint_identical=(c0.continuous_state.get('checkpoint') ==
                                     c1.continuous_state.get('checkpoint')),
               key_identical=c0.continuous_state.get('key') == c1.continuous_state.get('key'),
               stored_key_matches_recomputed=state.get('key') == c1.continuous_state.get('key'),
               seconds_off=[round(x, 2) for x in t_off], seconds_on=[round(x, 2) for x in t_on],
               added_seconds_median=round(statistics.median(t_on) - statistics.median(t_off), 2),
               row_bytes_off=len(c0.model_dump_json().encode()),
               row_bytes_on=len(c1.model_dump_json().encode()),
               public_response_identical=(c0.model_dump_json(exclude=PUBLIC_EXCLUDE) ==
                                          c1.model_dump_json(exclude=PUBLIC_EXCLUDE)))
    if traces is None:
        out['walker_traces'] = None
        return out
    on_road = _road_distance(net)
    strategies = Counter(p['strategy'] for p in c1.continuous_state['checkpoint']['particles'])
    distances = [on_road(lat, lng) for w in traces['walkers'] for lat, lng, _ in w['points']]
    out['walker_traces'] = {
        'bytes': len(json.dumps(traces, ensure_ascii=False, separators=(',', ':')).encode()),
        'walkers': len(traces['walkers']), 'total_walkers': traces['total_walkers'],
        'until_minute': traces['until_minute'],
        'population_strategies': dict(sorted(strategies.items())),
        'selected': [{'walker_idx': w['walker_idx'], 'strategy': w['strategy'],
                      'has_target': w['target'] is not None, 'starts_at_minute': w['starts_at_minute'],
                      'points': len(w['points'])} for w in traces['walkers']],
        'points_total': sum(len(w['points']) for w in traces['walkers']),
        'road_distance_m_max': round(max(distances), 2),
        'road_distance_m_p95': round(sorted(distances)[int(.95 * (len(distances) - 1))], 2)}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--db', required=True, help='a COPY of storage.db')
    parser.add_argument('--case', action='append', required=True, help='case id or id prefix')
    parser.add_argument('--repeat', type=int, default=2)
    parser.add_argument('--hours', type=float, default=None, help='override the stored horizon')
    parser.add_argument('--out', default=None)
    args = parser.parse_args()
    if settings.persist_storage:
        raise SystemExit('persistence must stay off')
    db = sqlite3.connect(f'file:{Path(args.db).resolve()}?mode=ro', uri=True)
    report = {'walker_trace_count': settings.walker_trace_count or 8,
              'mc_num_walkers': settings.mc_num_walkers,
              'statistical_channel_definition': settings.statistical_channel_definition,
              'mind_policy_contract': settings.mind_policy_contract,
              'cases': [measure(db, ident, args.repeat, args.hours) for ident in args.case]}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text + '\n')


if __name__ == '__main__':
    main()
