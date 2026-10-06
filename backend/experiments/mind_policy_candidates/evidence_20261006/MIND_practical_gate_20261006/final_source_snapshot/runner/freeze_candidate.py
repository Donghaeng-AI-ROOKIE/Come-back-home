"""Freeze a passing development candidate before any evaluation call."""
import argparse
import json
import os
from run_candidate import D, code_hashes, starts


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('candidate')
    args=parser.parse_args()
    if not args.candidate.replace('_','').isalnum():
        raise ValueError('invalid candidate name')
    summary=json.loads((D/'development'/args.candidate/'summary.json').read_text())
    if not summary['gate']['advance_to_integration'] or summary['gate']['total']!=16:
        raise SystemExit('complete 8 scenes x 2 repeats and pass prospective 90% gate')
    if summary['manifest']['code_sha256']!=code_hashes():
        raise SystemExit('code changed after development; not the evaluated candidate')
    if any(x.get('role')=='mind_state_alignment_evaluation' for x in starts()):
        raise SystemExit('evaluation already started; do not change candidate against its results')
    result={'candidate':args.candidate,'thinking':summary['manifest']['thinking'],
            'whole_person':summary['manifest'].get('whole_person',False),
            'code_sha256':code_hashes(),'development_gate':summary['gate'],
            'evaluation_input_sha256':json.loads((D/'manifest.json').read_text())['input_sha256']['evaluation_inputs.json']}
    path=D/'selected_candidate.json'
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as file:
        file.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('Frozen for evaluation; no model calls made.')


if __name__=='__main__':
    main()
