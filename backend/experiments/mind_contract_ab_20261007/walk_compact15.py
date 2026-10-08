"""Same frozen KINTEX benchmark for every D15 output, including invalid ones."""
from pathlib import Path
import sys
from experiments.mind_contract_ab_20261007 import run_v2 as r, run_compact15 as selected, walk_repair8, walk_dev8_reuse as reuse


def main():
    original=r.dataset
    r.dataset=lambda stage:selected.selected_dataset() if stage=='d3_dev8' else original(stage)
    reuse.check_inputs=walk_repair8.check_inputs
    reuse.main()
    out=Path(sys.argv[sys.argv.index('--output')+1]);result=r.read(out)
    result['scope']='D15 eight selected development failures/controls x2; no clinical or independent evaluation'
    result['selected_input_ids']=list(selected.IDS)
    result['runner_source_sha256']={str(p):reuse.sha(p) for p in
        (Path(__file__),Path(selected.__file__),Path(reuse.__file__),Path(walk_repair8.__file__))}
    r.write(out,result)


if __name__=='__main__':main()
