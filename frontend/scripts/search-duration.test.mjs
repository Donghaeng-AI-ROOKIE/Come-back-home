import assert from 'node:assert/strict';
import test from 'node:test';
import { formatSearchDuration } from '../src/utils/searchDuration.ts';

test('search time reads as hours and minutes', () => {
  assert.equal(formatSearchDuration(125), '2시간 5분');
  assert.equal(formatSearchDuration(60 * 26 + 3), '26시간 3분');
});

test('a zero part is left out instead of saying 0', () => {
  assert.equal(formatSearchDuration(45), '45분');
  assert.equal(formatSearchDuration(120), '2시간');
  assert.equal(formatSearchDuration(0), '1분 미만');
});

test('unknown or broken values stay unknown', () => {
  for (const unknown of [null, undefined, -5, Number.NaN, Number.POSITIVE_INFINITY]) {
    assert.equal(formatSearchDuration(unknown), null);
  }
});
