"""Keep numerically valid rules for diagnosis without claiming full coverage.

Only the explicit source_omitted_without_classification error is eligible.
Missing notes remain unclassified, never judged non-behavioral. Original
responses/scores remain frozen. This is not a production fallback or pass.
"""
from copy import deepcopy
from experiments.mind_contract_ab_20261007 import contracts,contract_d12


def compile_for_diagnosis(value,personal):
    try:
        policy=contract_d12.compile_d12(value,personal)
        return policy,{'source_accounting_complete':True,'unclassified_note_ids':[],'diagnostic_only':True}
    except ValueError as error:
        if str(error)!='source_omitted_without_classification':raise
    # The original still has to satisfy the same schema/field validation.
    contracts._validate_shape(value,contracts.schema_a(personal))
    parsed=contracts.OutputA.model_validate(value)
    covered=set(parsed.non_action_note_ids)|{n for row in parsed.rules for n in row.note_ids}
    covered|={e.note_id for row in contracts.fixed(personal) for e in row.evidence}
    missing=sorted({n['id'] for n in personal['notes']}-covered)
    if not missing:raise ValueError('coverage rejection without missing notes')
    temporary=deepcopy(value)
    temporary['non_action_note_ids']+=missing
    policy=contract_d12.compile_d12(temporary,personal)
    output=policy.model_dump()
    for item in output['unrepresented']:
        if item['note_id'] in missing:
            item['reason']='모델의 근거 분류 누락. 코드가 진단을 위해 보존했으며 비행동 정보라는 판정이 아님.'
    policy=type(policy).model_validate(output)
    return policy,{'source_accounting_complete':False,'unclassified_note_ids':missing,
        'diagnostic_only':True,'eligible_for_release':False,
        'rule_action_condition_numbers_unchanged':True,'raw_response_unchanged':True}
