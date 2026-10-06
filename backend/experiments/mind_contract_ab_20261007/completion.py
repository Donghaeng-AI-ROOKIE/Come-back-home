"""Separate output completion from meaning, without repairing any output.

Only `complete_json` is scored as a model output. `boundary_single_object` is a
diagnostic for a separately reviewed parser change; it is never merged into the
primary score. Truncation, several objects and duplicate keys are rejected.
"""
from __future__ import annotations

import json

from app.llm.initial_behavior import _unique, decode_json_content

STATUSES = ('complete_json', 'incomplete_length', 'empty', 'unexpected_finish',
            'duplicate_keys', 'boundary_single_object', 'multiple_objects', 'invalid_json')
BOUNDARY_LIMIT = 64


def _objects(text):
    decoder = json.JSONDecoder(object_pairs_hook=_unique)
    found, i = [], 0
    while i < len(text):
        if text[i] != '{':
            i += 1
            continue
        try:
            value, end = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            i += 1
            continue
        # A decoded span is skipped whole, so only top-level objects are found.
        found.append((i, end, value))
        i = end
    return found


def classify(public):
    """Return (status, value). value is set only for complete_json."""
    finish, content = public.get('finish_reason'), public.get('final_content')
    if finish == 'length':
        return 'incomplete_length', None
    if finish != 'stop':
        return 'unexpected_finish', None
    if not isinstance(content, str) or not content.strip():
        return 'empty', None
    try:
        value = decode_json_content(content)
    except ValueError as error:
        if 'duplicate JSON key' in str(error):
            return 'duplicate_keys', None
    else:
        return ('complete_json', value) if isinstance(value, dict) else ('invalid_json', None)
    try:
        top = [r for r in _objects(content) if isinstance(r[2], dict)]
    except ValueError:
        return 'duplicate_keys', None
    if len(top) > 1:
        return 'multiple_objects', None
    if len(top) == 1:
        start, end, _ = top[0]
        rest = (content[:start] + content[end:]).strip()
        if len(rest) <= BOUNDARY_LIMIT and not any(c in rest for c in '{}[]'):
            return 'boundary_single_object', None
    return 'invalid_json', None
