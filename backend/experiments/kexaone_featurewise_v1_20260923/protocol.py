"""Feature-envelope checks and the unchanged legacy prior validation. No model judge."""
import json
from legacy_protocol import inspect as legacy_inspect, STRATEGIES
FEATURES={'destination_pull','movement_persistence','route_shape','mobility_range'}
def inspect(content,case,condition):
    if condition=='CONTROL':return legacy_inspect(content,case,'SAR_K')
    assert condition=='FEATURES'
    result={'envelope_valid':False,'envelope_errors':[],'prior_usable':False};errors=result['envelope_errors']
    try:value=json.loads(content)
    except (ValueError,TypeError):
        errors.append('not_standalone_json')
        try:value=json.loads(content[content.index('{'):content.rindex('}')+1])
        except (ValueError,TypeError,AttributeError):return result
    if not isinstance(value,dict):errors.append('not_object');return result
    result['structured']=value
    if set(value)!={'features','integration','prior'}:errors.append('envelope_keys')
    notes={f'N{i}':n for i,n in enumerate(case['notes'])};refs=set(notes)|{f'R{i}' for i in range(4)}|{'SAR_REF'};seen=set()
    def texts(x,lo,hi):return isinstance(x,list) and lo<=len(x)<=hi and all(isinstance(v,str) and v.strip() for v in x)
    fs=value.get('features')
    if not isinstance(fs,dict) or set(fs)!=FEATURES:errors.append('feature_keys')
    if isinstance(fs,dict):
        for key,feature in fs.items():
            prefix='feature.'+key+'.'
            if not isinstance(feature,dict):errors.append(prefix+'not_object');continue
            if set(feature)!={'personal_evidence','domain_hypotheses','unknowns','conclusion'}:errors.append(prefix+'fields')
            obs=feature.get('personal_evidence')
            if not isinstance(obs,list) or len(obs)>2:errors.append(prefix+'evidence_count')
            else:
                for x in obs:
                    if not isinstance(x,dict) or set(x)!={'note_id','quote'}:errors.append(prefix+'evidence_fields');continue
                    n=x['note_id'];q=x['quote']
                    if not isinstance(n,str) or n not in notes or not isinstance(q,str) or not q.strip() or q not in notes[n]:errors.append(prefix+'quote_not_in_note')
                    else:seen.add(n)
            hs=feature.get('domain_hypotheses')
            if not isinstance(hs,list) or len(hs)>1:errors.append(prefix+'hypotheses_count')
            else:
                for h in hs:
                    if not isinstance(h,dict) or set(h)!={'basis','claim','limitation'}:errors.append(prefix+'hypothesis_fields');continue
                    if not texts(h['basis'],1,7) or not all(x in refs for x in h['basis']):errors.append(prefix+'hypothesis_refs')
                    if not all(isinstance(h[k],str) and h[k].strip() for k in ['claim','limitation']):errors.append(prefix+'hypothesis_text')
            if not texts(feature.get('unknowns'),0,2):errors.append(prefix+'unknowns')
            if not isinstance(feature.get('conclusion'),str) or not feature.get('conclusion','').strip():errors.append(prefix+'conclusion')
    if seen!=set(notes):errors.append('missing_note_coverage')
    places={a['label'] for a in case['persona']['attraction_points']}
    targets={f'strategy_probs.{s}' for s in STRATEGIES}|{f'attraction_levels.{p}' for p in places}|{'radius_level'}
    integration=value.get('integration')
    if not isinstance(integration,list) or not 2<=len(integration)<=4:errors.append('integration_count')
    else:
        for x in integration:
            if not isinstance(x,dict) or set(x)!={'target','feature_refs','action','reason'}:errors.append('integration_fields');continue
            if not isinstance(x['target'],str) or x['target'] not in targets:errors.append('integration_target')
            if not texts(x['feature_refs'],1,4) or not all(k in FEATURES for k in x['feature_refs']):errors.append('integration_feature_refs')
            if x['action'] not in ('increase','decrease','maintain','uncertain'):errors.append('integration_action')
            if not isinstance(x['reason'],str) or not x['reason'].strip():errors.append('integration_reason')
    # Use exactly the previous prior validation; ignore its envelope rules for this new schema.
    priorcheck=legacy_inspect(json.dumps({'prior':value.get('prior')},ensure_ascii=False),case,'SAR_K')
    result['prior_errors']=priorcheck.get('prior_errors',['missing_prior'])
    result['prior_usable']=priorcheck['prior_usable']
    if 'strategy_sum_not_one_normalized_by_existing_code' in priorcheck['envelope_errors']:errors.append('strategy_sum_not_one_normalized_by_existing_code')
    result['envelope_valid']=not errors and not result['prior_errors']
    return result
