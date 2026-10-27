import assert from 'node:assert/strict';
import test from 'node:test';
import { bracketAddress, resolvedTitle } from '../src/utils/alertTitle.ts';

test('the whole address sits inside one pair of brackets', () => {
  assert.equal(bracketAddress('[서울특별시 마포구] 월드컵로'), '[서울특별시 마포구 월드컵로]');
});

test('closed-case title matches the list card with or without age', () => {
  assert.equal(resolvedTitle('[서울특별시 성북구] 정릉동', 82), '[서울특별시 성북구 정릉동] 82세 어르신');
  assert.equal(resolvedTitle('정릉동', undefined), '[정릉동] 어르신');
});
