"""Configured app path and failure recovery, with captured replies; no paid calls."""
import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
from app import storage
from app.config import settings
from app.llm import mind_policy as m, mind_policy_guarded_core as guarded
from app.phase0 import mind_preparation as mp, person_preparation as pp, persona_events
from app.schemas.persona import Persona
from app.main import app
from app.cloud_bridge.policy import authorize

FIXTURE=Path(__file__).parent/'fixtures/service_connection'
OWNER=str(uuid4())

@pytest.fixture
def prepared(monkeypatch):
    storage.reset_for_tests()
    for name,value in dict(mind_policy_deployment='staging',mind_policy_contract='guarded_core',
            kexaone_api_key='offline',kexaone_base_url='https://offline.invalid',kexaone_model='offline',
            persist_storage=False).items():monkeypatch.setattr(settings,name,value)
    p=Persona.model_validate(json.loads((FIXTURE/'persona.json').read_text()))
    initial=json.loads((FIXTURE/'initial.json').read_text())
    p.guardian_id=OWNER
    p.initial_preparation_status={'state':'ready','fingerprint':pp.fingerprint(p)}
    p.prepared_initial={'core':initial['core'],'scope':initial['context'],'fingerprint':pp.fingerprint(p)}
    p.prepared_mind={};p.mind_preparation_status={}
    storage.personas.save(p.id,p)
    jobs=[];calls=[];notices=[]
    monkeypatch.setattr(pp,'_dispatch',lambda *a:jobs.append(a))
    raw=json.loads(json.loads((FIXTURE/'mind_public.json').read_text())['final_content'])
    def reply(url,body,**kwargs):
        calls.append(body)
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(raw)}}]}
    monkeypatch.setattr(mp,'logged_json_request',reply)
    monkeypatch.setattr(persona_events,'notify_persona_updated',lambda *a:notices.append(a))
    yield p,jobs,calls,notices
    storage.reset_for_tests()

def test_guarded_profile_selected_from_config_and_reused(prepared):
    p,jobs,calls,notices=prepared
    first=pp.enqueue(p.id,retry=True)
    assert first.initial_preparation_status['state']=='ready'
    assert first.prepared_initial==p.prepared_initial
    assert len(jobs)==1 and jobs[0][2]=='mind'
    assert pp.enqueue(p.id,retry=True) is None
    mp.run_queued(*jobs[0][:2])
    saved=storage.personas.get(p.id)
    assert saved.prepared_mind['interpretation_contract']==guarded.VERSION
    assert len(calls)==1 and len(notices)==1
    assert mp.ready(saved)[1]=='ready'
    pp.enqueue(p.id,retry=True);mp.run_queued(*jobs[0][:2])
    assert len(jobs)==1 and len(calls)==1 and len(notices)==1
    assert saved.prepared_initial==p.prepared_initial

def test_contract_change_invalidates_only_mind(prepared,monkeypatch):
    p,jobs,calls,_=prepared
    mp.prepare(p.id)
    ready=storage.personas.get(p.id)
    monkeypatch.setattr(settings,'mind_policy_contract','sourced_followup')
    assert mp.ready(ready)[1]=='stale'
    assert mp.status(ready)['can_retry']
    updated=pp.enqueue(p.id,retry=True)
    assert updated.prepared_initial==p.prepared_initial
    assert updated.mind_preparation_status['state']=='queued' and len(calls)==1

def test_restart_resumes_unstarted_queue_but_not_billable_running_job(prepared):
    p,jobs,calls,_=prepared
    pp.enqueue(p.id,retry=True)
    jobs.clear();mp.recover()
    assert len(jobs)==1 and not calls
    cur=storage.personas.get(p.id)
    cur.mind_preparation_status['state']='running';storage.personas.save(p.id,cur)
    jobs.clear();mp.recover()
    assert not jobs and not calls
    assert mp.status(storage.personas.get(p.id))['mind_state']=='interrupted'
    pp.enqueue(p.id,retry=True);mp.run_queued(*jobs[0][:2])
    assert len(calls)==1

def test_failure_preserves_initial_and_requires_explicit_retry(prepared,monkeypatch):
    p,jobs,calls,notices=prepared
    def fail(*a,**kw):raise TimeoutError('secret-source-and-key')
    monkeypatch.setattr(mp,'logged_json_request',fail)
    pp.enqueue(p.id,retry=True);mp.run_queued(*jobs[0][:2])
    saved=storage.personas.get(p.id)
    assert saved.prepared_initial==p.prepared_initial and mp.status(saved)['can_retry']
    assert not notices and 'secret-source' not in json.dumps(saved.mind_preparation_status)
    assert mp.enqueue(p.id) is None
    assert len(jobs)==1
    pp.enqueue(p.id,retry=True)
    assert len(jobs)==2

@pytest.mark.parametrize('mutation',['edit','delete'])
def test_late_mind_completion_cannot_restore_old_profile(prepared,monkeypatch,mutation):
    p,jobs,_,notices=prepared
    original=mp.logged_json_request
    def reply(*a,**kw):
        result=original(*a,**kw)
        if mutation=='delete':storage.personas.delete(p.id)
        else:
            cur=storage.personas.get(p.id);cur.version+=1;cur.prepared_mind={}
            storage.personas.save(p.id,cur)
        return result
    monkeypatch.setattr(mp,'logged_json_request',reply)
    pp.enqueue(p.id,retry=True);mp.run_queued(*jobs[0][:2])
    saved=storage.personas.get(p.id)
    assert saved is None if mutation=='delete' else not saved.prepared_mind
    assert not notices

def test_old_queued_revision_is_visible_and_can_be_replaced(prepared,monkeypatch):
    p,jobs,_,_=prepared
    pp.enqueue(p.id,retry=True)
    old=jobs[0]
    monkeypatch.setattr(settings,'mind_policy_contract','sourced_followup')
    assert mp.status(storage.personas.get(p.id))['can_retry']
    pp.enqueue(p.id,retry=True)
    mp.run_queued(*old[:2])
    assert storage.personas.get(p.id).mind_preparation_status['state']=='queued'
    assert len(jobs)==2

def test_public_status_is_read_only_owner_scoped_and_never_contains_source(prepared):
    p,jobs,calls,_=prepared
    client=TestClient(app)
    path=f'/phase0/personas/{p.id}/preparation'
    assert authorize(OWNER,'GET',path,None).path==path
    for method,suffix in [('GET','preparation'),('POST','prepare')]:
        with pytest.raises(HTTPException) as error:authorize(str(uuid4()),method,f'/phase0/personas/{p.id}/{suffix}',{})
        assert error.value.status_code==404
    response=client.get(path)
    assert response.status_code==200 and response.json()['can_retry']
    assert set(response.json())=={'initial_state','mind_state','can_retry','partial',
        'quarantined_rule_count','unrepresented_note_count','contract'}
    assert not jobs and not calls
    action=authorize(OWNER,'POST',f'/phase0/personas/{p.id}/prepare',{'policy':'forged'})
    assert action.body=={}
    assert client.post(action.path,json=action.body).status_code==200
    assert len(jobs)==1 and not calls



@pytest.mark.parametrize('stage',['initial','mind'])
def test_corrupt_ready_result_can_really_be_retried(prepared,stage):
    p,jobs,calls,_=prepared
    mp.prepare(p.id)
    cur=storage.personas.get(p.id)
    if stage=='initial':cur.prepared_initial={}
    else:cur.prepared_mind['policy']={'invalid':'must not be executed'}
    storage.personas.save(p.id,cur)
    assert mp.status(cur)['can_retry']
    pp.enqueue(p.id,retry=True)
    assert len(jobs)==1
    if stage=='initial':
        assert len(jobs[0])==2
        assert storage.personas.get(p.id).initial_preparation_status['state']=='queued'
    else:
        assert jobs[0][2]=='mind'
        mp.run_queued(*jobs[0][:2])
        assert mp.ready(storage.personas.get(p.id))[1]=='ready'
