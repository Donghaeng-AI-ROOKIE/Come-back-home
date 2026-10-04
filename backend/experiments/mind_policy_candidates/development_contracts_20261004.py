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
from app.llm.initial_behavior import build_payload, evidence_notes, decode_json_content, SOURCE_PRECEDENCE

VERSION = 'mind-policy-v6-preserve-prepared'
# This candidate failed source-faithfulness checks. A valid JSON response is not
# a deployment qualification. This is an evidence gate, not a user-facing toggle.
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
    op: Literal['eq','gte','lte']
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
    data={'version':VERSION,'model':settings.kexaone_model,'persona_version':persona.version,'source':source(persona)}
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
        for evidence in rule.evidence:
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

SYSTEM = '''치매 어르신의 보호자 원문을 시뮬레이션 중 사용할 개인 행동 조건으로 해석한다. 건강 권고가 아니라 그 사람이 실제 보인 반응을 나타내는 과업이다.
원문에서 조건·현재와 과거·본인의 의도와 보호자의 지시·정정·부정·예외를 함께 읽는다. 일반적인 치매 특성을 개인의 관찰 사실로 만들지 않는다. 저장된 초기 해석은 보조자료이며 원문을 우선한다.
각 rule은 원문을 정확히 인용하고 when(OR of AND)의 조건이 성립할 때만 실행할 행동을 적는다. 당사자의 반응을 모르는 내용, 과거 방문만 있는 내용, 단순 후보 장소는 행동 규칙으로 만들지 말고 unrepresented에 이유를 적는다. 원문을 단어 목록으로 대응하지 않는다.
행동: wait=자리에 머물러 기다림, rest=일시 휴식, walk=목표 여부와 독립적으로 보행 유지·재개, avoid=지정 환경에서 멀어짐, seek=등록된 목표로 이동. wait/rest/avoid도 기존 목표의 기억을 지우지 않는다. walk는 목표를 새로 만들거나 이미 도착한 목표를 다시 설정하지 않는다.
physical_arrival은 좌표 도달이고 target_recognized는 본인이 장소를 알아본 상태다. 좌표에 도달했다는 이유만으로 알아봤다거나 기다린다고 만들지 않는다. 도착 후 반응을 모르면 그 규칙을 만들지 않는다.
lost_awareness는 본인이 길 잃음을 알아챘다는 조건이다. is_walking은 실제 보행 중. continuous_walk_minutes는 마지막 정지 이후 보행 시간, distance_since_rest_m는 마지막 휴식/대기 이후 보행 거리. 실종 경과시간을 보행시간으로 대체하지 않는다.
조건의 true/false는 관측 또는 명시한 시뮬레이션 가정이며 null은 미확인이다. unknown을 false로 쓰지 않는다. 장소 한정 반응은 place_labels에 정확한 등록 이름을 넣고 유형 전체로 확대하지 않는다. 시장 전반 반응은 feature=market, place_labels=[]이다. 회피 rule의 feature를 다른 행동에 쓰지 않는다.
수치는 원문에 직접 주어진 보행 한계·휴식 시간·시각만 단위를 바꿔 기재한다. 휴식 시간이 없으면 hold_minutes=null. 숫자 없이 피곤할 때 쉰다고만 하면 피로 proxy 임계값을 지어내지 말고 unrepresented에 기록한다. 보행 한계의 휴식 조건에는 is_walking=true도 넣어 이미 대기하는 사람에게 가짜 보행 후 휴식을 만들지 않는다.
"길 잃으면 가족이 올 때까지 기다림"은 lost_awareness=true AND family_present=false이며, 가족이 도착하면 이 규칙을 적용하지 않는다. 예외도 AND 조건으로 보존한다. supersedes는 원문이 우선순위를 직접 설명할 때만 다른 규칙 ID를 넣는다. 모델 임의 우선순위는 금지.
규칙이 동시에 성립하고 우선순위가 없으면 엔진이 가능성을 유지한다. 모델은 행동 확률, 좌표, 일반적인 체류시간을 만들지 않는다. 한 rule의 장소 범위는 그 rule의 모든 조건에 적용된다.
오직 rules와 unrepresented를 가진 완전한 JSON 하나를 출력한다. 설명용 내부 추론은 출력하지 않는다.
'''+SOURCE_PRECEDENCE


def request(personal,model,*,draft=None):
    condition_a={'fact':'market.noisy','op':'eq','value':True}
    condition_b={'fact':'market.crowded','op':'eq','value':True}
    user={'format_only_not_person_evidence':{
            'when_AND_example':[[condition_a,condition_b]],
            'when_OR_example':[[condition_a],[condition_b]],
            'instruction':'when은 반드시 2중 배열. 바깥은 OR, 안쪽은 AND. 1중 배열은 금지. 이 예시 조건을 당사자 근거 없이 복사하지 않는다.'},'person':personal,'fact_vocabulary':{'boolean':BOOLEAN_FACTS,'nonnegative_number':NUMERIC_FACTS},
          'schema':Policy.model_json_schema()}
    if draft is not None:
        user['draft_to_review']=draft
        user['review_instruction']='원문으로 초안을 다시 검토하라. 조건 누락, AND/OR, 장소 범위, 과거화, 근거 없는 행동/숫자를 고친 전체 JSON을 반환한다. 이전 답과 일치할 의무는 없다. 단순 인용 존재를 의미 정확성으로 간주하지 않는다.'
    body={'model':model,'temperature':.2,'top_p':.95,'max_tokens':12000,'parse_reasoning':True,
          'chat_template_kwargs':{'enable_thinking':False},
          'response_format':{'type':'json_schema','json_schema':{'schema':provider_schema()}},
          'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(user,ensure_ascii=False)}]}
    if len(json.dumps(body,ensure_ascii=False).encode())>40000: raise ValueError('input byte cap')
    return body


def provider_schema():
    """Inline references for the serving API; local Pydantic checks still apply."""
    root=Policy.model_json_schema();definitions=root.get('$defs',{})
    def expand(value):
        if isinstance(value,list):return [expand(x) for x in value]
        if not isinstance(value,dict):return value
        if '$ref' in value:return expand(definitions[value['$ref'].rsplit('/',1)[-1]])
        out={k:expand(v) for k,v in value.items() if k not in ('$defs','title')}
        if 'anyOf' in out and all(set(v)=={'type'} for v in out['anyOf']):
            out['type']=list(dict.fromkeys(v['type'] for v in out.pop('anyOf')))
        return out
    return expand(root)


def atom_value(atom, facts):
    actual=facts.get(atom.fact)
    if actual is None:return None
    if atom.fact in BOOLEAN_FACTS:
        if type(actual) is not bool:return None
        return actual is atom.value
    if type(actual) not in (int,float):return None
    if atom.op=='eq':return actual==atom.value
    return actual>=atom.value-1e-8 if atom.op=='gte' else actual<=atom.value+1e-8


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

# v4: two independent interpretations of different features. Small output
# contracts reduce format pressure; the compiler never reads guardian keywords.
class MotionRule(Strict):
    when: list[list[Atom]]
    action: Literal['wait','rest','walk']
    hold_minutes: float | None = Field(ge=.1,le=360)
    evidence: list[Evidence] = Field(min_length=1,max_length=5)

class EnvironmentRule(Strict):
    when: list[list[Atom]]
    feature: Literal['market','park','forest','water']
    place_labels: list[str]
    evidence: list[Evidence] = Field(min_length=1,max_length=5)

class MotionOutput(Strict):
    rules: list[MotionRule] = Field(max_length=12)

class EnvironmentOutput(Strict):
    rules: list[EnvironmentRule] = Field(max_length=12)

PART_SYSTEM='''보호자가 실제 관찰한 치매 어르신의 개인 반응을 조건과 행동으로 해석한다.
현재/과거, 본인의 행동/보호자의 희망, 정정과 부정, 관찰함/모름을 구분한다. 관찰하지 못했다는 문장을 근거로 그 반응을 만들어서는 안 된다. 단순히 걸을 수 있는 시간은 그 시간에 반드시 쉬거나 그 전에는 반드시 걷는다는 뜻이 아니다. 근거가 없는 반응은 출력하지 않는다.
when은 OR of AND, 반드시 2중 배열. A와 B 모두 필요하면 [[A,B]], A나 B 중 하나면 [[A],[B]]. 예외가 있다면 각 행동의 조건에 그 예외를 반영해 함께 성립하지 않게 한다. 예시 A/B는 형식만 뜻하며 실제 조건은 원문에서 찾아야 한다.
원문의 정확한 짧은 인용과 note_id를 붙인다. 보호자 답이 짧으면 질문과 함께 해석하지만 인용은 답 자체에서 한다. 행동 확률·좌표·숫자 임계값을 만들어내지 않는다. 원문에 숫자로 제시된 보행시간·거리·시각·휴식시간만 단위 변환해 사용할 수 있다. null 조건은 미확인이고 false가 아니다. 완전한 JSON 하나만 출력한다.'''

def part_request(personal,model,part):
    contract=MotionOutput if part=='motion' else EnvironmentOutput
    if part=='motion':
        instruction='''보행과 정지만 해석. wait=기다림, rest=휴식, walk=걷기. 원문이 휴식시간을 주지 않으면 hold_minutes=null. 휴식은 보행시간을 늘리지 않으며 실종 경과시간도 보행시간이 아니다. 보행 한계의 rest 조건에는 is_walking=true를 같은 AND 절에 넣어라. 통증처럼 보행과 무관하게 쉴 수도 있는 조건에는 그것을 강제하지 않는다. 장소에 좌표상 도착한 physical_arrival과 그 장소를 알아본 target_recognized는 다르다. 길 잃음을 알았을 때만 보인 행동은 lost_awareness에 조건부여한다. 가족 도착 전까지라는 종료 조건도 보존한다. 목적지 선택·환경 회피는 다른 해석기가 담당하므로 여기서는 제외한다.'''
        facts=[x for x in FACTS if '.' not in x]
    else:
        instruction='''환경에서 멀어지는 회피 반응만 해석한다. 환경 선호, 단순 이동 능력, 휴식, 목적지 방문 이력은 여기서 제외한다. place_labels가 빈 배열이면 장소 유형 전체에 적용되므로, 한 곳에서만 본 반응이면 그 등록된 이름을 정확히 넣는다. noisy/crowded 조건의 AND/OR와 부정, 보호자와 당사자를 구분한다. 등록 이름이 없어 한 장소 한정을 보존할 수 없으면 유형 전체로 확대하지 말고 그 규칙을 출력하지 않는다.'''
        facts=[x for x in FACTS if '.' in x]+['dark_observed','rain_observed']
    schema=contract.model_json_schema();defs=schema.get('$defs',{})
    def expand(value):
        if isinstance(value,list):return [expand(x) for x in value]
        if not isinstance(value,dict):return value
        if '$ref' in value:return expand(defs[value['$ref'].rsplit('/',1)[-1]])
        out={k:expand(v) for k,v in value.items() if k not in ('$defs','title')}
        if 'anyOf' in out and all(set(v)=={'type'} for v in out['anyOf']):out['type']=[v['type'] for v in out.pop('anyOf')]
        return out
    body={'model':model,'temperature':1.,'top_p':.95,'max_tokens':12000,'parse_reasoning':True,
      'chat_template_kwargs':{'enable_thinking':True},
      'response_format':{'type':'json_schema','json_schema':{'schema':expand(schema)}},
      'messages':[{'role':'system','content':PART_SYSTEM+'\n'+instruction},
        {'role':'user','content':json.dumps({'notes':personal['notes'],'places':personal['places'],'allowed_facts':facts,
          'format_schema':schema,'format_example_only':{'AND':[[{'fact':facts[0],'op':'eq','value':True}]],
              'instruction':'형식 예시일 뿐이다. 실제 사실과 자료형은 원문과 schema를 따른다.'}},ensure_ascii=False)}]}
    if len(json.dumps(body,ensure_ascii=False).encode())>40000:raise ValueError('input byte cap')
    return body


def validate_part(value,personal,part):
    parsed=(MotionOutput if part=='motion' else EnvironmentOutput).model_validate(value)
    rules=[]
    for i,r in enumerate(parsed.rules):
        d=r.model_dump(mode='json');d.update(id=f'{part}_{i}',goal_label=None,supersedes=[])
        if part=='motion':d.update(feature=None,place_labels=[])
        else:d.update(action='avoid',hold_minutes=None)
        rules.append(d)
    return validate({'rules':rules,'unrepresented':[]},personal)


def merge_parts(parts,personal):
    rules=[r.model_dump(mode='json') for p in parts for r in p.rules]
    cited={e['note_id'] for r in rules for e in r['evidence']}
    return validate({'rules':rules,'unrepresented':[{'note_id':n['id'],
        'reason':'이 행동 계약에서 실행할 관찰 반응을 추출하지 않음. 초기 목표·능력 해석과 구분.'}
        for n in personal['notes'] if n['id'] not in cited]},personal)

COMPACT_SYSTEM='''보호자 원문에서 관찰된 조건부 개인 행동을 해석해 JSON으로 출력한다. 실제 이동 예측을 위한 해석이다.
반드시 구분할 것: 현재/과거, 행동을 봄/모름, 당사자 행동/보호자 권고, 능력/반응. "40분 걸을 수 있다"는 40분 뒤 쉰다는 근거가 아니다. "대처는 모른다"는 기다리거나 걷는다는 근거가 아니다.
행동 wait=기다림, rest=휴식, walk=계속 걷기/재개, avoid=멀어짐, seek=등록 목적지로 이동. 원문에 없는 행동은 만들지 않는다. 초기 장소 끌림·능력은 앞단에서 별도로 처리한다. 여기서는 조건에 따른 반응을 추출한다.
when의 바깥 배열은 OR, 안쪽 배열은 AND다. 복수 조건이 동시에 필요하면 같은 안쪽 배열에 넣는다. 예외와 종료 조건도 보존한다. 미확인 조건은 false가 아니다. place_labels는 그 특정 장소에서만 관찰했을 때 등록된 이름, 유형 전체에 적용할 때만 빈 배열이다.
보행시간은 경과시간과 다르다. 수치로 제시한 보행 한계 때문에 쉬는 조건에는 is_walking=true를 함께 넣는다. 단위만 변환하고 숫자를 지어내지 않는다. 말하지 않은 휴식시간은 null이다. fatigue_high/anxiety_high/home_pull_high는 엔진의 잠정 심리 추정 상태로, 관측된 사실은 아니다. 개인이 피곤할 때 보인 반응을 이 조건에 연결할 수 있으나 개인 임계값을 새로 만들지는 않는다.
physical_arrival=좌표상 도착, target_recognized=그곳을 알아봄. 둘은 다르다. 보호자 답을 정확하게 인용하고 note_id를 붙인다. 상충하는 규칙의 우선순위는 원문이 명시한 경우에만 supersedes로 지정한다.
근거 없는 규칙을 채워 넣지 않는다. 관련 관찰이 없으면 rules=[]가 정답이다. unrepresented에는 조건부 반응을 추출하지 못한 note_id와 짧은 이유만 적는다. 각 rule의 필수 키와 자료형은 제공된 schema를 따른다. 최종 응답은 JSON 하나.'''

def grounded_request(personal,model):
    schema=Policy.model_json_schema();schema['$defs']['Evidence']['properties'].pop('quote',None)
    return {'model':model,'temperature':.3,'top_p':.95,'max_tokens':12000,'parse_reasoning':True,
      'chat_template_kwargs':{'enable_thinking':True},
      'messages':[{'role':'system','content':COMPACT_SYSTEM+'\n이미 앞단에서 검토한 prepared_initial과 고정된 fixed_rules를 보존한다. fixed_rules에 있는 환경 반응은 출력에서 제외한다. 새로 필요한 반응만 rules로 만든다. evidence에는 note_id만 출력한다. 원문 인용은 코드가 해당 note에서 그대로 복사한다. 기존 persistence가 관찰 미확인이라면 반응을 발명하지 않는다.'},
        {'role':'user','content':json.dumps({'notes':personal['notes'],'places':personal['places'],
          'prepared_initial':personal.get('prepared_initial'), 'fixed_rules':[r.model_dump(mode='json') for r in fixed_rules(personal)],
          'schema':schema,'when_format':{'AND':'[[A,B]]','OR':'[[A],[B]]'}},ensure_ascii=False)}]}


def support_request(personal,policy,model):
    instruction='''개인 행동 추출의 독립 근거 판독. 아래 각 rule에 대해 원문이 조건과 행동 모두를 뒷받침하는지 판정한다. 새로운 rule은 만들지 않는다.
모른다/못 봤다는 문장은 그 행동의 근거가 아니다. 보행 가능 시간은 그 시점에 쉬거나 그 전에는 걷는다는 근거가 아니다. 방향 전환이나 멀어짐을 쉼으로 바꾸면 불일치다. 현재/과거, 본인/보호자, 정정/부정, AND/OR와 장소 범위, 종료 조건 중 하나라도 다르면 supported=false다. 인용이 원문에 있다는 사실만으로 통과시키지 않는다.
정확히 {"verdicts":[{"rule_id":"...","supported":true 또는 false,"reason":"짧은 이유"}]} JSON만 반환한다. 모든 rule을 한 번씩 판독하고 누락·추가하지 않는다.'''
    return {'model':model,'temperature':1.,'top_p':.95,'max_tokens':12000,'parse_reasoning':True,
      'chat_template_kwargs':{'enable_thinking':True},'messages':[{'role':'system','content':instruction},
      {'role':'user','content':json.dumps({'notes':personal['notes'],'places':personal['places'],'rules':policy.rules and [r.model_dump(mode='json') for r in policy.rules]},ensure_ascii=False)}]}


def apply_support(policy,response):
    rows=response['verdicts'];ids={r.id for r in policy.rules}
    if len(rows)!=len(ids) or {r['rule_id'] for r in rows}!=ids:raise ValueError('incomplete support review')
    if any(type(r['supported']) is not bool for r in rows):raise ValueError('invalid support verdict')
    accepted={r['rule_id'] for r in rows if r['supported']}
    keep=[]
    for r in policy.rules:
        if r.id in accepted:
            keep.append(r.model_copy(update={'supersedes':[x for x in r.supersedes if x in accepted]}))
    return Policy(rules=keep,unrepresented=policy.unrepresented)


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


def repair_request(personal,policy,model):
    schema=Policy.model_json_schema();schema['$defs']['Evidence']['properties'].pop('quote',None)
    instruction='''앞단 개인 해석을 시뮬레이션으로 연결하는 최종 검토자다. 보호자 원문과 기존 prepared_initial을 읽고 초안의 조건·행동·수치를 바로잡아 완전한 Policy JSON으로 반환한다.
기존 fixed_rules는 코드가 보존하므로 출력하지 않는다. 원문이 실제로 말한 반응만 남긴다. 보행 능력이나 "한 시간 연속으로 못 걷는다"는 부정의 상한을 한 시간에 쉰다는 규칙으로 바꾸지 않는다. 구체적으로 언제 쉰다고 했는지 확인한다. 실종 경과시간 대신 연속 보행시간을 쓴다. 기다림이 끝나는 조건도 읽는다. 모른다는 문장은 행동의 근거가 아니다. 능력과 반응을 구분한다. 회피와 휴식을 혼동하지 않는다.
AND/OR, 특정 장소/유형 전체, 원문의 숫자·단위, 부정과 예외를 각각 점검하라. 근거가 없으면 삭제한다. 원문에 명시되어 초안이 빠뜨린 조건부 반응은 보충할 수 있다. 증거에는 note_id만 적고 인용은 코드가 원문 그대로 복사한다. 예시를 발명하지 않는다. rules가 빈 배열일 수 있다. 내부 분석은 짧게 수행하고 최종에는 JSON만 쓴다.'''
    return {'model':model,'temperature':.3,'top_p':.95,'max_tokens':12000,'parse_reasoning':True,
      'chat_template_kwargs':{'enable_thinking':True},'messages':[{'role':'system','content':instruction},
      {'role':'user','content':json.dumps({'person':personal,'draft':policy.model_dump(mode='json'),
        'fixed_rules':[r.model_dump(mode='json') for r in fixed_rules(personal)],'schema':schema},ensure_ascii=False)}]}

# Compact wire contract: each row is an AND, multiple rows express alternatives.
# This avoids asking the model to construct an unlabelled nested array.
class ProgramRow(Strict):
    id: str
    all: list[Atom] = Field(max_length=8)
    action: Literal['wait','rest','walk','avoid','seek']
    target: str | None
    feature: Literal['market','park','water','forest'] | None
    places: list[str]
    duration_minutes: float | None
    supersedes: list[str]
    note_ids: list[str] = Field(min_length=1,max_length=5)

class Program(Strict):
    rules: list[ProgramRow] = Field(max_length=20)
    unused_note_ids: list[str]


def program_policy(value,personal):
    program=Program.model_validate(value)
    rules=[]
    for r in program.rules:
        rules.append({'id':r.id,'when':[[a.model_dump(mode='json') for a in r.all]],
            'action':r.action,'goal_label':r.target,'feature':r.feature,'place_labels':r.places,
            'hold_minutes':r.duration_minutes,'supersedes':r.supersedes,
            'evidence':[{'note_id':n} for n in r.note_ids]})
    parsed=validate({'rules':rules,'unrepresented':[{'note_id':n,'reason':'실행할 조건부 반응 미확인'} for n in program.unused_note_ids]},personal)
    return add_fixed(parsed,personal)


def program_request(personal,model,*,draft=None):
    schema=Program.model_json_schema();defs=schema.get('$defs',{})
    def flat(x):
        if isinstance(x,list):return [flat(y) for y in x]
        if not isinstance(x,dict):return x
        if '$ref' in x:return flat(defs[x['$ref'].rsplit('/',1)[-1]])
        y={k:flat(v) for k,v in x.items() if k not in ('$defs','title')}
        if 'anyOf' in y and all(set(v)=={'type'} for v in y['anyOf']):y['type']=[v['type'] for v in y.pop('anyOf')]
        return y
    system='''보호자 원문과 앞단의 개인 해석을 실행 가능한 행동 규칙으로 연결한다. 이미 확정된 fixed_rules는 출력하지 않는다.
한 rules 행은 all의 조건이 모두 맞을 때 하는 행동이다. 또는(OR)는 행을 나누어 같은 행동을 적는다. 행 간 우선순위가 원문에 있으면 supersedes에 그 행의 id를 쓴다.
wait=기다림, rest=휴식, walk=계속 걷기, avoid=멀어짐, seek=등록 목적지로 향함. 회피를 휴식으로 바꾸지 않는다. 보호자 권고와 당사자 행동을 구분한다. "대처는 못 봤다"면 기다림/이동 규칙을 만들지 않는다. "한 시간 못 걷는다"나 "40분 걸을 수 있다"는 해당 시점에 쉰다는 근거가 아니다. 실제로 쉰다고 한 보행 시간·거리가 따로 있으면 그것을 쓴다.
본인이 길 잃음을 알아챘음=lost_awareness. 가족 도착=family_present. 좌표상 도착=physical_arrival. 그곳을 알아봄=target_recognized. 이 상태들을 혼동하지 않는다. is_walking은 보행 중이다. 수치로 제시한 보행 한계의 휴식에는 is_walking=true도 필요하다. continuous_walk_minutes와 distance_since_rest_m는 마지막 휴식/대기 후 값이다. clock_hour는 한국 시각이다. fatigue_high/anxiety_high/home_pull_high는 엔진의 잠정 심리 상태다.
목표는 seek일 때만 target에 등록 이름을 넣는다. feature는 avoid일 때만 넣는다. places가 빈 배열이면 장소 유형 전체이므로, 특정 장소의 관찰은 이름으로 한정한다. 원문에 없는 휴식·대기 시간은 duration_minutes=null. evidence는 note_ids로 연결하며 코드는 원문을 그대로 복사한다. 근거가 없으면 규칙을 출력하지 않는다. 규칙이 0개일 수 있다.'''
    data={'notes':personal['notes'],'places':personal['places'],'prepared_initial':personal.get('prepared_initial'),
          'fixed_rules':[r.model_dump(mode='json') for r in fixed_rules(personal)]}
    if draft is not None:
        data['draft']=draft
        system+='\n최종 검토: 초안과 원문을 대조해 틀린 조건과 행동을 고치고 빠진 관찰 반응은 보충한다. 특히 보행 가능 시간과 휴식 시작 시점, 기다림의 종료 조건, AND/OR, 과거/현재, 특정 장소/유형 전체를 확인한다. 원문이 지지하지 않는 행은 삭제한다.'
    body={'model':model,'temperature':1.,'top_p':.95,'presence_penalty':0.,'max_tokens':12000,'parse_reasoning':True,
        'chat_template_kwargs':{'enable_thinking':True},
        'response_format':{'type':'json_schema','json_schema':{'schema':flat(schema)}},
        'messages':[{'role':'system','content':system},{'role':'user','content':json.dumps(data,ensure_ascii=False)}]}
    if len(json.dumps(body,ensure_ascii=False).encode())>40000:raise ValueError('input byte cap')
    return body
