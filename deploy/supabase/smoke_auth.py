"""Disposable Auth/queue smoke test, run inside the private cloud worker.

Creates two synthetic users without sending email; removes only those users.
No model calls, real accounts, passwords, JWTs or service keys in output/logs.
The API gate must remain closed during this test.
"""
import asyncio
import json
import os
import secrets
import time
import uuid

import httpx
from app.llm.usage_ledger import append_event


async def main():
    assert os.environ.get('CBH_API_ENABLED', 'false').lower() == 'false'
    url = os.environ['SUPABASE_URL'].rstrip('/')
    key = os.environ['SUPABASE_SERVICE_ROLE_KEY']
    public_key = os.environ['CBH_SMOKE_PUBLIC_KEY']
    ledger = os.environ['RESEARCH_USAGE_LEDGER_PATH']
    run = 'cloud-auth-smoke:' + str(uuid.uuid4())
    users = []
    checks = {}
    calls = 0
    async with httpx.AsyncClient(base_url=url, timeout=20) as client:
        async def request(role, method, path, data=None, token=None, admin=False):
            nonlocal calls
            calls += 1
            assert calls <= 48
            common = dict(run_id=run, attempt_id=str(uuid.uuid4()), provider='Supabase',
                          role=role, actual_cost=None, support_round=None)
            append_event({**common, 'event_type': 'transport_attempt_started'}, ledger)
            started = time.monotonic()
            code, error = None, None
            try:
                headers = {'apikey': key if admin else public_key}
                if admin or token:
                    headers['Authorization'] = 'Bearer ' + (key if admin else token)
                res = await client.request(method, path, json=data, headers=headers)
                code = res.status_code
                return code, res.json() if res.content else None
            except Exception as exc:
                error = type(exc).__name__
                raise
            finally:
                append_event({**common, 'event_type': 'transport_attempt_finished',
                              'http_status': code, 'error_type': error,
                              'duration_ms': round((time.monotonic()-started)*1000, 2)}, ledger)
        try:
            tokens = []
            for _ in range(2):
                email = 'cbh-smoke-' + uuid.uuid4().hex + '@example.com'
                password = secrets.token_urlsafe(36)
                code, user = await request('test_user_create', 'POST', '/auth/v1/admin/users',
                    {'email': email, 'password': password, 'email_confirm': True,
                     'user_metadata': {'role': 'guardian', 'synthetic_deployment_test': run}}, admin=True)
                assert code == 200, ('test_user_create', code)
                users.append(user['id'])
                code, session = await request('password_login', 'POST', '/auth/v1/token?grant_type=password',
                                             {'email': email, 'password': password})
                assert code == 200, ('password_login', code)
                tokens.append(session['access_token'])
            checks['two_password_logins'] = True
            request_id = str(uuid.uuid4())
            body = {'p_id': request_id, 'p_method': 'GET', 'p_path': '/phase0/slots', 'p_body': None}
            code, _ = await request('anonymous_denied', 'POST', '/rest/v1/rpc/cbh_submit', body)
            checks['anonymous_denied'] = code in (401, 403)
            code, result = await request('submit', 'POST', '/rest/v1/rpc/cbh_submit', body, tokens[0])
            checks['authenticated_submit'] = code == 200 and result == request_id
            code, result = await request('duplicate_submit', 'POST', '/rest/v1/rpc/cbh_submit', body, tokens[0])
            checks['same_id_is_idempotent'] = code == 200 and result == request_id
            code, _ = await request('changed_body_denied', 'POST', '/rest/v1/rpc/cbh_submit',
                                    {**body, 'p_path': '/phase0/personas'}, tokens[0])
            checks['changed_body_denied'] = code == 400
            code, result = await request('other_owner_result', 'POST', '/rest/v1/rpc/cbh_result',
                                         {'p_id': request_id}, tokens[1])
            checks['other_user_cannot_read_result'] = code == 200 and result is None
            for _ in range(20):
                code, result = await request('own_result', 'POST', '/rest/v1/rpc/cbh_result',
                                             {'p_id': request_id}, tokens[0])
                if result and result.get('state') == 'done':
                    break
                await asyncio.sleep(1)
            checks['worker_roundtrip_gate_503'] = bool(code == 200 and result and
                result.get('state') == 'done' and result.get('status_code') == 503)
            code, _ = await request('user_cannot_claim', 'POST', '/rest/v1/rpc/cbh_claim',
                                    {'p_lane': 'read'}, tokens[0])
            checks['user_cannot_claim_jobs'] = code in (401, 403, 404)
        finally:
            cleaned = 0
            for user_id in users:
                code, _ = await request('test_user_delete', 'DELETE', '/auth/v1/admin/users/' + user_id,
                                        admin=True)
                cleaned += code == 200
            checks['synthetic_users_removed'] = cleaned == len(users)
            output = {'run_id': run, 'checks': checks, 'passed': all(checks.values()),
                      'requests': calls, 'model_calls': 0, 'actual_cost': None,
                      'email_signup_delivery_tested': False}
            print(json.dumps(output, ensure_ascii=False), flush=True)
    assert output['passed']


if __name__ == '__main__':
    asyncio.run(main())
