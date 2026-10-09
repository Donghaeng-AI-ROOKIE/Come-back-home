"""Offline container replay. No credentials, network, live users, or model calls."""
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import json, sys
from fastapi.testclient import TestClient
from app import storage
from app.config import settings
from app.main import app
from app.schemas.persona import Persona
from app.phase0 import person_preparation as pp, mind_preparation as mp
from app.phase2 import pipeline, refresher
from app.llm.mind_policy_profiles import selected

stage=sys.argv[1]
assert settings.mind_policy_contract=='guarded_core'
assert settings.storage_db_path.startswith('/verification-data/')
settings.privacy_admin_key='synthetic-only'
settings.layer2_periodic_minutes=60
root=Path('/verification-data');fixture=Path('/verification-fixtures')
calls=[]
def read(name):return json.loads((fixture/name).read_text())
def replay(url,body,**kw):
    calls.append(1)
    return {'choices':[{'finish_reason':'stop','message':{'content':read('mind_public.json')['final_content']}}]}
def no_call(*a,**k):raise AssertionError('Unexpected external request')
start=datetime(2026,10,9,8)
client=TestClient(app)
with ExitStack() as stack:
    # Only external model replies are replayed. Actual packaged candidate and
    # verified KINTEX loader, API, prediction, persistence and closure run.
    stack.enter_context(patch.object(mp,'logged_json_request',replay if stage=='prepare' else no_call))
    stack.enter_context(patch.object(pipeline.exaone,'generate_prior',lambda p,r:pipeline.exaone._default_prior(p,r)))
    stack.enter_context(patch.object(pipeline.situation_link,'cached',lambda *a:[]))
    if stage=='prepare':
        p=Persona.model_validate(read('persona.json'))
        initial=read('initial.json')
        p.prepared_initial={'core':initial['core'],'scope':initial['context'],'fingerprint':pp.fingerprint(p)}
        p.initial_preparation_status={'state':'ready','fingerprint':pp.fingerprint(p)}
        p.prepared_mind={};p.mind_preparation_status={}
        storage.personas.save(p.id,p)
        mp.prepare(p.id)
        saved=storage.personas.get(p.id)
        assert mp.ready(saved)[1]=='ready' and len(calls)==1
        assert saved.prepared_mind['interpretation_contract']==selected().VERSION
        r=client.post('/phase1/reports',json={'missing_type':'dementia','persona_id':p.id,
            'lkp':p.home.model_dump(),'lkp_time':start.isoformat()})
        assert r.status_code==200,r.text
        case_id=r.json()['id']
        (root/'case_id.txt').write_text(case_id)
        case=storage.cases.get(case_id)
        pipeline.run_prediction(case,now=start+timedelta(hours=1),seed=17)
        q=storage.cases.get(case_id).prediction_quality
        assert q['personal_policy_status']=='ready' and q['unresolved_mass']==0
        result={'stage':stage,'contract':selected().VERSION,'replayed_model_responses':len(calls),
            'model_calls':0,'quality':q,'sqlite_saved':True}
    else:
        case_id=(root/'case_id.txt').read_text()
        case=storage.cases.get(case_id)
        p=storage.personas.get(case.report.persona_id)
        assert mp.ready(p)[1]=='ready'
        hours=[]
        for h in (2,4,6):
            assert refresher.refresh_due_cases(now=start+timedelta(hours=h))
            current=storage.cases.get(case_id)
            q=current.prediction_quality
            assert q['unresolved_mass']==0 and q['checkpoint_reused']
            assert all(abs(x['minute']-h*60)<1e-7 for x in current.continuous_state['checkpoint']['particles'])
            assert all(abs(x['minute']-h*60)<1e-7 for x in current.continuous_state['statistical']['checkpoint']['particles'])
            hours.append({'hour':h,'quality':q})
        assert not calls
        r=client.post('/privacy/cases/'+case_id+'/close',json={'reason':'found'},
            headers={'x-privacy-admin-key':'synthetic-only'})
        assert r.status_code==200
        assert client.post('/phase2/cases/'+case_id+'/predict').status_code==409
        result={'stage':stage,'restored_in_new_container':True,'model_calls':0,
            'hourly':hours,'found_blocks_prediction':True}
    (root/(stage+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k not in ('quality','hourly')}))
