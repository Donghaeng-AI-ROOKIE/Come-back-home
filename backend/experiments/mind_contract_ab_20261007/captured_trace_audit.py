"""Streaming oracle for the explicitly authored captured synthetic source.

This does not parse guardian text or implement a policy. It observes all
particles without changing their state, and checks the three fixed fixture
claims (6min/280m -> 5min rest; two wait windows; named noisy shop only).
"""
from collections import Counter
import math


class SourceTraceAudit:
    def __init__(self, scene, rules, start, shop, expected_particles):
        self.scene = scene
        self.rules = {r.id for r in rules}
        self.start = dict(start)
        self.shop = dict(shop)
        self.expected_particles = expected_particles
        self.states = {}
        self.checked = Counter()
        self.violations = Counter()
        self.examples = []

    def fail(self, index, reason, **values):
        self.violations[reason] += 1
        if len(self.examples) < 100:
            self.examples.append({'particle': index, 'reason': reason, **values})

    def observe(self, index, point):
        state = self.states.setdefault(index, {
            'prev': {'minute': 0., 'distance_m': 0., 'continuous_walk': 0., **self.start},
            'stationary_distance': 0., 'rest_start': None, 'rest_end': None,
            'personal_wait_minutes': 0., 'baseline_wait_minutes': 0.})
        prev = state['prev']
        begin, end = prev['minute'], point['minute']
        if end <= begin:
            self.fail(index, 'nonpositive_time_segment', start=begin, end=end)
        self.checked['segments'] += 1
        personal = point['rule_id'] in self.rules
        rest = personal and point['mode'] == 'rest'
        # The authored fixture says whichever threshold is reached first.
        # A missing rest command must fail even if no rest event was emitted.
        if point['mode'] in ('walk', 'seek'):
            self.checked['moving_segments_for_missed_rest'] += 1
            if (point['continuous_walk'] > 6+1e-4 or
                    point['distance_m']-state['stationary_distance'] > 280+1e-4):
                self.fail(index, 'walking_beyond_first_rest_threshold', minute=end)
        if self.scene == 'wait_release' and any(
                begin >= left-1e-4 and end <= right+1e-4 for left,right in ((40,90),(210,230))):
            self.checked['wait_window_segments_for_omission'] += 1
            # A previously started five-minute rest finishes first in the engine.
            # Count that explicitly, but movement during the wait window is wrong.
            if point['mode'] not in ('wait', 'rest'):
                self.fail(index, 'movement_during_required_wait', start=begin, end=end)
        if state['rest_start'] is not None and not rest:
            self.checked['completed_personal_rest_blocks'] += 1
            duration = state['rest_end'] - state['rest_start']
            if abs(duration - 5.) > 1e-4:
                self.fail(index, 'personal_rest_duration', duration=duration)
            state['rest_start'] = state['rest_end'] = None
        if rest:
            if state['rest_start'] is None:
                state['rest_start'] = begin
                self.checked['personal_rest_starts'] += 1
                if prev['continuous_walk'] < 6 - 1e-4 and prev['distance_m'] - state['stationary_distance'] < 280 - 1e-4:
                    self.fail(index, 'rest_before_either_threshold', minute=begin)
            state['rest_end'] = end
        if point['mode'] == 'wait':
            state['personal_wait_minutes' if personal else 'baseline_wait_minutes'] += end-begin
            if personal:
                self.checked['personal_wait_segments'] += 1
                valid = self.scene == 'wait_release' and any(
                    begin >= left-1e-4 and end <= right+1e-4 for left, right in ((40, 90), (210, 230)))
                if not valid:
                    self.fail(index, 'personal_wait_outside_window', start=begin, end=end)
        if personal and point['mode'] == 'avoid':
            self.checked['personal_avoid_segments'] += 1
            valid = self.scene == 'place_noise' and any(
                begin >= left-1e-4 and end <= right+1e-4 for left, right in ((0, 20), (80, 130)))
            if not valid:
                self.fail(index, 'avoid_outside_noise_window', start=begin, end=end)
            dy = (prev['lat'] - self.shop['lat']) * 111000
            dx = (prev['lng'] - self.shop['lng']) * 111000 * math.cos(math.radians(prev['lat']))
            if math.hypot(dx, dy) > 60.5:
                self.fail(index, 'avoid_outside_named_scope', distance_m=math.hypot(dx, dy))
        if point['mode'] in ('wait', 'rest'):
            state['stationary_distance'] = point['distance_m']
        state['prev'] = dict(point)

    def result(self, horizon):
        incomplete = [i for i,s in self.states.items() if abs(s['prev']['minute']-horizon)>1e-4]
        coverage = {
            'all_particles_observed': len(self.states) == self.expected_particles,
            'all_particles_reached_horizon': not incomplete and len(self.states) == self.expected_particles,
            'personal_rest_observed': self.checked['personal_rest_starts'] > 0,
            'personal_wait_observed': self.scene != 'wait_release' or self.checked['personal_wait_segments'] > 0,
            'personal_avoid_observed': self.scene != 'place_noise' or self.checked['personal_avoid_segments'] > 0,
        }
        return {'scene':self.scene, 'expected_particles':self.expected_particles, 'observed_particles':len(self.states),
            'checked':dict(self.checked), 'coverage':coverage,
            'violation_counts':dict(self.violations), 'violation_examples':self.examples,
            'violation_count':sum(self.violations.values()), 'incomplete_particles':incomplete,
            'right_censored_rest_blocks':sum(s['rest_start'] is not None for s in self.states.values()),
            'total_personal_wait_minutes':sum(s['personal_wait_minutes'] for s in self.states.values()),
            'total_baseline_wait_minutes':sum(s['baseline_wait_minutes'] for s in self.states.values()),
            'checks_passed':all(coverage.values()) and not self.violations,
            'limits':'one authored synthetic source; conditional rest/wait/avoid only; not clinical or location accuracy'}
