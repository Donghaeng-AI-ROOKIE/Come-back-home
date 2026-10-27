import assert from 'node:assert/strict';
import test from 'node:test';
import { QueryClient, QueryObserver } from '@tanstack/query-core';
import { refreshAfterCaseChange } from '../src/utils/caseRefresh.ts';

// 보호자 알림 탭과 같은 조건: 사건 목록은 15초마다 다시 묻는 조회가 화면에 붙어 있다
// (hooks/queries.ts 의 useGuardianCases, ALERT_POLL_MS).
const POLL_MS = 15_000;

function setup() {
  // gcTime 을 무한으로 둬 시험 프로세스에 정리 타이머가 남지 않게 한다.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  const server = { status: 'predicted', calls: 0, personaCalls: 0, delayMs: 0 };
  const cases = new QueryObserver(qc, {
    queryKey: ['guardianCases', 'owner', []],
    queryFn: async () => {
      server.calls += 1;
      if (server.delayMs) await new Promise((r) => setTimeout(r, server.delayMs));
      return [{ id: 'c1', status: server.status }];
    },
    refetchInterval: POLL_MS,
  });
  const personas = new QueryObserver(qc, {
    queryKey: ['personas', 'owner'],
    queryFn: async () => { server.personaCalls += 1; return [{ id: 'p1' }]; },
  });
  const seen = [];
  const stop = [cases.subscribe((r) => seen.push(r.data)), personas.subscribe(() => {})];
  return { qc, server, cases, personas, seen, stop: () => { stop.forEach((s) => s()); qc.clear(); } };
}

async function settle(observer) {
  for (let i = 0; i < 50 && observer.getCurrentResult().fetchStatus !== 'idle'; i++) await new Promise((r) => setTimeout(r, 5));
  await new Promise((r) => setTimeout(r, 5));
}

test('after closing, the case list is fetched again right away instead of at the next 15 s poll', async () => {
  const t = setup();
  try {
    await settle(t.cases);
    assert.equal(t.cases.getCurrentResult().data[0].status, 'predicted');
    const before = t.server.calls;

    t.server.status = 'closed';            // 서버에서 종결 작업이 끝났다
    const started = Date.now();
    await refreshAfterCaseChange(t.qc);
    await settle(t.cases);

    assert.equal(t.server.calls, before + 1, '종결 직후 사건 목록을 한 번 다시 받아야 한다');
    assert.equal(t.cases.getCurrentResult().data[0].status, 'closed', '화면에 붙은 조회가 종결 상태를 받아야 한다');
    assert.ok(Date.now() - started < POLL_MS / 10, '다음 주기 조회를 기다리지 않아야 한다');
  } finally {
    t.stop();
  }
});

test('cached data of screens that are not showing is dropped, so ended-case data does not linger', async () => {
  const t = setup();
  try {
    await settle(t.cases);
    // 화면에 붙지 않은 조회: 종결 사건의 지도, 시민 경보 목록.
    t.qc.setQueryData(['poa', 'c1', 0], { cells: ['8a30c1'] });
    t.qc.setQueryData(['activeAlerts', '8730c1'], [{ caseId: 'c1' }]);
    await refreshAfterCaseChange(t.qc);
    assert.equal(t.qc.getQueryData(['poa', 'c1', 0]), undefined);
    assert.equal(t.qc.getQueryData(['activeAlerts', '8730c1']), undefined);
  } finally {
    t.stop();
  }
});

test('screens unrelated to the case keep their data and are not asked again', async () => {
  const t = setup();
  try {
    await settle(t.cases);
    await settle(t.personas);
    const before = t.server.personaCalls;
    await refreshAfterCaseChange(t.qc);
    await settle(t.personas);
    assert.equal(t.server.personaCalls, before);
    assert.deepEqual(t.qc.getQueryData(['personas', 'owner']), [{ id: 'p1' }]);
  } finally {
    t.stop();
  }
});

test('when deleting changes the list key, the old list holding the deleted case is not left behind', async () => {
  const t = setup();
  try {
    await settle(t.cases);
    t.server.status = 'closed';
    t.server.delayMs = 20;   // 새 목록 응답이 오는 동안 화면이 다시 그려진다
    const refreshing = refreshAfterCaseChange(t.qc);
    await new Promise((r) => setTimeout(r, 5));
    assert.equal(t.cases.getCurrentResult().fetchStatus, 'fetching', '키가 바뀌는 시점은 재조회 도중이어야 한다');
    // 삭제는 기기의 사건 ID 목록을 바꾸므로 화면이 새 키로 옮겨 간다(useGuardianCases).
    t.cases.setOptions({
      queryKey: ['guardianCases', 'owner', ['other']],
      queryFn: async () => { t.server.calls += 1; return []; },
      refetchInterval: POLL_MS,
    });
    await refreshing;
    assert.equal(t.qc.getQueryData(['guardianCases', 'owner', []]), undefined, '지운 사건이 든 옛 목록이 캐시에 남으면 안 된다');
  } finally {
    t.stop();
  }
});
