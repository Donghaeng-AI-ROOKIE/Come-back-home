"""Local source/observation/partition/command audit, without external calls."""
import collections, copy, hashlib, json
from pathlib import Path
import observation_contract_v2 as contract
from build_personal_contrasts import policy_results
D=Path(__file__).resolve().parent

def at(value,path):
    for key in path.strip('/').split('/'):
        value=value[int(key)] if isinstance(value,list) else value[key]
    return value

def audit(root):
    manifest=json.loads((root/'manifest.json').read_text());errors=[];splits={};report={}
    for name,entry in manifest['files'].items():
        path=root/name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:errors.append([name,'hash'])
        rows=[json.loads(x) for x in path.read_text().splitlines()];splits[name]=rows
        by_lineage=collections.defaultdict(list);by_pair=collections.defaultdict(list)
        for r in rows:
            by_lineage[r['lineage_id']].append(r)
            by_pair[r['contrast_id']].append(r)
            oracle=r['authoring_oracle'];expected=r['expected_output'];c=r['context']
            if [at(c,p) for p in oracle['fact_paths']]!=oracle['values']:errors.append([r['id'],'observation mismatch'])
            try:
                contract.base.validate(expected,c)
                if len(expected['reason'])>400:raise ValueError('reason too long')
                body=contract.payload(c,'audit-only-no-call')
                if 'authoring_oracle' in body['messages'][1]['content'] or 'expected_output' in body['messages'][1]['content']:raise ValueError('oracle leaked')
            except Exception as exc:errors.append([r['id'],type(exc).__name__+':'+str(exc)])
            source='N2' if oracle['kind']=='correction' else 'N1'
            if expected['source_ids']!=[source]:errors.append([r['id'],'source correction mismatch'])
            if r['quality']['clinical_observations']!=0 or r['quality']['real_frontend_output']:errors.append([r['id'],'provenance'])
        for group in by_lineage.values():
            if len({json.dumps(r['expected_output'],sort_keys=True) for r in group})!=1:errors.append([group[0]['lineage_id'],'augmentation changed label'])
        different=0
        for pair in by_pair.values():
            if len(pair)!=2:errors.append([pair[0]['contrast_id'],'pair incomplete']);continue
            contexts=[]
            for r in pair:
                c=copy.deepcopy(r['context'])
                for k in ('case_id','person_id','person_revision','person'):c.pop(k,None)
                contexts.append(c)
            if contexts[0]!=contexts[1]:errors.append([pair[0]['contrast_id'],'scene changed with person'])
            different+=pair[0]['expected_output']['next_command_id']!=pair[1]['expected_output']['next_command_id']
        report[name]=dict(rows=len(rows),lineages=len(by_lineage),paired_states=len(by_pair),
            different_person_action_pairs=different,
            scene_only_oracle_upper_bound=(len(rows)-different)/len(rows),
            action_counts=dict(collections.Counter(r['expected_output']['next_command_id'] for r in rows)),
            kind_counts=dict(collections.Counter(r['authoring_oracle']['kind'] for r in rows)))
        required={'continue','rest','stay','roam','seek_1','defer','avoid_park','avoid_market','avoid_forest','avoid_water'}
        if required-set(report[name]['action_counts']):errors.append([name,'missing command coverage',sorted(required-set(report[name]['action_counts']))])
    names=list(splits)
    for i,a in enumerate(names):
        for b in names[i+1:]:
            for key in ('group_id','person_id','lineage_id'):
                if {r[key] for r in splits[a]}&{r[key] for r in splits[b]}:errors.append([a,b,key,'overlap'])
            if {r['authoring_oracle']['pair_key'] for r in splits[a]}&{r['authoring_oracle']['pair_key'] for r in splits[b]}:errors.append([a,b,'observation pair overlap'])
            if {n['text'] for r in splits[a] for n in r['context']['person']['evidence_notes']}&{n['text'] for r in splits[b] for n in r['context']['person']['evidence_notes']}:errors.append([a,b,'exact source overlap'])
    result=dict(status='PASS' if not errors else 'FAIL',errors=errors,splits=report,
        scope='mechanical consistency only; no independent human or clinical validation',
        training_ready=False,semantic_template_review_required=True)
    (root/'mechanical_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result

def test_independent_truth_examples():
    assert policy_results('and',(False,None),'rest','stay')==(['continue'],'continue')
    assert policy_results('and',(True,None),'rest','stay')==(['continue','rest'],'defer')
    assert policy_results('or',(True,None),'rest','stay')==(['rest'],'rest')
    assert policy_results('unless',(True,True),'rest','stay')==(['continue'],'continue')
    assert policy_results('unless',(True,None),'rest','stay')==(['continue','rest'],'defer')
    assert policy_results('priority',(True,None),'rest','stay')==(['rest'],'rest')
    assert policy_results('priority',(None,True),'rest','stay')==(['rest','stay'],'defer')
    assert policy_results('single',(None,False),'continue','stay')==(['continue'],'continue')

if __name__=='__main__':
    test_independent_truth_examples()
    result=audit(D/'personal_contrasts_v3')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if result['errors']:raise SystemExit(1)
