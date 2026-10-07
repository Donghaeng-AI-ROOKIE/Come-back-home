"""Paired source review of all 16 final D6 outputs; no gold enters requests.

Freeze the saved drafts as one data manifest before any new model call. The
first call of this stage is a semantic review, not a new first-pass draft.
One further received-response validation correction is allowed. Do not
select only successful D6 outputs. Original D6 failures remain in denominator.
"""
import argparse
import hashlib
import json
from pathlib import Path

from experiments.mind_contract_ab_20261007 import run_repair8, run_v2, contract_d7

STAGE = 'd7_dev8'


def freeze_drafts(d6_out, target):
    scored_path = d6_out / 'scored.json'
    scored = run_v2.read(scored_path)
    if not scored or not scored['summary']['complete']:
        raise ValueError('D6 batch must finish before paired review')
    expected = {(key, rep) for key in run_repair8.IDS for rep in (1, 2)}
    rows = scored['rows']
    if len(rows) != len(expected) or {(r['input_id'], r['rep']) for r in rows} != expected:
        raise ValueError('D6 denominator differs')
    drafts = []
    for r in rows:
        part = 'fix' if r['corrected'] else 'first'
        path = d6_out / r['input_id'] / str(r['rep']) / part / 'response.public.json'
        public = run_v2.read(path)
        if public is None:
            raise ValueError('no received draft; do not turn transport recovery into a review: ' + str(path))
        drafts.append({'input_id': r['input_id'], 'rep': r['rep'], 'source': str(path),
                       'sha256': run_v2.digest(path),
                       'public': {k: public.get(k) for k in ('finish_reason', 'final_content')}})
    value = {'stage': STAGE, 'source_stage': 'd6_dev8', 'source_scored': str(scored_path),
             'source_scored_sha256': run_v2.digest(scored_path),
             'review_kind': 'model_self_review_not_human_validation', 'drafts': drafts}
    if target.exists():
        if run_v2.read(target) != value:
            raise ValueError('frozen drafts differ')
    else:
        run_v2.write(target, value)
    return value


def register(draft_file):
    frozen = run_v2.read(draft_file)
    if not frozen:
        raise ValueError('draft manifest missing')
    drafts = {(r['input_id'], r['rep']): r for r in frozen['drafts']}
    expected = {(key, rep) for key in run_repair8.IDS for rep in (1, 2)}
    if len(frozen['drafts']) != len(expected) or set(drafts) != expected:
        raise ValueError('draft denominator differs')
    for r in drafts.values():
        path = Path(r['source'])
        if run_v2.digest(path) != r['sha256']:
            raise ValueError('source draft changed')
        original = run_v2.read(path)
        if r['public'] != {k: original.get(k) for k in ('finish_reason', 'final_content')}:
            raise ValueError('public draft differs from source')
    run_v2.CANDIDATES['d7'] = ('contract_d7', 'compile_d7', 'PLAN_d7.md')
    for path in (Path(__file__).resolve(), Path(run_repair8.__file__).resolve()):
        if path not in run_v2.COMMON:
            run_v2.COMMON.append(path)
    base_data, base_jobs = run_v2.dataset, run_v2.jobs_for

    def data(stage):
        if stage != STAGE:
            return base_data(stage)
        inputs, scenes, reference, files = run_repair8.repair_dataset()
        return inputs, scenes, reference, [*files, draft_file]

    def jobs(stage, module, inputs):
        if stage != STAGE:
            return base_jobs(stage, module, inputs)
        return [{'job': f'{stage}_{r["id"]}_{rep}', 'input': r, 'rep': rep,
                 'body': contract_d7.request_with_draft(r['personal'], drafts[r['id'], rep]['public'],
                                                       run_v2.transport.MODEL)}
                for r in inputs for rep in run_v2.REPS]
    run_v2.dataset, run_v2.jobs_for = data, jobs


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--d6-out', type=Path, required=True)
    p.add_argument('--run-dir', type=Path, required=True)
    p.add_argument('--ledger', type=Path)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--score-only', action='store_true')
    a = p.parse_args()
    draft_file = a.run_dir / 'd6_drafts_manifest.json'
    freeze_drafts(a.d6_out, draft_file)
    register(draft_file)
    argv = ['--stage', STAGE, '--run-dir', str(a.run_dir)]
    if a.ledger:
        argv += ['--ledger', str(a.ledger)]
    if a.execute:
        argv.append('--execute')
    if a.score_only:
        argv.append('--score-only')
    return run_v2.main(argv)


if __name__ == '__main__':
    main()
