"""Replay the captured D12 policy with the place-bound research executor.

Explicit local experiment substitution; no API route or deployed code changes.
The frozen old captured_walk harness and every recorded input are retained.
"""
from pathlib import Path
import sys
import hashlib
import json


def main():
    backend = Path(sys.argv[sys.argv.index('--product-backend')+1]).resolve()
    output = Path(sys.argv[sys.argv.index('--output')+1])
    if output.exists(): raise SystemExit('preserve completed replay')
    sys.path.insert(0, str(backend))
    from app.phase2 import person_walk, place_bound_walk
    assert Path(person_walk.__file__).resolve().is_relative_to(backend)
    assert Path(place_bound_walk.__file__).resolve().is_relative_to(backend)
    person_walk.Population = place_bound_walk.PlaceBoundPopulation
    from experiments.mind_contract_ab_20261007 import captured_walk
    evidence = {'executor': 'PlaceBoundPopulation', 'source_sha256': {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
        (Path(__file__), Path(captured_walk.__file__), Path(person_walk.__file__), Path(place_bound_walk.__file__))},
        'source_policy_or_persona_modified': False, 'new_place_recognition_observations': [],
        'purpose': 'regression of other captured traits; named arrival covered separately',
        'new_external_calls': 0, 'release_qualified': False}
    marker = output.with_name(output.name+'.wrapper.json')
    if marker.exists(): raise SystemExit('wrapper was already started; inspect before restarting')
    marker.write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n')
    captured_walk.main()
    (output/'executor_manifest.json').write_text(marker.read_text())


if __name__ == '__main__': main()
