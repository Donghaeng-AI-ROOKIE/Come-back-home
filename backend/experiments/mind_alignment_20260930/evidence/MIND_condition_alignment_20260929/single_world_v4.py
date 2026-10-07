"""Isolate one hypothetical world per request, preserving the v3 evidence."""
import copy
import json
import branch_json_completion_v3 as previous
import branch_contract as branches


def payload(context, world_key, model):
    body = previous.payload(context, 'branch_json_completion_v3', model)
    data = json.loads(body['messages'][1]['content'])
    if world_key not in data['가정_분기']:
        raise ValueError('unknown_world')
    data['가정_분기'] = {world_key: data['가정_분기'][world_key]}
    data['가정_분기_읽기'] = {world_key: data['가정_분기_읽기'][world_key]}
    body['messages'][1]['content'] = json.dumps(data, ensure_ascii=False)
    schema = body['response_format']['json_schema']['schema']
    schema['required'] = [world_key]
    schema['properties'] = {world_key: schema['properties'][world_key]}
    return body


def validate(value, context, world_key):
    if world_key not in branches.worlds(context):
        raise ValueError('unknown_world')
    if not isinstance(value, dict) or set(value) != {world_key}:
        raise ValueError('single_world_coverage')
    response = value[world_key]
    if not isinstance(response, dict):
        raise ValueError('branch_type')
    if response.get('next_command_id') not in previous.previous.options(context):
        raise ValueError('command_not_available')
    reason = response.get('reason')
    if not isinstance(reason, str) or not 1 <= len(reason) <= 240:
        raise ValueError('reason')
    return branches.original.validate(response, context, 'next_source_ids')


def aggregate(responses, context):
    # Missing/repeated worlds must not be silently combined or filled in.
    expected = branches.worlds(context)
    merged = {}
    for response in responses:
        if not isinstance(response, dict) or len(response) != 1:
            raise ValueError('single_world_coverage')
        key = next(iter(response))
        validate(response, context, key)
        if key in merged:
            raise ValueError('duplicate_world')
        merged[key] = copy.deepcopy(response[key])
    if set(merged) != set(expected):
        raise ValueError('branch_coverage')
    return previous.validate(merged, context, 'branch_json_completion_v3')
