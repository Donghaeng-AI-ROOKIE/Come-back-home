import assert from 'node:assert/strict';
import test from 'node:test';
import { formatTipTime, listedCases, mapCaseOf, splitCases, tipTimeMs } from '../src/utils/guardianTips.ts';

// 보호자 기기는 한국 시간이다. 서버 컨테이너는 UTC 라 시각이 오프셋 없이 온다.
process.env.TZ = 'Asia/Seoul';

const KINTEX = { lat: 37.6652142, lng: 126.7483258 };

test('seen time from the server is UTC, so an 11:38 sighting reads 11:38 in Korea', () => {
  // 10/27 운영: "10분 전" 제보의 seen_at 은 서버 now(UTC) - 10분으로 저장됐고,
  // 보호자 화면에 02:38 로 보였다.
  const tip = { seen_at: '2026-10-27T02:38:00', created_at: '2026-10-27T02:48:10.123456' };
  assert.equal(tipTimeMs(tip), Date.UTC(2026, 9, 27, 2, 38));
  assert.equal(formatTipTime(tip), '2026/10/27 11:38');
});

test('without a seen time the receipt time is used under the same rule', () => {
  const tip = { seen_at: null, created_at: '2026-10-27T02:48:10.123456' };
  assert.equal(formatTipTime(tip), '2026/10/27 11:48');
});

test('a time that already carries an offset is not shifted again', () => {
  assert.equal(tipTimeMs({ seen_at: '2026-10-27T11:38:00+09:00', created_at: '2026-10-27T02:48:10' }), Date.UTC(2026, 9, 27, 2, 38));
  assert.equal(tipTimeMs({ seen_at: '2026-10-27T02:38:00Z', created_at: '2026-10-27T02:48:10' }), Date.UTC(2026, 9, 27, 2, 38));
});

test('an unreadable seen time falls back to the receipt time', () => {
  assert.equal(formatTipTime({ seen_at: 'not a time', created_at: '2026-10-27T02:48:10' }), '2026/10/27 11:48');
});

test('only the open case on the map lists its tips; closed cases do not mix in', () => {
  const open = { id: 'open', status: 'predicted', lkp: KINTEX, tips: [{ id: 't1', text: '킨텍스역 앞에서 봤어요' }] };
  const closed = { id: 'closed', status: 'closed', lkp: KINTEX, tips: [{ id: 't0', text: '[테스트] 배포 확인용 합성 제보' }] };
  const found = { id: 'found', status: 'found', lkp: KINTEX, tips: [{ id: 't2', text: '이미 찾은 사건의 제보' }] };
  // 서버 목록은 최신순이다. 종결 사건이 더 최근이어도 지도와 목록은 진행 중 사건을 본다.
  const cases = [closed, open, found];
  assert.equal(mapCaseOf(cases), open);
  assert.deepEqual(listedCases(cases).map((c) => c.id), ['open']);
});

test('with no open case nothing is listed', () => {
  const closed = { id: 'closed', status: 'closed', lkp: KINTEX, tips: [{ id: 't0', text: '[테스트] 배포 확인용 합성 제보' }] };
  assert.equal(mapCaseOf([closed]), null);
  assert.deepEqual(listedCases([closed]), []);
});

test('case management splits ongoing and closed cases, keeping the server order', () => {
  const cases = [
    { id: 'a', status: 'searching' },
    { id: 'b', status: 'found' },
    { id: 'c', status: 'intake' },
    { id: 'd', status: 'closed' },
    { id: 'e', status: 'predicted' },
  ];
  const { active, closed } = splitCases(cases);
  assert.deepEqual(active.map((c) => c.id), ['a', 'c', 'e']);
  assert.deepEqual(closed.map((c) => c.id), ['b', 'd']);
  assert.deepEqual(splitCases([]), { active: [], closed: [] });
});
