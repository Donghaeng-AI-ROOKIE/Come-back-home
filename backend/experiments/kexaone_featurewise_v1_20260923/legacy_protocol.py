"""Offline structural checks. They do not prove a behavioral hypothesis is true."""
import json,math,re
STRATEGIES={'route_following','direction_keeping','random_walk','backtracking','staying_put','landmark_seeking'}
def inspect(content,case,condition):
    out={'envelope_valid':False,'envelope_errors':[],'prior_usable':False};errors=out['envelope_errors']
    try:
        value=json.loads(content)
    except (ValueError,TypeError):
        errors.append('not_standalone_json')
        try:value=json.loads(content[content.index('{'):content.rindex('}')+1])
        except (ValueError,TypeError,AttributeError):return out
    if not isinstance(value,dict):errors.append('not_object');return out
    out['structured']=value
    if set(value)!={'observations','hypotheses','unknowns','decisions','prior'}:errors.append('envelope_keys')
    notes={f'N{i}':n for i,n in enumerate(case['notes'])};refs=set(notes)|{f'R{i}' for i in range(4)}
    if condition=='SAR_K':refs.add('SAR_REF')
    obs=value.get('observations');ids=set()
    if not isinstance(obs,list) or not 2<=len(obs)<=3:errors.append('observations_count')
    else:
        for x in obs:
            if not isinstance(x,dict) or set(x)!={'note_id','quote'}:errors.append('observation_keys');continue
            note=x['note_id'];quote=x['quote']
            if not isinstance(note,str) or note not in notes or not isinstance(quote,str) or not quote.strip() or quote not in notes[note]:errors.append('observation_quote_not_in_note')
            else:ids.add(note)
        if ids!=set(notes):errors.append('missing_note_coverage')
    hs=value.get('hypotheses');hids=set()
    def validrefs(x,allowed):return isinstance(x,list) and bool(x) and all(isinstance(k,str) and k in allowed for k in x)
    if not isinstance(hs,list) or not 1<=len(hs)<=3:errors.append('hypotheses_count')
    else:
        for h in hs:
            if not isinstance(h,dict) or set(h)!={'id','claim','basis','limitation'}:errors.append('hypothesis_keys');continue
            if not isinstance(h['id'],str) or not re.fullmatch(r'H[1-9][0-9]*',h['id']) or h['id'] in hids:errors.append('hypothesis_id')
            elif isinstance(h['id'],str):hids.add(h['id'])
            if not all(isinstance(h[k],str) and h[k].strip() for k in ['claim','limitation']):errors.append('hypothesis_text')
            if not validrefs(h['basis'],refs):errors.append('hypothesis_refs')
    unknown=value.get('unknowns')
    if not isinstance(unknown,list) or not 1<=len(unknown)<=3 or not all(isinstance(x,str) and x.strip() for x in unknown):errors.append('unknowns')
    places={a['label'] for a in case['persona']['attraction_points']}
    allowedtargets={f'strategy_probs.{s}' for s in STRATEGIES}|{f'attraction_levels.{p}' for p in places}|STRATEGIES|places|{'radius_level'}
    dec=value.get('decisions')
    if not isinstance(dec,list) or not 2<=len(dec)<=4:errors.append('decisions_count')
    else:
        for x in dec:
            if not isinstance(x,dict) or set(x)!={'target','basis','reason'}:errors.append('decision_keys');continue
            if not isinstance(x['target'],str) or x['target'] not in allowedtargets:errors.append('decision_target')
            if not validrefs(x['basis'],refs|hids):errors.append('decision_refs')
            if not isinstance(x['reason'],str) or not x['reason'].strip():errors.append('decision_reason')
    prior=value.get('prior');pe=[]
    if not isinstance(prior,dict):pe.append('missing_prior')
    else:
        if set(prior)!={'strategy_probs','attraction_levels','radius_level','reasoning'}:pe.append('prior_keys')
        probs=prior.get('strategy_probs')
        if not isinstance(probs,dict) or set(probs)!=STRATEGIES or not all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in probs.values()) or sum(probs.values())<=0:pe.append('strategy_numbers')
        elif abs(sum(probs.values())-1)>1e-6:errors.append('strategy_sum_not_one_normalized_by_existing_code')
        levels=prior.get('attraction_levels')
        if not isinstance(levels,dict) or set(levels)!=places or not all(v in ('상','중','하') for v in levels.values()):pe.append('attraction_levels')
        if prior.get('radius_level') not in ('상','중','하'):pe.append('radius_level')
        if not isinstance(prior.get('reasoning'),str) or not prior.get('reasoning','').strip():pe.append('reasoning')
    out['prior_errors']=pe;out['prior_usable']=not pe
    out['envelope_valid']=not errors and not pe
    return out
