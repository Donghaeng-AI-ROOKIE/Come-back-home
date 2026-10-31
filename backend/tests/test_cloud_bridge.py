import asyncio
from types import SimpleNamespace
from uuid import uuid4
import httpx
import pytest
from fastapi import FastAPI, HTTPException
from app import storage
from app.cloud_bridge.policy import authorize
from app.cloud_bridge.worker import dispatch, execute

OWNER = str(uuid4())
OTHER = str(uuid4())


def test_ids_are_taken_from_authenticated_job_not_body_or_query():
    r = authorize(OWNER, 'POST', '/walk/sessions', {'user_id':OTHER})
    assert r.body['user_id']==OWNER
    r = authorize(OWNER, 'GET', '/phase0/personas?guardian_id='+OTHER, None)
    assert r.path.endswith('guardian_id='+OWNER)
    r = authorize(OWNER, 'POST', '/phase1/reports', {'guardian_id':OTHER})
    assert r.body['guardian_id']==OWNER


@pytest.mark.parametrize('path', [
    '/auth/login', '/privacy/audit', '/debug/state', '/docs',
    'https://other/phase0/personas', '//other/phase0/personas',
    '/phase0/../privacy/audit', '/phase0/%2e%2e/privacy/audit',
    '/phase0/personas?guardian_id=x&guardian_id=y',
])
def test_unlisted_or_ambiguous_routes_are_denied(path):
    with pytest.raises(HTTPException):
        authorize(OWNER, 'GET', path, None)


@pytest.mark.parametrize('repo,path,field', [
    ('personas','/phase0/personas/private','guardian_id'),
    ('interviews','/phase0/interviews/private','guardian_id'),
    ('cases','/phase1/cases/private','guardian_id'),
    ('walk_sessions','/walk/sessions/private/end','user_id'),
])
def test_cross_account_objects_are_denied(monkeypatch,repo,path,field):
    monkeypatch.setattr(getattr(storage,repo),'get', lambda _: SimpleNamespace(**{field:OTHER}))
    with pytest.raises(HTTPException) as exc:
        authorize(OWNER,'POST' if field=='user_id' else 'GET',path,None)
    assert exc.value.status_code==404


def test_case_link_checks_both_owners(monkeypatch):
    monkeypatch.setattr(storage.cases,'get',lambda _:SimpleNamespace(guardian_id=OWNER))
    monkeypatch.setattr(storage.personas,'get',lambda _:SimpleNamespace(guardian_id=OTHER))
    with pytest.raises(HTTPException):
        authorize(OWNER,'PATCH','/phase1/cases/case/persona',{'persona_id':'other'})


def test_citizen_cannot_read_whole_case_but_can_report_tip(monkeypatch):
    monkeypatch.setattr(storage.cases,'get',lambda _:SimpleNamespace(guardian_id=OTHER))
    with pytest.raises(HTTPException):
        authorize(OWNER,'GET','/phase1/cases/case',None)
    r=authorize(OWNER,'POST','/phase3/cases/case/tips',{'reporter_user_id':OTHER,'text':'synthetic'})
    assert r.body['reporter_user_id']==OWNER
    with pytest.raises(HTTPException):
        authorize(OWNER,'GET','/phase3/cases/case/poa?elapsed_hours=6',None)


def test_disabled_worker_never_invokes_api():
    class NoAPI:
        async def request(self,*a,**k): raise AssertionError('API called')
    assert asyncio.run(dispatch(NoAPI(),{},enabled=False))[0]==503


def test_lost_completion_ack_does_not_repeat_mutation(monkeypatch):
    import app.cloud_bridge.worker as w
    calls=[]
    async def run(*a,**kw):
        calls.append('api')
        return 200,{'ok':True}
    monkeypatch.setattr(w,'dispatch',run)
    class Cloud:
        count=0
        async def rpc(self,name,**p):
            assert name=='cbh_complete'
            self.count+=1
            if self.count==1: raise OSError('lost acknowledgement')
            return True
    cloud=Cloud()
    asyncio.run(execute(cloud,None,{'id':'x','lease_id':'lease'},enabled=True))
    assert calls==['api'] and cloud.count==2


def test_dispatch_preserves_http_errors_and_uses_asgi_without_network():
    app=FastAPI()
    @app.get('/walk/stats')
    def stats(user_id:str): return {'user_id':user_id}
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test') as api:
            return await dispatch(api,dict(owner_id=OWNER,method='GET',path='/walk/stats?user_id='+OTHER),enabled=True)
    status,result=asyncio.run(run())
    assert status==200 and result['user_id']==OWNER


# ── 부스 시연 경로(/phase0/demo/*): DEMO_GUARDIAN_IDS 에 적힌 계정만, 소유자 강제 ──
def test_demo_paths_are_denied_unless_owner_is_a_listed_booth_account(monkeypatch):
    monkeypatch.delenv('DEMO_GUARDIAN_IDS', raising=False)
    for method, path in (('GET', '/phase0/demo/onboarding/template'), ('POST', '/phase0/demo/onboarding/template'),
                         ('POST', '/phase0/demo/onboarding/template/prepared'),
                         ('POST', '/phase0/demo/onboarding/sessions'), ('POST', '/phase0/demo/onboarding/reset')):
        with pytest.raises(HTTPException) as exc:
            authorize(OWNER, method, path, {} if method == 'POST' else None)
        assert exc.value.status_code == 403
    monkeypatch.setenv('DEMO_GUARDIAN_IDS', OTHER)
    with pytest.raises(HTTPException) as exc:
        authorize(OWNER, 'POST', '/phase0/demo/onboarding/sessions', {})
    assert exc.value.status_code == 403


def test_demo_paths_force_owner_and_check_session_ownership(monkeypatch):
    monkeypatch.setenv('DEMO_GUARDIAN_IDS', f' {OWNER} ,{OTHER}')
    r = authorize(OWNER, 'POST', '/phase0/demo/onboarding/sessions', {'guardian_id': OTHER, 'guardian_name': 'x' * 100})
    assert r.body == {'guardian_id': OWNER, 'guardian_name': 'x' * 40}
    r = authorize(OWNER, 'POST', '/phase0/demo/onboarding/reset', {'guardian_id': OTHER})
    assert r.body == {'guardian_id': OWNER}
    r = authorize(OWNER, 'GET', '/phase0/demo/onboarding/template', None)
    assert r.path == f'/phase0/demo/onboarding/template?guardian_id={OWNER}' and r.body is None
    # 세션 id 를 주면 내 것이어야 한다
    monkeypatch.setattr(storage.interviews, 'get', lambda _: SimpleNamespace(guardian_id=OTHER))
    with pytest.raises(HTTPException) as exc:
        authorize(OWNER, 'POST', '/phase0/demo/onboarding/template', {'session_id': 'theirs'})
    assert exc.value.status_code == 404
    monkeypatch.setattr(storage.interviews, 'get', lambda _: SimpleNamespace(guardian_id=OWNER))
    r = authorize(OWNER, 'POST', '/phase0/demo/onboarding/template', {'session_id': 'mine', 'label': 'L', 'guardian_id': OTHER})
    assert r.body == {'guardian_id': OWNER, 'session_id': 'mine', 'label': 'L'}
    # 준비 결과 저장 — 가족 id 를 주면 내 가족이어야 하고, 소유자는 로그인 계정으로 강제한다
    r = authorize(OWNER, 'POST', '/phase0/demo/onboarding/template/prepared', {'guardian_id': OTHER})
    assert r.body == {'guardian_id': OWNER, 'persona_id': None}
    monkeypatch.setattr(storage.personas, 'get', lambda _: SimpleNamespace(guardian_id=OTHER))
    with pytest.raises(HTTPException) as exc:
        authorize(OWNER, 'POST', '/phase0/demo/onboarding/template/prepared', {'persona_id': 'theirs'})
    assert exc.value.status_code == 404
    monkeypatch.setattr(storage.personas, 'get', lambda _: SimpleNamespace(guardian_id=OWNER))
    r = authorize(OWNER, 'POST', '/phase0/demo/onboarding/template/prepared', {'persona_id': 'mine'})
    assert r.body == {'guardian_id': OWNER, 'persona_id': 'mine'}
    # 다른 /phase0/demo/ 경로는 없다
    with pytest.raises(HTTPException) as exc:
        authorize(OWNER, 'DELETE', '/phase0/demo/onboarding/template', None)
    assert exc.value.status_code == 403
