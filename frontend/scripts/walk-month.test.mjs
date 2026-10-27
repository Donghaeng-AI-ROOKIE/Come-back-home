import assert from 'node:assert/strict';
import test from 'node:test';
import { koreanMonth } from '../src/utils/walkFormat.ts';

test('the home month is the current month in Korea, not a fixed August', () => {
  // 10/27 캡처에서 "8월에는 총 …km"로 보였다.
  assert.equal(koreanMonth(Date.UTC(2026, 9, 27, 4, 0)), 10);
});

test('the month turns at midnight Korean time, whatever the device time zone', () => {
  // 11/1 00:30 KST = 10/31 15:30 UTC — 한국에서는 이미 11월이다.
  assert.equal(koreanMonth(Date.UTC(2026, 9, 31, 15, 30)), 11);
  // 10/31 23:59 KST = 10/31 14:59 UTC — 아직 10월.
  assert.equal(koreanMonth(Date.UTC(2026, 9, 31, 14, 59)), 10);
  // 해가 바뀌는 날: 1/1 00:10 KST = 12/31 15:10 UTC.
  assert.equal(koreanMonth(Date.UTC(2026, 11, 31, 15, 10)), 1);
});
