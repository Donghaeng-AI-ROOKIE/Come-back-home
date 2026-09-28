"""Offline archive integrity and numerical checks; never invokes a model."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parent
for f in json.loads((R/'SOURCE_MANIFEST.json').read_text())['files']:
 assert hashlib.sha256((R/f['published']).read_bytes()).hexdigest()==f['published_sha256'],f['published']
rows=[json.loads(x) for x in (R/'results/comparison.jsonl').read_text().splitlines()]
assert len(rows)==96 and len({(r['arm'],r['epoch'],r['id']) for r in rows})==96
score=json.loads((R/'results/evaluation_summary.json').read_text())['scores']
review=json.loads((R/'results/explanation_review.json').read_text())
for arm,expected,joint in [('original72',[12,11,13],[7,9,9]),('augmented120',[10,13,12],[5,8,10])]:
 for ep,n,j in zip([2,4,6],expected,joint):
  key=f'{arm}_epoch{ep}';group=[r for r in rows if r['arm']==arm and r['epoch']==ep]
  assert len(group)==16 and sum(r['raw_contract_pass'] for r in group)==16
  assert sum(r['action_match'] and r['raw_contract_pass'] for r in group)==score[key]['strict_action_match']==n
  reviews=[r for r in review['rows'] if r['arm']==arm and r['epoch']==ep]
  assert len(reviews)==16 and sum(r['joint_pass'] for r in reviews)==review['scores'][key]['joint_pass']==j
u=json.loads((R/'results/usage_summary.json').read_text())
assert sum(r['usage']['input_tokens'] for r in rows)==u['input_tokens_known']==120738
assert sum(r['usage']['output_tokens'] for r in rows)==u['output_tokens_known']==9114
assert u['generation_attempts']==u['generation_finished']==96
assert u['training_attempts']==u['training_finished']==2
service=json.loads((R/'results/service_control/result.json').read_text())
assert service['service_restored'] and service['midm_original_process_alive']
print('PASS: source hashes, 96 outputs, six comparisons, explanation annotations, token totals, service restoration')
