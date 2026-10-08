"""Offline KINTEX check for all 48 expanded D12 outputs, invalid ones included."""
from pathlib import Path
import sys
from experiments.mind_contract_ab_20261007 import run_v2 as r, run_compact24 as wide, walk_repair8, walk_dev8_reuse as reuse


def main():
    original=r.dataset
    r.dataset=lambda stage:wide.expanded_dataset() if stage=='d3_dev8' else original(stage)
    reuse.check_inputs=walk_repair8.check_inputs
    reuse.main()
    out=Path(sys.argv[sys.argv.index('--output')+1]);result=r.read(out)
    result['scope']='24 synthetic development people x 2; expanded KINTEX diagnostic, not independent release/clinical evaluation'
    result['selected_input_ids']=[x['id'] for x in wide.expanded_dataset()[0]]
    result['runner_source_sha256']={str(p):reuse.sha(p) for p in
        (Path(__file__),Path(wide.__file__),Path(reuse.__file__),Path(walk_repair8.__file__))}
    r.write(out,result)


if __name__=='__main__':main()
