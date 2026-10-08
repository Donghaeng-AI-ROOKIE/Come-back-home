"""Freeze then optionally execute one synthetic D16 length-failure correction."""
import argparse
from pathlib import Path
from experiments.mind_contract_ab_20261007 import (
    bounded_correction, run_v2 as r, transport, run_compact15, contract_d16, condition_probe,
)
from app.llm.mind_policy import Policy


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--ledger', type=Path)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    request_file = a.source / 'first/request.json'; response_file = a.source / 'first/response.public.json'
    request, audit = bounded_correction.prepare(r.read(request_file), r.read(response_file), 'incomplete_length')
    inputs, _, refs, _ = run_compact15.selected_dataset()
    key = a.source.parent.name
    row = next(x for x in inputs if x['id'] == key)
    assert row['synthetic'] is True
    manifest = {'input_id': key, 'rep': int(a.source.name), 'synthetic': True,
                'max_calls': 1, 'max_output_tokens': request['max_tokens'], 'automatic_retry': False,
                'original_scores_unchanged': True, 'new_external_services': False,
                'source_sha256': {str(f): r.digest(f) for f in
                    (request_file, response_file, Path(__file__), Path(bounded_correction.__file__))},
                'request_sha256': __import__('hashlib').sha256(__import__('json').dumps(request, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
                'standing_approval': 'same-goal repeated experiments, user 2026-10-08',
                'unit_price': None, 'actual_cost': None, 'support_round': None, 'audit': audit}
    if (a.output / 'manifest.json').exists():
        assert r.read(a.output / 'manifest.json') == manifest, 'frozen correction changed'
    else:
        r.write(a.output / 'manifest.json', manifest)
        r.write(a.output / 'request.json', request)
    if not a.execute:
        print(audit); return
    if not a.ledger: raise ValueError('ledger required')
    if (a.output / 'submitted.json').exists(): raise ValueError('never resubmit; inspect saved result/ledger')
    r.write(a.output / 'submitted.json', {'attempted': True, 'max_calls': 1})
    try:
        response = transport.invoke(request, 'd16_length_supplement', run_id='MIND_contract_ab_20261007_d16_bounded_correction',
            role='synthetic_length_correction_diagnostic', ledger_path=a.ledger, max_started=1)
        public = transport.public(response)
    except Exception as error:
        r.write(a.output / 'error.json', {'error_type': type(error).__name__, 'automatic_retry': False})
        raise
    r.write(a.output / 'response.public.json', public)
    problem, value, policy = r.judge(public, row['personal'], contract_d16.compile_d16)
    result = {'problem': problem, 'policy': policy.model_dump() if policy else None,
              'probe': condition_probe.compare(policy, Policy.model_validate(refs[key])) if policy else None,
              'original_scores_unchanged': True, 'deployment_qualified': False}
    r.write(a.output / 'result.json', result)
    print({'problem': problem, 'probe': result['probe']})


if __name__ == '__main__': main()
