"""Prepared latency repair; retains v2 execution validation.

XGrammar's token-mask replay showed a large cost for overlapping action branches
that generate the bounded reason field before their discriminator. Select action
first. Keep every existing field constraint, including the reason length limit.
No inference improvement is claimed until an approved live recheck completes.
"""
from copy import deepcopy
from .contract_v2 import CHOICE, request_spec as v2_request_spec, validate_choice


def generation_schema():
    schema = deepcopy(CHOICE.json_schema())
    for definition in schema['$defs'].values():
        properties = definition['properties']
        definition['properties'] = {
            'action': properties['action'],
            **{name: value for name, value in properties.items() if name != 'action'},
        }
    return schema


def request_spec(context, model):
    request = v2_request_spec(context, model)
    request['guided_json'] = generation_schema()
    request['messages'][0]['content'] += '\nJSON은 action부터 출력한다. reason은 400자 이내로 작성한다.\n'
    return request
