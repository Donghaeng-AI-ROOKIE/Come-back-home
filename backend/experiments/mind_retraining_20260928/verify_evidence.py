"""Recompute published counts from saved artifacts. No network or model calls."""
from pathlib import Path
import json,hashlib,sys,re
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D/'lora'))
from evaluate_saved import evaluate

def read(p):return json.loads((D/p).read_text())
def main():
    for f in read('SOURCE_MANIFEST.json')['files']:
        assert hashlib.sha256((D/f['published']).read_bytes()).hexdigest()==f.get('published_sha256',f['sha256']),f['published']
    b=read('evidence/baseline/results.json');s=read('evidence/baseline/summary.json')
    assert len(b)==s['calls']==36
    assert sum(r['usage']['prompt_tokens'] for r in b)==s['input_tokens']==20226
    assert sum(r['usage']['completion_tokens'] for r in b)==s['output_tokens']==2323
    r=next(r for r in b if r['id']=='rest__fatigue__r2')
    assert json.loads(r['raw'])['behavior']=='계속 배회' and '앉고 싶다' in r['raw']
    k=read('evidence/grounded/c5/evaluation_k.json');ks=read('evidence/grounded/c5/evaluation_summary.json')
    assert len(k)==48 and len({r['case'] for r in k})==24
    assert sum(r['contract_pass'] for r in k)==ks['contract_pass']==48
    assert sum(r['automatic_match'] for r in k)==ks['allowed_action_goal_feature_match']==35
    kr=read('evidence/grounded/c5/evaluation_semantic_review.json')
    assert sum(r['critical_action_violation'] for r in kr)==13
    assert sum(r['critical_environment_claim'] and r['automatic_match'] for r in kr)==3
    summary,comparison=evaluate(D/'lora/dataset_v2/development.jsonl',D/'lora/results')
    assert summary==read('lora/results/evaluation_summary.json')
    assert summary['candidates']['lora_final']['action_tuple_match']==9
    assert summary['candidates']['lora_final']['contract_pass']==16
    fields=('status','action','goal_operation','goal_label','avoid_feature')
    readable={}
    for tag in ['base','lora_final']:
        exact=0
        for r in comparison:
            if r['candidate']!=tag:continue
            raw=r['raw'];m=re.match(r'^\s*```(?:json)?\s*\n(.*?)\n```',raw,re.S)
            v=json.loads(m.group(1) if m else raw)
            exact+=all(v.get(k)==r['expected'][k] for k in fields)
        readable[tag]=exact
    assert readable=={'base':1,'lora_final':9}
    review=read('lora/results/lora_explanation_review.json')
    assert sum(r['assessment']=='행동 일치·설명 문제' for r in review['rows'])==5
    usage=read('lora/results/usage_summary.json')
    assert sum(r['usage']['input_tokens'] for r in comparison)==usage['input_tokens']==40246
    assert sum(r['usage']['output_tokens'] for r in comparison)==usage['output_tokens']==8283
    assert read('lora/results/service_result.json')['service_restored'] is True
    graph=D.parents[1]/'tests/fixtures/kintex_walk.graphml'
    assert hashlib.sha256(graph.read_bytes()).hexdigest()==read('evidence/kintex/검증결과.json')['sha256']
    assert read('evidence/kintex/검증결과.json')['scripted_provider'] is True
    print('PASS: archive hashes, baseline36, K48, LoRA32, diagnostic1→9, explanation5, usage, service restoration, KINTEX hash')

if __name__=='__main__':main()
