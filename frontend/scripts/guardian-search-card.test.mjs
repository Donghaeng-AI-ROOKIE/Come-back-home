import assert from 'node:assert/strict';
import test from 'node:test';
import { activeCases, formatElapsed, guardianSearchCard, newTipCount } from '../src/utils/guardianSearchCard.ts';

// 보호자 기기는 한국 시간이다. 서버 컨테이너는 UTC 라 시각이 오프셋 없이 온다.
process.env.TZ = 'Asia/Seoul';

// 10/27 13:20 KST(= 04:20 UTC)에 보는 화면.
const NOW = Date.UTC(2026, 9, 27, 4, 20);

const searching = (id, createdAt, extra = {}) => ({ id, status: 'searching', created_at: createdAt, tips: [], ...extra });

test('elapsed time reads the server time as UTC, not as device local time', () => {
  // 11:59:30 KST 신고 → 서버에는 "02:59:30.123456"(오프셋 없음)으로 찍힌다. 로컬로 읽으면
  // 02:59 KST 가 되어 경과가 10시간 20분으로 9시간 부풀려진다.
  assert.equal(formatElapsed('2026-10-27T02:59:30.123456', NOW), '1시간 20분');
  assert.equal(formatElapsed('2026-10-27T12:00:00+09:00', NOW), '1시간 20분');
});

test('under an hour shows minutes only, and a device clock behind the server never goes negative', () => {
  assert.equal(formatElapsed('2026-10-27T04:08:30', NOW), '11분');
  assert.equal(formatElapsed('2026-10-27T04:25:00', NOW), '0분');
  assert.equal(formatElapsed('2026-10-26T02:20:00', NOW), '26시간 0분');
});

test('only intake, predicted and searching count as an ongoing search, newest report first', () => {
  const list = activeCases([
    searching('old', '2026-10-27T01:00:00'),
    { ...searching('done', '2026-10-27T04:00:00'), status: 'found' },
    { ...searching('closed', '2026-10-27T04:10:00'), status: 'closed' },
    { ...searching('new', '2026-10-27T03:00:00'), status: 'intake' },
    { ...searching('mid', '2026-10-27T02:00:00'), status: 'predicted' },
  ]);
  assert.deepEqual(list.map((c) => c.id), ['new', 'mid', 'old']);
});

test('new tips are the ones this device has not shown in the alerts tab, compared by id', () => {
  const tips = [{ id: 't1' }, { id: 't2' }, { id: 't3' }];
  assert.equal(newTipCount(tips, undefined), 3);
  assert.equal(newTipCount(tips, ['t1', 't2']), 1);
  // 접수 대기 제보(t0)가 취소돼 빠져도 그다음 제보(t3)는 새 제보로 센다 — 개수 비교였다면 0.
  assert.equal(newTipCount(tips, ['t0', 't1', 't2']), 1);
  assert.equal(newTipCount(null, ['t1']), 0);
});

test('no ongoing case means no card', () => {
  assert.equal(guardianSearchCard([], [], {}, NOW), null);
  assert.equal(guardianSearchCard([{ ...searching('c1', '2026-10-27T03:00:00'), status: 'found' }], [], {}, NOW), null);
});

test('the card names the registered family member and counts unseen tips', () => {
  const c = searching('c1', '2026-10-27T03:00:00', {
    report: { persona_id: 'p1' },
    area_label: '[고양시 일산서구] 킨텍스로',
    tips: [{ id: 't1' }, { id: 't2' }],
  });
  assert.deepEqual(guardianSearchCard([c], [{ id: 'p1', name: '김영희' }], { c1: ['t1'] }, NOW), {
    caseId: 'c1',
    badge: '수색 중',
    title: '김영희 님 수색 중 · 경과 1시간 20분',
    body: '새 제보 1건 · 지도는 15초마다 갱신돼요',
  });
});

test('without a registered name the card falls back to the area, then to "가족"', () => {
  const quick = searching('c1', '2026-10-27T03:00:00', { report: { persona_id: null }, area_label: '[고양시 일산서구] 킨텍스로' });
  assert.equal(guardianSearchCard([quick], [], {}, NOW).title, '[고양시 일산서구 킨텍스로] 수색 중 · 경과 1시간 20분');
  const blank = searching('c1', '2026-10-27T03:00:00', { report: { persona_id: 'gone' }, area_label: '[] ' });
  assert.equal(guardianSearchCard([blank], [{ id: 'p1', name: '김영희' }], {}, NOW).title, '가족 수색 중 · 경과 1시간 20분');
});

test('two ongoing cases show the newest one and say how many others there are', () => {
  const card = guardianSearchCard([
    searching('older', '2026-10-27T01:00:00', { tips: [{ id: 'a' }] }),
    searching('newer', '2026-10-27T04:00:00'),
    searching('oldest', '2026-10-26T23:00:00'),
  ], [], {}, NOW);
  assert.equal(card.caseId, 'newer');
  assert.equal(card.badge, '수색 중 · 외 2건');
  assert.equal(card.title, '가족 수색 중 · 경과 20분');
  assert.equal(card.body, '새 제보 0건 · 지도는 15초마다 갱신돼요');
});
