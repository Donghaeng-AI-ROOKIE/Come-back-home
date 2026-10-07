"""Persistent, offline candidate executor over the existing RoadNetwork interface.

This is a probe, not a replacement for the calibrated prior/radius pipeline. The
caller supplies a decision provider and explicit timing assumptions. No API calls.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import math
import random
from copy import deepcopy
from app.phase2 import gauges
from app.phase2.environment_conditions import SceneConditions
from app.phase2.simulation import _bearing, _kappa
from .contract import State, context_for, validate_decision


@dataclass(frozen=True)
class RuntimePolicy:
    rest_minutes: float
    reassess_minutes: float
    # Uses the existing engine's fatigue recovery convention; not clinical calibration.
    rest_fatigue_retention: float = .4
    avoidance_distance_scale_m: float = 60.

    def __post_init__(self):
        if not (0 < self.rest_minutes < float('inf') and
                0 < self.reassess_minutes < float('inf') and
                0 <= self.rest_fatigue_retention <= 1 and
                0 < self.avoidance_distance_scale_m < float('inf')):
            raise ValueError('invalid experimental timing/avoidance policy')


class WalkingSession:
    def __init__(self, net, persona, prior, start, started_at: datetime, provider,
                 *, policy: RuntimePolicy, case_id='synthetic', observations=(), seed=42):
        self.net,self.persona,self.prior,self.provider=net,persona,prior,provider
        self.policy,self.case_id,self.started_at=policy,case_id,started_at
        self.scene=SceneConditions(net,list(observations),started_at)
        self.rng=random.Random(seed)
        self.node=net.nearest_node(start)
        self.g=gauges.Gauges(gauges.config_for(persona))
        self.distance=0.;self.mind_confusion=None;self.rest_end=None;self.hold_until=0.;self.next_review=0.
        self.action='continue';self.travel_action='roam';self.avoid_feature=None
        self.target=None;self.target_reached=False;self.last_rest_end=None
        self.labels={ap.label:net.nearest_node(ap.location) for ap in persona.attraction_points}
        self.edge_to=None;self.edge_remaining=0.;self.edge_length=0.
        self.heading=self.rng.uniform(-math.pi,math.pi)
        self.history=[];self.decisions=[];self.path=[{'minute':0.,'node':self.node}]
        self.trigger='initial';self.previous_environment=None;self.last_fatigue_band=0
        self.terminated=False;self.termination_reason=None

    def _event(self,kind,**extra):
        self.history.append({'kind':kind,'elapsed_minutes':self.g.elapsed_min,**extra})

    def state(self):
        return State(elapsed_minutes=self.g.elapsed_min,distance_m=self.distance,
                     fatigue=self.g.F,confusion=min(1.,self.g.C),anxiety=self.g.A,
                     interpreted_confusion=self.mind_confusion,
                     current_action=self.action,target_label=self.target,
                     target_reached=self.target_reached,last_rest_end_minutes=self.last_rest_end,
                     recent_events=deepcopy(self.history[-8:]))

    def context(self,trigger):
        return context_for(self.persona,self.prior,self.state(),case_id=self.case_id,
                           started_at=self.started_at,trigger=trigger,
                           env=self.net.env(self.node),
                           observations=self.scene.at(self.node,self.g.elapsed_min))

    def _environment_key(self):
        env=self.net.env(self.node)
        nearby=tuple((f,env.get(f+'_m') is not None and env[f+'_m']<=limit)
                     for f,limit in [('water',100),('market',60),('park',60),('forest',60)])
        observations=self.scene.at(self.node,self.g.elapsed_min)
        signals=tuple((f,s,observations.get(f,{}).get(s))
                      for f in ['water','market','park','forest'] for s in ['noisy','crowded'])
        return nearby,signals

    def _decide(self,reason):
        context=self.context(reason)
        # Provider exceptions are observable. No heuristic is relabeled as model output.
        decision=validate_decision(self.provider(context),context)
        self.decisions.append({'minute':self.g.elapsed_min,'context':context,
                               'decision':decision.model_dump(mode='json')})
        if decision.goal_operation=='set':
            self.target=decision.goal_label;self.target_reached=False
        elif decision.goal_operation=='clear':
            self.target=None;self.target_reached=False
        if decision.confusion_level != 'unknown':
            self.mind_confusion={'high':.85,'medium':.6,'low':.35}[decision.confusion_level]
        action=decision.action
        if action=='continue':action=self.travel_action
        if action in ('seek','roam','avoid'):
            self.travel_action=action
        self.action=action
        if action=='avoid':self.avoid_feature=decision.avoid_feature
        elif action not in ('rest','stay'):self.avoid_feature=None
        if action=='rest':self.hold_until=self.g.elapsed_min+self.policy.rest_minutes
        elif action=='stay':self.hold_until=self.g.elapsed_min+self.policy.reassess_minutes
        self.next_review=self.g.elapsed_min+self.policy.reassess_minutes
        self._event('decision',action=self.action,reason=reason,target=self.target)
        self.previous_environment=self._environment_key()
        self.last_fatigue_band=2 if self.g.F>=.7 else 1 if self.g.F>=.4 else 0
        self.trigger=None

    def _choose_edge(self):
        neighbors=self.net.neighbors(self.node)
        if not neighbors:
            self.terminated=True;self.termination_reason='no_road_neighbor'
            self._event('blocked');return
        here=self.net.node_location(self.node)
        if self.action=='avoid':
            # Retain the destination without steering into the avoided feature.
            desired=self.heading
        elif self.target and not self.target_reached:
            desired=_bearing(here,self.net.node_location(self.labels[self.target]))
        elif self.action=='roam':desired=self.rng.uniform(-math.pi,math.pi)
        else:desired=self.heading
        weights=[]
        for nb in neighbors:
            w=1. if self.action=='avoid' else math.exp(_kappa(self.mind_confusion if self.mind_confusion is not None else min(1.,self.g.C))*math.cos(_bearing(here,self.net.node_location(nb))-desired))
            w*=gauges.road_preference(self.net.edge_attrs(self.node,nb),self.persona)
            # Explicit avoid action replaces the static personal environmental tilt,
            # preventing the same personal reaction from being counted twice here.
            if self.action=='avoid' and self.avoid_feature:
                distance=self.net.env(nb).get(self.avoid_feature+'_m')
                current_distance=self.net.env(self.node).get(self.avoid_feature+'_m')
                if distance is not None and current_distance is not None:
                    delta=(distance-current_distance)/self.policy.avoidance_distance_scale_m
                    w*=math.exp(max(-3.,min(delta,3.)))
            else:
                w*=gauges.env_response_weight(self.net.env(nb),self.persona,
                    conditions=self.scene.at(nb,self.g.elapsed_min))
            weights.append(w)
        self.edge_to=self.rng.choices(neighbors,weights=weights)[0]
        self.edge_length=float(self.net.edge_attrs(self.node,self.edge_to).get('length',30.))
        if not 0 < self.edge_length < float('inf'):raise ValueError('invalid edge length')
        self.edge_remaining=self.edge_length
        self.heading=_bearing(here,self.net.node_location(self.edge_to))

    def advance_to(self,minute):
        if not self.g.elapsed_min <= minute < float('inf'):raise ValueError('time must be finite and monotone')
        while self.g.elapsed_min < minute-1e-9:
            if self.terminated:
                self.g.elapsed_min=minute;break
            if self.action in ('rest','stay') and self.g.elapsed_min < self.hold_until-1e-9:
                self.g.elapsed_min=min(minute,self.hold_until)
                if self.g.elapsed_min >= self.hold_until-1e-9:
                    if self.action=='rest':
                        self.g.F*=self.policy.rest_fatigue_retention
                        self.last_rest_end=self.g.elapsed_min
                        self._event('rest_complete');self.trigger='rest_complete'
                    else:self.trigger='stay_review'
                    self.action='continue'
                continue
            if self.edge_to is None:
                if self.target and not self.target_reached and self.node==self.labels[self.target]:
                    self.target_reached=True;self.trigger=self.trigger or 'target_arrived';self._event('target_arrived',target=self.target)
                environmental=self._environment_key()
                fatigue_band=2 if self.g.F>=.7 else 1 if self.g.F>=.4 else 0
                if self.previous_environment is not None and environmental!=self.previous_environment:
                    self.trigger=self.trigger or 'environment_changed'
                if fatigue_band!=self.last_fatigue_band:self.trigger=self.trigger or 'fatigue_changed'
                if self.g.elapsed_min>=self.next_review-1e-9:self.trigger=self.trigger or 'scheduled_review'
                if self.trigger:self._decide(self.trigger)
                if self.action in ('rest','stay'):continue
                self._choose_edge()
                if self.terminated:continue
            speed=gauges.walk_speed(self.persona)
            dt=min(minute-self.g.elapsed_min,self.edge_remaining/speed)
            moved=dt*speed
            self.g.step(dt,terrain=gauges.terrain_difficulty(self.net.edge_attrs(self.node,self.edge_to)),
                        fatigue_mult=gauges.fatigue_mult(self.persona),
                        unfamiliarity=gauges.unfamiliarity(self.net.node_location(self.node),
                            [self.persona.home]+[a.location for a in self.persona.attraction_points]),
                        hostile=gauges.hostile_exposure(self.net.env(self.node),self.persona))
            self.distance+=moved;self.edge_remaining-=moved
            if self.edge_remaining<=1e-7:
                self.node=self.edge_to;self.edge_to=None;self.edge_remaining=0.
                self.path.append({'minute':self.g.elapsed_min,'node':self.node})
        return self.snapshot()

    def snapshot(self):
        # Nodes + edge offset represent an in-progress road traversal without snapping
        # the walker forward to a node at an earlier hour.
        return {'state':self.state().model_dump(mode='json'),'node':self.node,
                'edge_to':self.edge_to,'edge_progress_m':self.edge_length-self.edge_remaining if self.edge_to is not None else 0.,
                'termination_reason':self.termination_reason,
                'path':deepcopy(self.path),'history':deepcopy(self.history)}
