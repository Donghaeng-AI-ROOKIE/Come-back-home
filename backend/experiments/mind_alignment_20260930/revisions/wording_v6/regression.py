"""Authored regression fixtures, never a production guardian-language parser.

Assertions cover the data/payload boundary. Optional saved model responses can
be scored separately; these assertions do not imply model interpretation passes.
"""
import copy
import json
from build import HERE, SOURCE, read_rows, contract


def fixtures():
    return json.loads((HERE / 'regression_cases.json').read_text())


def context_for(case):
    context = copy.deepcopy(read_rows(SOURCE / 'train.jsonl')[0]['context'])
    context['case_id'] = case['id']
    context['person_id'] = 'wording-v6-regression-only'
    context['person']['evidence_notes'] = copy.deepcopy(case['notes'])
    context['environment']['observed_signals'] = {'market': {'noisy': case['value']}}
    context['environment']['map_proximity_m'] = dict(park=None, market=20, forest=None, water=None)
    context['state']['recent_events'] = []
    # Target is remembered; no route relationship is asserted or invented.
    context['state']['target_label'] = case.get('target_label', '등록 장소 A')
    return context


def check_response(case, response):
    contract.validate(response, context_for(case))
    if response['next_command_id'] != case['expected_command']:
        raise ValueError('semantic_command_mismatch:' + case['id'])
    if response['source_ids'] != case['expected_source_ids']:
        raise ValueError('source_attribution_mismatch:' + case['id'])
    # Free-text reason still requires semantic review; keyword matching would
    # not distinguish quotation, negation and unsupported route assumptions.


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Score separately generated JSONL {id, output}; no model calls')
    parser.add_argument('--responses', required=True)
    args = parser.parse_args()
    answers = read_rows(__import__('pathlib').Path(args.responses))
    cases = {c['id']: c for c in fixtures()}
    if len(answers) != len(cases) or {a['id'] for a in answers} != set(cases):
        raise SystemExit('missing, duplicate, or unexpected regression responses')
    errors = []
    for answer in answers:
        try:
            check_response(cases[answer['id']], answer['output'])
        except (ValueError, TypeError, KeyError) as exc:
            errors.append(dict(id=answer['id'], error=str(exc)))
    print(json.dumps(dict(total=len(cases), passed=len(cases)-len(errors), errors=errors,
                         reason_semantic_review_complete=False), ensure_ascii=False, indent=2))
    raise SystemExit(bool(errors))
