import assert from 'node:assert/strict';
import { reportTimeIso } from '../src/utils/reportTime.ts';
const now = new Date('2026-09-25T12:00:00+09:00');
assert.equal(reportTimeIso('2026-09-25 10:00', now), '2026-09-25T01:00:00.000Z');
assert.equal(reportTimeIso('2026-09-25 13:00', now), null);
assert.equal(reportTimeIso('2026-02-31 10:00', now), null);
assert.equal(reportTimeIso('', now), null);
assert.equal(reportTimeIso('2026-09-25 24:00', now), null);
console.log('Report time: timezone, future, invalid calendar date, missing value and invalid hour passed');
