"""K-grounded conditional behavior, evaluated without guardian keyword matching.

The model interprets personal evidence. The executor only evaluates typed facts.
Unknown facts produce explicit possible branches, never a fabricated observation.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from typing import Literal
from itertools import product
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, model_validator
from app.llm.initial_behavior import build_payload, evidence_notes

VERSION = 'mind-policy-d12-sourced-followup-v2'
# New sourced-followup contract: integration tests are not live semantic release
# qualification. Staging may exercise this version without enabling production.
RELEASE_QUALIFIED = False
BOOLEAN_FACTS = ('lost_awareness', 'family_present', 'pain_observed', 'target_recognized',
    'physical_arrival', 'is_walking', 'dark_observed', 'rain_observed',
    'fatigue_high', 'anxiety_high', 'home_pull_high',
    'market.noisy', 'market.crowded', 'park.noisy', 'park.crowded',
    'forest.noisy', 'forest.crowded', 'water.noisy', 'water.crowded')
NUMERIC_FACTS = ('continuous_walk_minutes', 'distance_since_rest_m', 'clock_hour')
FACTS = BOOLEAN_FACTS + NUMERIC_FACTS
FactName = Literal[*FACTS]

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Evidence(Strict):
    note_id: str
    quote: str | None = Field(default=None, min_length=1, max_length=4000)

class Atom(Strict):
    fact: FactName
    op: Literal['eq','gte','lte','gt','lt']
    value: StrictBool | StrictInt | StrictFloat

    @model_validator(mode='after')
    def typed(self):
        if self.fact in BOOLEAN_FACTS:
            if self.op != 'eq' or type(self.value) is not bool:
                raise ValueError('boolean facts require boolean equality')
        elif type(self.value) is bool or self.value < 0:
            raise ValueError('numeric fact needs a nonnegative number')
        if self.fact == 'clock_hour' and self.value > 24:
            raise ValueError('clock hour out of range')
        return self

class AfterWait(Strict):
    """Only an explicitly sourced movement after a completed finite wait."""
    action: Literal['walk', 'seek']
    goal_label: str | None = None
    evidence: list[Evidence] = Field(min_length=1, max_length=5)

    @model_validator(mode='after')
    def structure(self):
        if (self.action == 'seek') != (self.goal_label is not None):
            raise ValueError('follow-up seek requires a registered goal')
        if any(e.quote is None for e in self.evidence):
            raise ValueError('follow-up needs an explicit original quote')
        return self


class Rule(Strict):
    id: str = Field(min_length=1, max_length=120)
    when: list[list[Atom]] = Field(min_length=1, max_length=6)
    action: Literal['wait','rest','walk','avoid','seek']
    goal_label: str | None
    feature: Literal['market','park','water','forest'] | None
    # Names are supplied by the user; empty = not limited to a particular place.
    place_labels: list[str] = Field(max_length=6)
    hold_minutes: float | None = Field(ge=0.1, le=360)
    supersedes: list[str] = Field(max_length=8)
    evidence: list[Evidence] = Field(min_length=1, max_length=5)
    after_wait: AfterWait | None = None

    @model_validator(mode='after')
    def structure(self):
        if any(len(clause)>8 for clause in self.when):
            raise ValueError('empty or oversized AND clause')
        if (self.action=='seek') != (self.goal_label is not None):
            raise ValueError('seek needs a registered goal; other actions preserve memory')
        if (self.action=='avoid') != (self.feature is not None):
            raise ValueError('avoid needs its feature')
        if self.hold_minutes is not None and self.action not in ('rest','wait'):
            raise ValueError('only a sourced rest/wait duration is allowed')
        if self.after_wait is not None and (self.action != 'wait' or self.hold_minutes is None):
            raise ValueError('follow-up requires a finite sourced wait')
        return self

class Unrepresented(Strict):
    note_id: str
    reason: str = Field(min_length=1, max_length=1200)

class Policy(Strict):
    rules: list[Rule] = Field(max_length=24)
    unrepresented: list[Unrepresented] = Field(max_length=24)


def source(persona, prior=None):
    raw=build_payload(persona,None,[],prior)
    return {'notes':evidence_notes(raw),'places':raw['places'],
            'prepared_initial':deepcopy({k:persona.prepared_initial.get(k) for k in ('core','scope','version')})}


def revision(persona):
    # A numerical baseline or scenario must not masquerade as personal evidence.
    from app.config import settings
    from app.llm.mind_policy_profiles import selected
    data={'contract':selected().VERSION,'version':VERSION,'model':settings.kexaone_model,'persona_version':persona.version,'source':source(persona)}
    return hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def validate(value, personal):
    policy=Policy.model_validate(value)
    notes={n['id']:n['text'] for n in personal['notes']}
    labels={p['label'] for p in personal['places']}
    ids={r.id for r in policy.rules}
    if len(ids)!=len(policy.rules): raise ValueError('duplicate rule id')
    for rule in policy.rules:
        if not set(rule.place_labels)<=labels or (rule.goal_label and rule.goal_label not in labels):
            raise ValueError('invented place')
        if rule.id in rule.supersedes or not set(rule.supersedes)<=ids:
            raise ValueError('invalid precedence reference')
        extra = rule.after_wait.evidence if rule.after_wait else []
        if rule.after_wait and rule.after_wait.goal_label and rule.after_wait.goal_label not in labels:
            raise ValueError('invented follow-up goal')
        for evidence in rule.evidence + extra:
            if evidence.note_id not in notes:raise ValueError('unknown evidence note')
            answer=notes[evidence.note_id].split('\n답변: ',1)[-1]
            if answer.startswith('답변: '): answer=answer[4:]
            if evidence.quote is None:evidence.quote=answer
            if not evidence.quote or evidence.quote not in answer: raise ValueError('quote not in original answer')
    # Cyclic precedence could erase all matching rules.
    def visit(rid, ancestors):
        if rid in ancestors: raise ValueError('cyclic precedence')
        for other in next(r for r in policy.rules if r.id==rid).supersedes:
            visit(other,ancestors|{rid})
    for rid in ids: visit(rid,set())
    if any(item.note_id not in notes for item in policy.unrepresented):
        raise ValueError('invented unrepresented source')
    return policy

def atom_value(atom, facts):
    actual=facts.get(atom.fact)
    if actual is None:return None
    if atom.fact in BOOLEAN_FACTS:
        if type(actual) is not bool:return None
        return actual is atom.value
    if type(actual) not in (int,float):return None
    if atom.op=='eq':return actual==atom.value
    # Strict and inclusive bounds must partition the same boundary. Otherwise
    # "before eight minutes" can overlap "from eight minutes, rest".
    if atom.op=='gte':return actual>=atom.value-1e-8
    if atom.op=='lte':return actual<=atom.value+1e-8
    if atom.op=='gt':return actual>atom.value+1e-8
    return actual<atom.value-1e-8


def truth(clauses,facts):
    values=[]
    for clause in clauses:
        vals=[atom_value(a,facts) for a in clause]
        values.append(False if False in vals else None if None in vals else True)
    return True if True in values else None if None in values else False


def spatial_scope(rule,near_places,near_features):
    # A named place is the narrower scope; a missing category layer must not
    # erase an explicitly mapped named location.
    if rule.place_labels:
        key='spatial_scope:places:'+json.dumps(sorted(rule.place_labels),ensure_ascii=False)
        return key,None if near_places is None else bool(set(rule.place_labels)&set(near_places))
    if rule.feature:
        value=(near_features.get(rule.feature) if isinstance(near_features,dict)
               else None if near_features is None else rule.feature in near_features)
        return 'spatial_scope:feature:'+rule.feature,value
    return None,True


def applicable(policy,facts,*,near_places=None,near_features=None):
    """Return true and possible rules, preserving unknown and explicit precedence."""
    yes=[];maybe=[]
    for rule in policy.rules:
        value=truth(rule.when,facts)
        key,scoped=spatial_scope(rule,near_places,near_features)
        if scoped is None:scoped=facts.get(key)
        value=False if scoped is False or value is False else None if scoped is None else value
        if value is True:yes.append(rule)
        elif value is None:maybe.append(rule)
    # A possible overriding rule is itself an unresolved branch; only true
    # overriding rules may remove another rule from the definitely-active set.
    removed={rid for r in yes for rid in r.supersedes}
    return [r for r in yes if r.id not in removed],[r for r in maybe if r.id not in removed]


def possibilities(policy,facts,*,near_places=(),near_features=()):
    """Consistent possible commands, not a model confidence distribution.

    Boolean unknowns are enumerated together, preserving correlations between
    predicates across rules. None means the ordinary movement prior is still
    possible. The caller must disclose any weighting of these possibilities.
    """
    active, possible=applicable(policy,facts,near_places=near_places,near_features=near_features)
    unknown=sorted({a.fact for r in possible for clause in r.when for a in clause
                    if facts.get(a.fact) is None})
    unknown+=sorted({key for r in possible
        for key,value in [spatial_scope(r,near_places,near_features)] if value is None})
    domains=[]
    for name in unknown:
        if name in BOOLEAN_FACTS or name.startswith('spatial_scope:'):domains.append([False,True])
        else:
            thresholds={float(a.value) for r in possible for c in r.when for a in c if a.fact==name}
            values={0.}
            for n in thresholds:values.update([max(0,n-1e-6),n,n+1e-6])
            domains.append(sorted(values))
    if __import__('math').prod(map(len,domains))>256:
        raise ValueError('too many unresolved policy conditions')
    outcomes={}
    for values in product(*domains):
        assigned=dict(facts,**dict(zip(unknown,values)))
        chosen,_=applicable(policy,assigned,near_places=near_places,near_features=near_features)
        for r in chosen or [None]:
            key='baseline' if r is None else json.dumps([r.action,r.goal_label,r.feature,r.place_labels,r.hold_minutes],ensure_ascii=False)
            outcomes.setdefault(key,r)
    return list(outcomes.values()),unknown

def fixed_rules(personal):
    """Compile agreed typed initial conditions; never parse guardian text.

    Place-specific reactions still need a grounded place link, so they are not
    widened here. Category conditions with evidence are already fully typed.
    """
    prepared=personal.get('prepared_initial') or {};scope=prepared.get('scope') or {};out=[]
    for feature,item in scope.get('environment',{}).items():
        if item.get('response')!='avoid' or item.get('scope') not in ('category','conditional_category'):continue
        if not item.get('note_ids'):continue
        clauses=item.get('condition_clauses',[])
        if item['scope']=='conditional_category' and not clauses:continue
        when=[[{'fact':feature+'.'+c['signal'],'op':'eq','value':c['state']=='present'} for c in clause] for clause in clauses] or [[]]
        raw={'id':'initial_env_'+feature,'when':when,'action':'avoid','goal_label':None,
             'feature':feature,'place_labels':[],'hold_minutes':None,'supersedes':[],
             'evidence':[{'note_id':n} for n in item['note_ids']]}
        out.extend(validate({'rules':[raw],'unrepresented':[]},personal).rules)
    return out


def add_fixed(policy,personal):
    fixed=fixed_rules(personal);features={r.feature for r in fixed}
    # Avoid reinterpreting the same established environment response.
    free=[r for r in policy.rules if r.feature not in features]
    kept={r.id for r in fixed+free}
    free=[r.model_copy(update={'supersedes':[x for x in r.supersedes if x in kept]}) for r in free]
    return Policy(rules=fixed+free,unrepresented=policy.unrepresented)
