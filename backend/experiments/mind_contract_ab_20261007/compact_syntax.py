"""Explicit lexical aliases in model condition expressions, not source interpretation.

Only AND/OR/NOT/TRUE/FALSE keyword tokens are normalized. Numbers, fact names,
conditions, quotes and caregiver language are never repaired or inferred.
Original saved model responses remain untouched. Research-only compiler.
"""
from copy import deepcopy
from io import StringIO
import tokenize
from experiments.mind_contract_ab_20261007 import contract_d12

ALIASES={'AND':'and','OR':'or','NOT':'not','TRUE':'True','FALSE':'False'}


def normalize(text):
    if not isinstance(text,str) or not 0<len(text)<=1600: raise ValueError('invalid condition length')
    tokens=[];changes=[]
    for t in tokenize.generate_tokens(StringIO(text).readline):
        if t.type==tokenize.NAME and t.string in ALIASES:
            replacement=ALIASES[t.string]
            changes.append({'from':t.string,'to':replacement,'line':t.start[0],'column':t.start[1]})
            t=t._replace(string=replacement)
        tokens.append(t)
    return (tokenize.untokenize(tokens) if changes else text),changes


def prepare(value):
    result=deepcopy(value);audit=[]
    if not isinstance(result,dict):return result,audit
    for index,rule in enumerate(result.get('rules',[])):
        if not isinstance(rule,dict) or 'condition' not in rule:continue
        before=rule['condition'];after,changes=normalize(before)
        if changes:audit.append({'rule_index':index,'before':before,'after':after,'tokens':changes})
        rule['condition']=after
    return result,audit


def compile_aliases(value,personal):
    normalized,_=prepare(value)
    return contract_d12.compile_d12(normalized,personal)
