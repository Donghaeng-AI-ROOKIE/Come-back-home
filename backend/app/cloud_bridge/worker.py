"""One private GPU process, outgoing HTTPS only; no listening socket or SSH relay.

Run only on a fresh cloud-demo data volume. All app storage and background
preparation threads share this process. No fork/multiple uvicorn workers.
"""
import asyncio
import contextlib
import json
import logging
import os
import threading
import time
import uuid
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from app.cloud_bridge.policy import authorize
from app.llm.usage_ledger import append_event, warm_started_index

log = logging.getLogger(__name__)

# Work that an endpoint deliberately left running after its response (FastAPI
# BackgroundTasks: tip layer-2 re-prediction, post-prediction alerts). The
# compute lane stops claiming new jobs while this many are still running so
# heavy recomputations cannot pile up without bound.
MAX_CONTINUATIONS = 2


class EarlyResponseTransport(httpx.AsyncBaseTransport):
    """In-process ASGI call that returns as soon as the response body is complete.

    httpx.ASGITransport awaits the whole app call, which includes background
    tasks. Under uvicorn those run after the client already has its answer; here
    they held the tip job and the single compute consumer for the full layer-2
    re-prediction (about 2.5 min on 2026-10-12, other users' maps queued behind).
    """

    def __init__(self, app):
        self.app = app
        self.pending: set[asyncio.Task] = set()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        scope = {
            'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
            'method': request.method,
            'headers': [(k.lower(), v) for (k, v) in request.headers.raw],
            'scheme': request.url.scheme, 'path': request.url.path,
            'raw_path': request.url.raw_path.split(b'?')[0],
            'query_string': request.url.query,
            'server': (request.url.host, request.url.port),
            'client': ('127.0.0.1', 123), 'root_path': '',
        }
        status, headers, parts = None, [], []
        complete = asyncio.Event()
        sent = False

        async def receive():
            nonlocal sent
            if sent:
                await complete.wait()
                return {'type': 'http.disconnect'}
            sent = True
            return {'type': 'http.request', 'body': body, 'more_body': False}

        async def send(message):
            nonlocal status, headers
            if message['type'] == 'http.response.start':
                status, headers = message['status'], message.get('headers', [])
            elif message['type'] == 'http.response.body':
                if message.get('body'):
                    parts.append(message['body'])
                if not message.get('more_body', False):
                    complete.set()

        app_task = asyncio.create_task(self.app(scope, receive, send))
        waiter = asyncio.create_task(complete.wait())
        try:
            await asyncio.wait({app_task, waiter}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            waiter.cancel()
        if not complete.is_set():
            app_task.result()  # an exception before the response propagates as before
            raise RuntimeError('ASGI app finished without a complete response')
        if app_task.done():
            # Starlette sends its 500 and then re-raises; keep the old propagation.
            app_task.result()
        else:
            self.pending.add(app_task)
            app_task.add_done_callback(self._continuation_done)
        return httpx.Response(status, headers=headers, content=b''.join(parts), request=request)

    def _continuation_done(self, task: asyncio.Task):
        self.pending.discard(task)
        if not task.cancelled() and task.exception() is not None:
            # The client already has its answer; the endpoint's own data stays saved.
            log.error('Work after response failed: %s', type(task.exception()).__name__)


class Cloud:
    def __init__(self, url: str, key: str):
        parts = urlsplit(url)
        if parts.scheme != 'https' or not parts.hostname or not parts.hostname.endswith('.supabase.co') or parts.path not in ('', '/'):
            raise ValueError('Use the project HTTPS Supabase URL')
        if not key:
            raise ValueError('Worker service-role secret missing')
        self.ledger = os.environ.get('RESEARCH_USAGE_LEDGER_PATH')
        if not self.ledger:
            raise ValueError('Persistent usage ledger path required')
        self.client = httpx.AsyncClient(base_url=url.rstrip('/')+'/rest/v1/',
            headers={'apikey': key, 'Authorization': 'Bearer '+key}, timeout=15)

    async def rpc(self, name, **params):
        common = {'attempt_id': str(uuid.uuid4()), 'provider': 'Supabase',
                  'role': name, 'run_id': 'cloud_worker_transport',
                  'actual_cost': None, 'support_round': None}
        append_event({**common, 'event_type': 'transport_attempt_started'}, self.ledger)
        started = time.monotonic()
        status, error = None, None
        try:
            res = await self.client.post('rpc/'+name, json=params)
            status = res.status_code
            # Response bodies may contain guardian data. Never log body, key or URL query.
            if res.is_error:
                raise RuntimeError('Supabase RPC HTTP '+str(status))
            return res.json() if res.content else None
        except Exception as exc:
            error = type(exc).__name__
            raise
        finally:
            append_event({**common, 'event_type': 'transport_attempt_finished',
                          'http_status': status, 'error_type': error,
                          'duration_ms': round((time.monotonic()-started)*1000, 2)}, self.ledger)


async def dispatch(api: httpx.AsyncClient, job: dict, *, enabled: bool):
    if not enabled:
        return 503, {'detail': 'AI 서버 연결을 준비 중입니다. 잠시 후 다시 확인해 주세요.'}
    try:
        path, method = job['path'], job['method']
        request = authorize(job['owner_id'], method, path, job.get('body'))
        res = await api.request(request.method, request.path, json=request.body)
        if len(res.content)>2_000_000:
            return 502, {'detail': '응답이 너무 큽니다. 범위를 줄여 다시 조회해 주세요.'}
        return res.status_code, res.json() if res.content else None
    except HTTPException as exc:
        return exc.status_code, {'detail': exc.detail}
    except Exception as exc:
        log.error('API execution failed: %s', type(exc).__name__)
        return 500, {'detail': '처리 중 오류가 발생했습니다. 기록을 확인한 뒤 다시 시도해 주세요.'}


async def execute(cloud, api, job, *, enabled):
    """Keep lease alive, invoke once, retry only publishing the already saved result."""
    lost = asyncio.Event()
    async def heartbeat():
        while True:
            await asyncio.sleep(20)
            try:
                ok = await cloud.rpc('cbh_heartbeat', p_id=job['id'], p_lease=job['lease_id'])
                if not ok:
                    lost.set()
                    return
            except Exception:
                # The DB marks an expired lease interrupted. It never requeues it.
                log.warning('Heartbeat unavailable; job may become interrupted')
    task = asyncio.create_task(heartbeat())
    try:
        status, result = await dispatch(api, job, enabled=enabled)
        if lost.is_set():
            return
        for attempt in range(3):
            try:
                await cloud.rpc('cbh_complete', p_id=job['id'], p_lease=job['lease_id'],
                                p_status=status, p_result=result)
                return
            except Exception:
                if attempt<2:
                    await asyncio.sleep(2)
        log.error('Completion could not be published; API will NOT be rerun')
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def consume(cloud, api, lane, enabled, continuations=None):
    while True:
        try:
            # Read jobs never wait: they are cheap and keep lists/alerts responsive.
            while lane == 'compute' and continuations is not None and len(continuations) >= MAX_CONTINUATIONS:
                await asyncio.sleep(1)
            job = await cloud.rpc('cbh_claim', p_lane=lane)
            if job:
                await execute(cloud, api, job, enabled=enabled)
            else:
                await asyncio.sleep(1)
        except Exception as exc:
            log.warning('Queue temporarily unavailable: %s', type(exc).__name__)
            await asyncio.sleep(5)


def warm_ledger_index(path):
    try:
        warm_started_index(path)
    except (OSError, ValueError) as exc:
        # Capped model calls count again themselves and still fail closed.
        log.warning('Usage ledger pre-count failed: %s', type(exc).__name__)


async def main():
    from app.main import app
    enabled = os.environ.get('CBH_API_ENABLED', 'false').lower() == 'true'
    # API lifespan can start paid preparation/recovery. Do not start it before
    # credentials, model routing and usage logging have been verified.
    lifecycle = app.router.lifespan_context(app) if enabled else contextlib.nullcontext()
    cloud = Cloud(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
    # Count existing history off the lock now, not inside the first SAR call.
    threading.Thread(target=warm_ledger_index, args=(cloud.ledger,),
                     name='ledger-index', daemon=True).start()
    try:
        async with lifecycle:
            transport = EarlyResponseTransport(app)
            async with httpx.AsyncClient(transport=transport,
                    base_url='http://private-engine', timeout=None) as api:
                await asyncio.gather(consume(cloud, api, 'read', enabled),
                                     consume(cloud, api, 'compute', enabled, transport.pending))
    finally:
        await cloud.client.aclose()


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
