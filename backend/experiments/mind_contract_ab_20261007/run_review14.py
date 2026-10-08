"""D14 compact-expression comparison on the same fixed repair8 sources."""
import argparse
from pathlib import Path
from experiments.mind_contract_ab_20261007 import run_v2 as r, run_repair8, resume_concise8 as guarded


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir', required=True); p.add_argument('--ledger')
    p.add_argument('--execute', action='store_true'); p.add_argument('--draft-dir',required=True,type=Path); a = p.parse_args()
    r.CANDIDATES['d14'] = ('contract_d14', 'compile_d14', 'PLAN_d14.md')
    for f in (__file__, run_repair8.__file__, guarded.__file__):
        path = Path(f).resolve()
        if path not in r.COMMON: r.COMMON.append(path)
    original_dataset = r.dataset
    r.dataset = lambda stage: run_repair8.repair_dataset() if stage == 'd14_dev8' else original_dataset(stage)
    from experiments.mind_contract_ab_20261007 import contract_d14 as review
    original_jobs=r.jobs_for
    def jobs(stage,module,inputs):
        if stage!='d14_dev8': return original_jobs(stage,module,inputs)
        out=[]; fingerprints={}
        for x in inputs:
            for rep in r.REPS:
                folder=a.draft_dir/x['id']/str(rep)
                source=folder/'fix/response.public.json'
                if not source.exists():source=folder/'first/response.public.json'
                public=r.read(source);status,draft=r.completion.classify(public)
                if status!='complete_json': raise ValueError('draft must be a saved public JSON')
                fingerprints[str(source.resolve())]=r.digest(source)
                out.append({'job':f'{stage}_{x["id"]}_{rep}','input':x,'rep':rep,
                            'body':review.request_review(x['personal'],r.transport.MODEL,draft)})
        f=Path(a.run_dir)/'draft_provenance.json'
        if f.exists() and r.read(f)!=fingerprints: raise ValueError('frozen drafts changed')
        r.write(f,fingerprints)
        return out
    r.jobs_for=jobs
    old_execute, old_score = r.execute, r.score
    r.execute = lambda *args: guarded.execute_guarded(old_execute, *args)
    r.score = lambda *args: guarded.score_with_unavailable(old_score, *args)
    old_summarize = r.summarize
    def summarize(module, rows):
        out = old_summarize(module, rows)
        out['trait_accounting'] = {'available': False, 'unmeasured_responses': len(rows),
            'note': 'Compact note-level contract cannot measure per-sentence trait loss; do not interpret as zero loss.'}
        return out
    r.summarize = summarize
    argv = ['--stage', 'd14_dev8', '--run-dir', a.run_dir]
    if a.ledger: argv += ['--ledger', a.ledger]
    if a.execute: argv.append('--execute')
    r.main(argv)


if __name__ == '__main__': main()
