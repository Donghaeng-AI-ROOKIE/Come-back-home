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

test('a blank area never renders empty brackets', () => {
  // 10/27 운영: 워커 재시작 뒤 지역명이 빈 값으로 와 카드 제목이 "[] 어르신"이었다.
  for (const blank of ['', '   ', '[]', '[ ] ', null, undefined]) {
    assert.equal(resolvedTitle(blank, null), '내 주변 어르신');
    assert.equal(resolvedTitle(blank, 81), '내 주변 81세 어르신');
  }
});
