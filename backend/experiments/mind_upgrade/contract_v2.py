"""Uncalled candidate: make incompatible action fields unrepresentable.

The first live pilot remains frozen in contract.py. This version is prepared
without new inference. Its typed envelope is not evidence of better behavior.
"""
from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from .contract import Feature, SYSTEM, validate_decision
import json


class Evidence(BaseModel):
    model_config = ConfigDict(extra='forbid')
    evidence_ids: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=400)
    confusion_level: Literal['high', 'medium', 'low', 'unknown']


class Continue(Evidence):
    action: Literal['continue']


class Seek(Evidence):
    action: Literal['seek']
    goal_label: str = Field(min_length=1)


class Roam(Evidence):
    action: Literal['roam']


class Rest(Evidence):
    action: Literal['rest']


class Stay(Evidence):
    action: Literal['stay']


class Avoid(Evidence):
    action: Literal['avoid']
    avoid_feature: Feature


CHOICE = TypeAdapter(Annotated[Union[Continue, Seek, Roam, Rest, Stay, Avoid],
                               Field(discriminator='action')])

# Preserve the semantic instructions, replace only the incompatible output format.
SYSTEM_V2 = SYSTEM.split('JSON 하나:')[0] + '''
지금 시작할 행동 하나만 선택한다. 지금 쉬고 나중에 걸을 생각이면 현재 행동은 rest다.
미래 행동과 현재 행동을 한 항목으로 합치지 않는다. 개인 근거와 현재 조건이
휴식을 뒷받침하지 않으면 단지 피로 수치가 있다는 이유만으로 rest로 정하지 않는다.
공통 출력은 action, evidence_ids, reason, confusion_level이다.
seek에만 goal_label(등록된 장소)을 추가한다. avoid에만 avoid_feature를 추가한다.
그 외 행동에는 목적지 필드가 없다. continue/rest/stay/avoid는 기존 목적지를 유지하고,
roam은 기존 목적지를 해제한다. goal_operation을 생성하지 않는다.
reason은 지금 선택한 행동과 근거를 설명한다. 불확실성은 명시한다.
'''


def validate_choice(value, context):
    choice = CHOICE.validate_python(value)
    # Deterministic typed-interface translation; no reading/parsing of reason text.
    operation = 'set' if choice.action == 'seek' else 'clear' if choice.action == 'roam' else 'keep'
    execution = {
        'action': choice.action,
        'goal_operation': operation,
        'goal_label': getattr(choice, 'goal_label', None),
        'avoid_feature': getattr(choice, 'avoid_feature', None),
        'evidence_ids': choice.evidence_ids,
        'reason': choice.reason,
        'confusion_level': choice.confusion_level,
    }
    return validate_decision(execution, context)


def request_spec(context, model):
    return {'model': model,
            'messages': [{'role': 'system', 'content': SYSTEM_V2},
                         {'role': 'user', 'content': json.dumps(context, ensure_ascii=False, sort_keys=True)}],
            'temperature': .3, 'max_tokens': 700,
            'chat_template_kwargs': {'enable_thinking': False},
            'guided_json': CHOICE.json_schema(), 'repetition_penalty': 1.05}
