"""Opt-in, offline candidate. Preserve raw output; never synthesize missing model content.
Not installed in the application or the frozen experimental runner.
"""
import json,re
FEATURE_KEYS={'destination_pull','movement_persistence','route_shape','mobility_range'}
class FormatRejected(ValueError):pass

def _unique_object(pairs):
    d={}
    for k,v in pairs:
        if k in d:raise FormatRejected('duplicate_key:'+k)
        d[k]=v
    return d

def _no_constant(value):raise FormatRejected('nonfinite_number:'+value)

def recover_envelope(raw,condition):
    """Return decoded object plus explicit repairs, not an assertion of semantic validity."""
    if not isinstance(raw,str):raise FormatRejected('content_not_string')
    text=raw.strip();repairs=[]
    fence=re.fullmatch(r'```(?:json)?\s*\n(.*)\n```',text,re.DOTALL|re.IGNORECASE)
    if fence:text=fence.group(1).strip();repairs.append('strip_outer_code_fence')
    decoder=json.JSONDecoder(object_pairs_hook=_unique_object,parse_constant=_no_constant)
    try:value,end=decoder.raw_decode(text)
    except ValueError as e:raise FormatRejected('invalid_json:'+str(e)) from None
    tail=text[end:].strip()
    if tail:
        if tail=='}' and isinstance(value,dict):repairs.append('remove_one_extra_terminal_closing_brace')
        else:raise FormatRejected('ambiguous_trailing_content')
    if not isinstance(value,dict):raise FormatRejected('top_level_not_object')
    if condition=='FEATURES' and set(value)=={'features'}:
        fs=value['features']
        if isinstance(fs,dict) and set(fs)==FEATURE_KEYS|{'integration','prior'} and isinstance(fs['integration'],list) and isinstance(fs['prior'],dict):
            value={'features':{k:fs[k] for k in fs if k in FEATURE_KEYS},'integration':fs['integration'],'prior':fs['prior']}
            repairs.append('lift_unique_misnested_integration_and_prior')
    # This is only syntax/wrapper recovery. Caller must run the same schema,
    # exact-evidence and semantic checks as on any original response.
    return value,repairs
