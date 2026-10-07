"""Export synthetic SFT candidates; this does not start or approve GPU training."""
import hashlib,json
from pathlib import Path
import motion_goal_candidate as contract
D=Path(__file__).resolve().parent
def main():
    source=D/'personal_contrasts_v5';out=D/'training_export_v2';out.mkdir(exist_ok=False)
    if json.loads((source/'mechanical_audit.json').read_text())['status']!='PASS':raise ValueError('audit failed')
    files={}
    # Never export held-out evaluation into the trainer package.
    for split in ('train','development'):
        rows=list(map(json.loads,(source/(split+'.jsonl')).read_text().splitlines()));converted=[]
        for row in rows:
            c=row['context'];expected=row['expected_output'];contract.validate(expected,c)
            payload=contract.payload(c,'separate_motion_and_goal','not-an-api-call')
            messages=payload['messages']+[dict(role='assistant',content=json.dumps(expected,ensure_ascii=False))]
            converted.append(dict(id=row['id'],group_id=row['group_id'],person_id=row['person_id'],lineage_id=row['lineage_id'],variant=row['variant'],
                messages=messages,expected_output=expected,source_sha256=hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
                clinical_observation=False,real_frontend_output=False))
        outputs={split:converted}
        if split=='train':outputs['train_base']=[r for r in converted if r['variant']==0]
        for name,data in outputs.items():
            p=out/(name+'.jsonl');p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in data))
            files[p.name]=dict(rows=len(data),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    manifest=dict(status='tokenization_candidate_only_not_trained',files=files,source_version='personal_contrasts_v5',
        contract='motion_goal_candidate: separate_motion_and_goal (development candidate, not adopted)',human_review=False,clinical_validation=False,
        cpu_tokenization_allowed=True,gpu_training_started=False,evaluation_included=False)
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
