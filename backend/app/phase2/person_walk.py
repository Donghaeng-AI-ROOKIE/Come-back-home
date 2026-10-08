"""Continuous personal walkers with persisted clock and explicit uncertainty.

No LLM call in a particle loop. K interprets evidence into a versioned policy;
this executor reevaluates its typed conditions using the current world state.
Both channels can share this clock. A policy-free channel still shares initial
personal traits; it is not a population-only statistical baseline.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass,field,asdict
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from bisect import bisect_right
import math,random,hashlib,json
from app.geo.h3grid import haversine_km,cell_of
from app.llm import mind_policy
from app.llm.initial_behavior import simulation_persona
from app.phase2 import gauges,radius
from app.phase2.environment_conditions import SceneConditions
from app.phase2.simulation import _bearing,_kappa,STRATEGIES
from app.schemas.common import GeoPoint
from app.schemas.prediction import MindState

VERSION='continuous-person-v4'


@dataclass(frozen=True)
class BaselineRestPolicy:
    """Research assumption, not a measured individual rest prescription.

    Reuse the existing fatigue logistic curve and recovery fraction, but evaluate
    it once per simulation minute rather than once per road edge. Rest duration
    remains provisional. Explicit responses to physical conditions take
    precedence. General movement intent does not imply unlimited endurance.
    """
    enabled: bool = True
    minutes: float = 5.
    recovery_fraction: float = .4

    def __post_init__(self):
        if type(self.enabled) is not bool or not 0 < self.minutes <= 60:
            raise ValueError('invalid population rest assumption')
        if not 0 <= self.recovery_fraction < 1:
            raise ValueError('invalid fatigue recovery assumption')

def _tuples(value):
    return tuple(_tuples(v) for v in value) if isinstance(value,list) else value

@dataclass
class Particle:
    node:int
    seed:int
    minute:float=0.
    edge_to:int|None=None
    edge_remaining:float=0.
    edge_length:float=0.
    previous_node:int|None=None
    heading:float=0.
    mode:str='walk'
    strategy:str='random_walk'
    target:str|None=None
    arrived:bool=False
    recognized:bool|None=None
    recognition_source:str='unobserved'
    completed_goals:list[str]=field(default_factory=list)
    avoid_feature:str|None=None
    avoid_labels:list[str]=field(default_factory=list)
    hold_until:float=0.
    fatigue:float=0.
    confusion:float=0.
    hostile:float=0.
    walking:float=0.
    continuous_walk:float=0.
    rest:float=0.
    waiting:float=0.
    distance:float=0.
    distance_since_rest:float=0.
    rule_minutes:dict[str,float]=field(default_factory=dict)
    selection_signature:str=''
    selected:int=0
    uncertain_minutes:float=0.
    baseline_minutes:float=0.
    hold_rule_id:str|None=None
    last_uncertain:bool=False
    last_baseline:bool=False
    blocked:bool=False
    events:list=field(default_factory=list)
    rng_state:object=None
    next_population_rest_check:float=1.
    population_rest_minutes:float=0.

class Population:
    def __init__(self,net,persona,prior,policy,start,started_at,*,count=500,seed=42,
                 environment_observations=(),behavior_observations=(),mind=None,checkpoint=None,trace_hook=None,
                 rest_policy=None):
        if net is None or not hasattr(net,'graph'):raise ValueError('continuous walking requires an OSM road graph')
        if count<=0:raise ValueError('positive walker count required')
        self.trace_hook=trace_hook
        self.net=net;self.persona=simulation_persona(persona,prior);self.prior=prior
        self.policy=policy;self.start=start;self.started_at=started_at;self.seed=seed
        # Historical stored naive timestamps are Korean local time. Never let
        # the deployment host's timezone change clock-conditioned behavior.
        self.clock_origin=(started_at.replace(tzinfo=ZoneInfo('Asia/Seoul'))
                           if started_at.tzinfo is None else started_at.astimezone(ZoneInfo('Asia/Seoul')))
        self.observations=list(behavior_observations);self.scene=SceneConditions(net,environment_observations,started_at)
        self.rest_policy=rest_policy if rest_policy is not None else BaselineRestPolicy()
        self.observation_boundaries=sorted({(time-started_at).total_seconds()/60
            for observation in self.observations+self.scene.observations
            for time in (observation.valid_from,observation.valid_until) if time>started_at})
        self.locations={n:net.node_location(n) for n in net.graph.nodes}
        self.neighbors={n:net.neighbors(n) for n in net.graph.nodes}
        self.attrs={(n,v):net.edge_attrs(n,v) for n,ns in self.neighbors.items() for v in ns}
        self.goals={a.label:net.nearest_node(a.location) for a in self.persona.attraction_points}
        self.goal_locations={a.label:a.location for a in self.persona.attraction_points}
        self.familiar=[self.persona.home]+list(self.goal_locations.values())
        self.route_scores={r.route:r.score for r in self.persona.route_familiarity}
        self.routine_labels={a.label for a in self.persona.attraction_points if a.origin_slot=='routine_destinations'}
        self.cfg=gauges.config_for(self.persona);self.speed=gauges.walk_speed(self.persona)
        self.cap=radius.statistical_p95_km(prior.radius_lognormal)
        self.mind_confusion=(mind.confusion if mind is not None and mind.changed
                             else MindState().confusion)
        if not math.isfinite(self.mind_confusion) or not 0<=self.mind_confusion<=1:
            raise ValueError('invalid directional state')
        self.direction_state_source=('updated_mind_state' if mind is not None and mind.changed
                                     else 'unobserved_default_0.5')
        self._near_cache={};self._direction_cache={};self._policy_cache={}
        self.coverage_bbox=getattr(net,'coverage_bbox',None)
        if self.coverage_bbox is None:raise ValueError('map coverage bounds missing')
        for point in [start]+list(self.goal_locations.values()):
            if haversine_km(point,self.locations[net.nearest_node(point)])>.15:
                raise ValueError('start or personal goal outside map coverage')
        self.policy_digest=hashlib.sha256(policy.model_dump_json().encode()).hexdigest()
        if checkpoint:
            if checkpoint['version']!=VERSION or checkpoint['policy_digest']!=self.policy_digest:
                raise ValueError('stale continuous checkpoint')
            if checkpoint.get('rest_policy')!=asdict(self.rest_policy):
                raise ValueError('population rest assumptions changed')
            self.particles=[Particle(**p) for p in checkpoint['particles']]
            if len(self.particles)!=count:raise ValueError('walker count changed')
        else:
            node=net.nearest_node(start);self.particles=[]
            weights=[max(0.,prior.strategy_probs.get(s,0.)) for s in STRATEGIES]
            if not sum(weights):raise ValueError('empty movement prior')
            labels=list(self.goals);goal_weights=[max(0.,prior.attraction_weights.get(k,0.)) for k in labels]
            for i in range(count):
                rng=random.Random(seed+i*100003)
                strategy=rng.choices(STRATEGIES,weights=weights)[0]
                target=rng.choices(labels,weights=goal_weights)[0] if labels and sum(goal_weights)>0 and strategy in ('landmark_seeking','route_following') else None
                p=Particle(node,seed+i*100003,heading=rng.uniform(-math.pi,math.pi),strategy=strategy,target=target)
                p.rng_state=rng.getstate();self.particles.append(p)

    def checkpoint(self):
        return {'version':VERSION,'policy_digest':self.policy_digest,'seed':self.seed,
                'rest_policy':asdict(self.rest_policy),
                'particles':[asdict(p) for p in self.particles]}

    def _event(self,p,kind,**extra):
        p.events.append({'minute':p.minute,'kind':kind,**extra})
        p.events=p.events[-24:]

    def position(self,p):
        a=self.locations[p.node]
        if p.edge_to is None:return a
        b=self.locations[p.edge_to];fraction=1-p.edge_remaining/p.edge_length
        geometry=self.attrs[p.node,p.edge_to].get('geometry')
        if geometry is not None:
            first,last=geometry.coords[0],geometry.coords[-1]
            d1=(first[0]-a.lng)**2+(first[1]-a.lat)**2;d2=(last[0]-a.lng)**2+(last[1]-a.lat)**2
            point=geometry.interpolate(1-fraction if d2<d1 else fraction,normalized=True)
            return GeoPoint(lat=point.y,lng=point.x)
        return GeoPoint(lat=a.lat+(b.lat-a.lat)*fraction,lng=a.lng+(b.lng-a.lng)*fraction)

    def facts(self,p):
        now=self.started_at+timedelta(minutes=p.minute)
        local_clock=self.clock_origin+timedelta(minutes=p.minute)
        f={k:None for k in mind_policy.BOOLEAN_FACTS}
        # The same provisional high band used by gauges.report; these are latent
        # simulation states, not observations of the missing person's feelings.
        anxiety=self.cfg.k_a1*p.confusion+self.cfg.k_a2*p.hostile
        home_pull=self.cfg.k_h1*p.minute+self.cfg.k_h2*p.confusion
        f.update(fatigue_high=p.fatigue>=.7,anxiety_high=anxiety>=.7,home_pull_high=home_pull>=.7,
            physical_arrival=p.arrived,target_recognized=p.recognized,is_walking=p.mode in ('walk','avoid','seek'),
            continuous_walk_minutes=p.continuous_walk,distance_since_rest_m=p.distance_since_rest,
            clock_hour=local_clock.hour+local_clock.minute/60+local_clock.second/3600)
        conditions=(self.scene.at(p.node,p.minute) if p.edge_to is None
                    else self.scene.at_location(self.position(p),p.minute))
        for feature,signals in conditions.items():
            for signal,value in signals.items():
                if feature+'.'+signal in f:f[feature+'.'+signal]=value
        values={}
        for obs in self.observations:
            # These are typed, bounded observations, never extracted by text matching.
            if obs.valid_from<=now<obs.valid_until:
                values.setdefault(obs.fact,set()).add(obs.value)
        for name,vs in values.items():f[name]=next(iter(vs)) if len(vs)==1 else None
        return f

    def near(self,p):
        # Scope is a declared geometric approximation, not proof of perception.
        if p.edge_to is None and p.node in self._near_cache:return self._near_cache[p.node]
        loc=self.position(p)
        labels=[name for name,point in self.goal_locations.items() if haversine_km(loc,point)*1000<=60]
        features={}
        for feature,limit in [('market',60),('park',60),('forest',60),('water',100)]:
            distance=self.net.env(p.node).get(feature+'_m')
            if p.edge_to is not None:
                other=self.net.env(p.edge_to).get(feature+'_m')
                fraction=1-p.edge_remaining/p.edge_length
                distance=(distance+(other-distance)*fraction
                          if distance is not None and other is not None else None)
            features[feature]=None if distance is None else distance<=limit
        result=(labels,features)
        if p.edge_to is None:self._near_cache[p.node]=result
        return result

    def _baseline(self,p,rng,facts):
        # Reaching or recognizing a place does not establish a stopping response.
        # Only sourced personal rules change that response; otherwise keep the
        # existing movement prior and mark its contribution in quality metadata.
        if p.strategy=='staying_put':return 'wait',30.,None,None
        return 'walk',None,None,None

    def _population_rest(self,p):
        """No guardian word matching or invented personal endurance capacity.

        An independent per-person, per-minute draw makes the probability
        independent of road-node count and repeated API/checkpoint requests.
        This is a declared population hypothesis, not a clinical calibration.
        """
        if not self.rest_policy.enabled or p.minute < p.next_population_rest_check-1e-8:
            return False
        minute=math.floor(p.minute+1e-8)
        p.next_population_rest_check=minute+1.
        rng=random.Random(p.seed ^ (minute*1000003) ^ 0x5E571)
        return rng.random() < gauges.p_trigger(p.fatigue,self.cfg.theta_f,self.cfg.beta_f)

    @staticmethod
    def _explicit_physical_walk(rule,facts):
        """Typed model interpretation, never a keyword search in guardian text.

        'Walk when lost' says nothing about endurance. A supported branch that
        explicitly describes walking under fatigue/pain or a walking limit does.
        Do not use an inactive OR clause to override physical rest.
        """
        if rule is None or rule.action!='walk':return False
        physical={'fatigue_high','continuous_walk_minutes','distance_since_rest_m'}
        return any(mind_policy.truth([clause],facts) is not False and
                   any(a.fact in physical or (a.fact=='pain_observed' and a.value is True)
                       for a in clause) for clause in rule.when)

    def _policy_options(self,p,f,labels,features):
        """Default policy evaluation; contextual executors can bind typed facts."""
        signature_key=tuple(mind_policy.atom_value(a,f) for r in self.policy.rules for c in r.when for a in c),tuple(labels),tuple(features.items())
        if signature_key not in self._policy_cache:
            self._policy_cache[signature_key]=mind_policy.possibilities(self.policy,f,near_places=labels,near_features=features)
        return self._policy_cache[signature_key]

    def _decide(self,p,rng):
        f=self.facts(p);labels,features=self.near(p)
        if p.mode=='rest' and p.minute<p.hold_until-1e-8:
            return p.last_uncertain,p.last_baseline
        # Waiting is reviewed every clock step, so a newly arrived family does not
        # have to wait out a made-up 30 minute commitment.
        options,unknown=self._policy_options(p,f,labels,features)
        # A repeated desire is not proof of repeatedly forgetting a just-visited place.
        options=[r for r in options if r is None or r.action!='seek' or r.goal_label not in p.completed_goals]
        if not options:options=[None]
        signature=json.dumps([[(r.id if r else None) for r in options],unknown,p.arrived,p.target],ensure_ascii=False)
        if signature!=p.selection_signature:
            p.selection_signature=signature;p.selected=rng.randrange(len(options))
        rule=options[p.selected];uncertain=len(options)>1
        baseline=rule is None
        if baseline:
            mode,hold,goal,feature=self._baseline(p,rng,f);scope=[];rid=None
        else:
            mode=rule.action;hold=rule.hold_minutes;goal=rule.goal_label;feature=rule.feature;scope=rule.place_labels;rid=rule.id
        # Keep movement intent, but do not interpret it as physical endurance.
        # An explicit physical walk response, rest or wait remains authoritative.
        # The source of a general fatigue rest is recorded separately.
        can_rest=mode in ('walk','seek','avoid') and not self._explicit_physical_walk(rule,f)
        if can_rest and self._population_rest(p):
            self._event(p,'population_rest_start',fatigue=p.fatigue,
                        interrupted_action=mode,interrupted_rule_id=rid,
                        assumption='existing_curve_one_check_per_minute_provisional')
            mode='rest';hold=self.rest_policy.minutes;baseline=True;rid=None
        old_mode=p.mode;old_feature=p.avoid_feature
        if goal is not None and goal!=p.target:
            p.target=goal;p.arrived=False;p.recognized=None;p.recognition_source='unobserved'
        if mode=='rest':hold=hold or 5.
        if mode=='wait':hold=hold or 30.
        p.mode=mode;p.avoid_feature=feature;p.avoid_labels=list(scope)
        if mode=='avoid' and not scope and not math.isfinite(self._feature_distance(p,p.node)):
            p.blocked=True;self._event(p,'unmapped_avoidance',feature=feature)
            return uncertain,baseline
        p.last_uncertain=uncertain;p.last_baseline=baseline;p.hold_rule_id=rid
        if hold is not None:p.hold_until=p.minute+hold
        if mode in ('rest','wait'):
            p.continuous_walk=0.;p.distance_since_rest=0.
        if old_mode!=mode or old_feature!=feature:
            self._event(p,'action',action=mode,rule_id=rid,source='population_prior' if baseline else 'K_person_policy',
                        uncertain=uncertain,unknown_facts=unknown,goal=p.target)
        # Turning around mid-edge is permitted on a bidirectional walking edge.
        if mode=='avoid' and p.edge_to is not None and (old_mode!='avoid' or old_feature!=feature):
            u,v=p.node,p.edge_to
            if (v,u) in self.attrs and self._feature_distance(p,v)<self._feature_distance(p,u):
                progress=p.edge_length-p.edge_remaining
                p.node,p.edge_to=v,u;p.edge_remaining=progress;p.previous_node=None
                p.heading=_bearing(self.locations[v],self.locations[u]);self._event(p,'avoid_turn')
        return uncertain,baseline

    def _feature_distance(self,p,node):
        if p.avoid_labels:
            return min(haversine_km(self.locations[node],self.goal_locations[x])*1000 for x in p.avoid_labels)
        value=self.net.env(node).get((p.avoid_feature or '')+'_m')
        return float('inf') if value is None else value

    def _edge(self,p,rng):
        neighbors=self.neighbors[p.node]
        if not neighbors:p.blocked=True;self._event(p,'road_blocked');return
        here=self.locations[p.node]
        south,west,north,east=self.coverage_bbox
        # Reaching a downloaded boundary is censored, never treated as a true
        # cul-de-sac. Do not redistribute that walker's probability to survivors.
        if min((here.lat-south)*111000,(north-here.lat)*111000,
               (here.lng-west)*111000*math.cos(math.radians(here.lat)),
               (east-here.lng)*111000*math.cos(math.radians(here.lat)))<50:
            p.blocked=True;self._event(p,'map_boundary');return
        if p.mode=='avoid':desired=p.heading
        elif p.target and not p.arrived:desired=_bearing(here,self.locations[self.goals[p.target]])
        elif p.strategy=='backtracking':desired=_bearing(here,self.start)
        elif p.strategy=='random_walk' or p.arrived:desired=rng.uniform(-math.pi,math.pi)
        else:desired=p.heading
        known=self.route_scores.get(p.target)
        if known is None and p.target in self.routine_labels:known=gauges.ROUTINE_DEFAULT_FAMILIARITY
        # Only a supported familiar route can use graph shortest-path guidance.
        # Unfamiliar travellers retain the existing local direction kernel.
        distances=None
        if known is not None and known>0 and p.target and not p.arrived and p.mode!='avoid':
            if p.target not in self._direction_cache:
                import networkx as nx
                self._direction_cache[p.target]=nx.single_source_dijkstra_path_length(
                    self.net.graph.reverse(copy=False),self.goals[p.target],weight='length')
            distances=self._direction_cache[p.target]
        weights=[]
        for nb in neighbors:
            attrs=self.attrs[p.node,nb]
            if haversine_km(self.start,self.locations[nb])>self.cap:
                weights.append(0.);continue
            # C is an unbounded accumulated trigger gauge, not a 0..1 estimate
            # of directional impairment. Feeding C into kappa made all walkers
            # converge to maximum dispersion merely through elapsed time.
            w=1. if p.mode=='avoid' else math.exp(_kappa(self.mind_confusion)*math.cos(_bearing(here,self.locations[nb])-desired))
            if distances is not None and p.node in distances and nb in distances:
                improvement=(distances[p.node]-distances[nb])/max(float(attrs.get('length',30)),1.)
                w*=math.exp(max(-2.,min(2.,improvement*2*known)))
            w*=gauges.road_preference(attrs,self.persona)
            if p.mode=='avoid':
                a=self._feature_distance(p,p.node);b=self._feature_distance(p,nb)
                if math.isfinite(a) and math.isfinite(b):w*=math.exp(max(-3.,min(3.,(b-a)/60.)))
            else:w*=gauges.env_response_weight(self.net.env(nb),self.persona,conditions=self.scene.at(nb,p.minute))
            if nb==p.previous_node and len(neighbors)>1:w*=.2
            weights.append(w)
        if not sum(weights):p.blocked=True;self._event(p,'support_boundary');return
        p.edge_to=rng.choices(neighbors,weights=weights)[0]
        p.edge_length=float(self.attrs[p.node,p.edge_to].get('length',30.))
        if not 0<p.edge_length<float('inf'):raise ValueError('invalid road length')
        p.edge_remaining=p.edge_length;p.heading=_bearing(here,self.locations[p.edge_to])

    def _advance(self,p,end):
        if end<p.minute-1e-8:raise ValueError('cannot reverse a live particle clock')
        rng=random.Random();rng.setstate(_tuples(p.rng_state))
        while p.minute<end-1e-8 and not p.blocked:
            if p.edge_to is None and p.target and not p.arrived and p.node==self.goals[p.target]:
                p.arrived=True;p.completed_goals.append(p.target)
                self._event(p,'physical_arrival',goal=p.target,recognized=None)
            uncertain,baseline=self._decide(p,rng)
            if p.blocked:break
            boundary=min(end,math.floor(p.minute+1e-7)+1.)
            next_observation=bisect_right(self.observation_boundaries,p.minute+1e-8)
            if next_observation<len(self.observation_boundaries):
                boundary=min(boundary,self.observation_boundaries[next_observation])
            # Stop at supplied continuous-walking limits, including fractional values.
            if p.mode in ('walk','avoid','seek'):
                for rule in self.policy.rules:
                    for clause in rule.when:
                        for a in clause:
                            if a.fact=='continuous_walk_minutes' and a.op in ('gte','lt') and a.value>p.continuous_walk+1e-8:
                                boundary=min(boundary,p.minute+float(a.value)-p.continuous_walk)
                            elif a.fact=='distance_since_rest_m' and a.op in ('gte','lt') and a.value>p.distance_since_rest+1e-8:
                                boundary=min(boundary,p.minute+(float(a.value)-p.distance_since_rest)/self.speed)
            dt=boundary-p.minute
            if p.mode in ('wait','rest'):
                dt=min(dt,p.hold_until-p.minute)
                if dt<=1e-8:raise ValueError('nonadvancing hold')
                if p.mode=='rest':
                    p.rest+=dt
                    if baseline:p.population_rest_minutes+=dt
                else:p.waiting+=dt
                p.minute+=dt
                if p.minute>=p.hold_until-1e-8 and p.mode=='rest':
                    p.fatigue*=self.rest_policy.recovery_fraction;self._event(p,'rest_complete')
            else:
                if p.edge_to is None:self._edge(p,rng)
                if p.blocked:break
                dt=min(dt,p.edge_remaining/self.speed)
                known=None
                if p.target and not p.arrived and p.mode!='avoid':
                    known=self.route_scores.get(p.target)
                    if known is None and p.target in self.routine_labels:known=gauges.ROUTINE_DEFAULT_FAMILIARITY
                g=gauges.Gauges(self.cfg);g.F=p.fatigue;g.C=p.confusion;g.E=p.hostile;g.elapsed_min=p.minute
                g.step(dt,terrain=gauges.terrain_difficulty(self.attrs[p.node,p.edge_to]),
                    fatigue_mult=gauges.fatigue_mult(self.persona),
                    unfamiliarity=gauges.unfamiliarity(self.locations[p.node],self.familiar,known_score=known),
                    hostile=gauges.hostile_exposure(self.net.env(p.node),self.persona),
                    dark=self.facts(p).get('dark_observed') is True)
                p.minute=g.elapsed_min;p.fatigue=g.F;p.confusion=g.C;p.hostile=g.E
                moved=dt*self.speed;p.distance+=moved;p.distance_since_rest+=moved;p.walking+=dt;p.continuous_walk+=dt
                p.edge_remaining-=moved
                if p.edge_remaining<=1e-7:
                    p.previous_node=p.node;p.node=p.edge_to;p.edge_to=None;p.edge_remaining=0.
            if uncertain:p.uncertain_minutes+=dt
            if baseline:p.baseline_minutes+=dt
            if p.hold_rule_id:
                p.rule_minutes[p.hold_rule_id]=p.rule_minutes.get(p.hold_rule_id,0.)+dt
            if self.trace_hook is not None:self.trace_hook(p,self.position(p))
        p.rng_state=rng.getstate()

    def advance_to(self,minute):
        if not 0<=minute<float('inf'):raise ValueError('invalid prediction horizon')
        for p in self.particles:self._advance(p,minute)
        return self.distribution(minute)

    def distribution(self,minute):
        cells={};unresolved=0;reasons={}
        for p in self.particles:
            if p.blocked or abs(p.minute-minute)>1e-7:
                unresolved+=1
                reason=(p.events[-1]['kind'] if p.events and p.blocked else 'unfinished_clock')
                reasons[reason]=reasons.get(reason,0)+1
                continue
            cell=cell_of(self.position(p));cells[cell]=cells.get(cell,0)+1/len(self.particles)
        denominator=sum(p.minute for p in self.particles)
        return {'cells':cells,'quality':{'engine':VERSION,'walkers':len(self.particles),
            'minute':minute,'unresolved_mass':unresolved/len(self.particles),'resolved_mass':sum(cells.values()),
            'unresolved_reasons':reasons,
            'uncertain_time_fraction':sum(p.uncertain_minutes for p in self.particles)/denominator if denominator else 0.,
            'population_prior_time_fraction':sum(p.baseline_minutes for p in self.particles)/denominator if denominator else 0.,
            'population_rest_minutes':sum(p.population_rest_minutes for p in self.particles),
            'population_rest_is_provisional':True,'population_rest_policy':asdict(self.rest_policy),
            'population_rest_priority':'pause_movement_intent; preserve_explicit_physical_walk_rest_wait',
            'direction_state_source':self.direction_state_source,
            'direction_state':self.mind_confusion,
            'cumulative_confusion_role':'condition_trigger_only_not_direction_probability',
            'population_rest_trigger':'existing_gauge_curve_once_per_simulation_minute_not_per_road_node',
            'unknown_branch_weighting':'equal_distinct_supported_actions_not_calibrated',
            'unobserved_recognition':'unknown; branches only when a personal rule depends on it',
            'arrival_default':'completed_goal_with_unchanged_movement_prior_not_automatic_wait',
            'rest_minutes_if_unreported':5.,'wait_review_minutes_if_unreported':30.,
            'rule_scope_distance_m':60.,'clinical_accuracy_measured':False,'latent_high_band':.7,'latent_high_band_source':'existing_gauges_report_provisional_not_clinical','new_model_calls_during_walk':0,
            'environment_distance_on_edge':'linear_interpolation_of_mapped_endpoint_distances',
            'radius_role':'existing_statistical_p95_support_not_fitted_terminal_distance',
            'map_extent_checked':True,'map_boundary_margin_m':50.}}
