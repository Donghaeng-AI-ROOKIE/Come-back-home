import assert from 'node:assert/strict';
import { checkReportTime, reportTimeIso } from '../src/utils/reportTime.ts';

// 입력 시각은 기기(보호자 기기는 한국) 시간대로 해석하므로 UTC 컨테이너에서도 한국 시간으로 고정한다.
process.env.TZ = 'Asia/Seoul';

const now = new Date('2026-09-25T12:00:00+09:00');
assert.equal(reportTimeIso('2026-09-25 10:00', now), '2026-09-25T01:00:00.000Z');
assert.equal(reportTimeIso('2026-09-25 13:00', now), null);
assert.equal(reportTimeIso('2026-02-31 10:00', now), null);
assert.equal(reportTimeIso('', now), null);
assert.equal(reportTimeIso('2026-09-25 24:00', now), null);

// 10/29 팀 점검: 01:16 에 "2026-10-29 1:00"을 적었더니 형식 오류인데 미래 시각처럼 안내됐다.
const night = new Date('2026-10-29T01:16:00+09:00');
assert.equal(reportTimeIso('2026-10-29 1:00', night), '2026-10-28T16:00:00.000Z');
assert.equal(reportTimeIso('2026-10-29 01:00', night), '2026-10-28T16:00:00.000Z');
assert.equal(reportTimeIso('2026-9-5 7:05', now), '2026-09-04T22:05:00.000Z');
assert.equal(reportTimeIso('2026.10.29 1:00', night), '2026-10-28T16:00:00.000Z');
// 형식 오류와 미래 시각은 다른 안내가 나가도록 구분한다.
assert.deepEqual(checkReportTime('2026-10-29 1:20', night), { error: 'future' });
assert.deepEqual(checkReportTime('2026-10-29 1시', night), { error: 'format' });
assert.deepEqual(checkReportTime('2026-10-29', night), { error: 'format' });
assert.deepEqual(checkReportTime('2026-10-29 25:00', night), { error: 'format' });
console.log('Report time: timezone, future, invalid calendar date, missing value, invalid hour, one-digit fields and error kinds passed');
