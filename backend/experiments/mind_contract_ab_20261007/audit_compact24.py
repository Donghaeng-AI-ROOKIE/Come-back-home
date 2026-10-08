"""Pair the complete expansion against saved D4; no model calls or gold edits."""
import argparse
from pathlib import Path
from experiments.mind_contract_ab_20261007 import run_v2 as r, run_compact24 as wide, audit_repair8, condition_probe


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--before',type=Path,required=True)
    p.add_argument('--ledger',type=Path,required=True)
    a=p.parse_args()
    s=r.read(a.out/'scored.json')
    if not s or not s['summary']['complete']:raise SystemExit('expansion incomplete')
    inputs,_,refs,_=wide.expanded_dataset()
    expected={(x['id'],rep) for x in inputs for rep in (1,2)}
    if len(s['rows'])!=48 or {(x['input_id'],x['rep']) for x in s['rows']}!=expected:
        raise ValueError('expanded denominator differs')
    old=r.read(a.before)
    before={'rows':[x for x in old['rows'] if (x['input_id'],x['rep']) in expected]}
    paired=audit_repair8.paired(before,s)
    probes=condition_probe.audit(s,refs)
    old_probes=condition_probe.audit(before,refs)
    r.write(a.out/'condition_probes.json',probes)
    r.write(a.out/'d4_condition_probes.json',old_probes)
    r.write(a.out/'paired_with_d4.json',paired)
    costs=audit_repair8.usage(a.ledger,wide.STAGE)
    r.write(a.out/'usage_summary.json',costs)
    r.write(a.out/'iteration_audit.json',{
        'scope':'expanded development; same source and authored reference; not clinical accuracy',
        'scored_sha256':r.digest(a.out/'scored.json'),'d4_scored_sha256':r.digest(a.before),
        'd4_scene_passed':sum(t['pass'] for x in before['rows'] for t in x['scenes']),
        'd12_scene_passed':s['summary']['passed'],'scene_total':192,
        'd4_valid':sum(x['policy'] is not None for x in before['rows']),
        'd12_valid':s['summary']['final_valid'],'responses':48,
        'd4_probes':old_probes['summary'],'d12_probes':probes['summary'],
        'paired':{k:v for k,v in paired.items() if k!='rows'},'costs':costs,'release_qualified':False})
    print((a.out/'iteration_audit.json').read_text())


if __name__=='__main__':main()
