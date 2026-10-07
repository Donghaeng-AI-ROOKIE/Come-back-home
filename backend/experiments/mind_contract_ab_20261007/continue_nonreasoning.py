"""Execute registered D10/D11 calls, then source-condition and KINTEX checks."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from experiments.mind_contract_ab_20261007 import run_v2 as r, audit_repair8, run_repair8, condition_probe


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('out', 'ledger', 'reference-walks', 'frozen-backend', 'map'):
        p.add_argument('--' + key, type=Path, required=True)
    a = p.parse_args(); a.out.mkdir(parents=True, exist_ok=True)
    def mark(state, **kwargs):
        r.write(a.out / 'continuation_status.json', {'state': state,
            'updated_at': datetime.now(timezone.utc).isoformat(), **kwargs})
    def run(module, args, label):
        mark('running', step=label)
        with (a.out / (label + '.log')).open('a') as f:
            done = subprocess.run([sys.executable, '-m', 'experiments.mind_contract_ab_20261007.' + module,
                                   *map(str, args)], stdout=f, stderr=subprocess.STDOUT, cwd=r.BACKEND)
        if done.returncode:
            mark('needs_diagnosis', step=label, exit_code=done.returncode); raise SystemExit(done.returncode)
    for cand in ('d10', 'd11'):
        stage = cand + '_dev8'; f = a.out / stage
        run('run_nonreasoning', ['--candidate', cand, '--run-dir', a.out, '--ledger', a.ledger, '--execute'], stage)
        scored = r.read(f / 'scored.json')
        if not scored['summary']['complete']:
            mark('needs_diagnosis', reason='incomplete batch'); raise SystemExit(2)
        _, _, refs, _ = run_repair8.repair_dataset()
        r.write(f / 'condition_probes.json', condition_probe.audit(scored, refs))
        r.write(f / 'usage_summary.json', audit_repair8.usage(a.ledger, stage))
        run('walk_repair8', ['--scored', f / 'scored.json', '--reference-walks', a.reference_walks,
            '--frozen-backend', a.frozen_backend, '--map', a.map,
            '--output', f / 'engine_outputs_reused_v2.json'], stage + '_walk')
    mark('comparison_complete_not_release_verdict')


if __name__ == '__main__': main()
