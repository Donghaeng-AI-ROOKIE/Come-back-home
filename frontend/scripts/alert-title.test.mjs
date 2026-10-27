import assert from 'node:assert/strict';
import test from 'node:test';
import { activeAlertTitle, bracketAddress, nearbyAlertCard, resolvedTitle } from '../src/utils/alertTitle.ts';

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

test('active alert title is the list card title, with the old fallback for a blank area', () => {
  // 긴급 알림 목록 카드가 쓰던 식을 그대로 옮긴 것이다 — 홈 카드도 같은 제목을 쓴다.
  assert.equal(activeAlertTitle('[고양시 일산서구] 킨텍스로', 81), '[고양시 일산서구 킨텍스로] 81세 실종 어르신');
  assert.equal(activeAlertTitle('', undefined), '[최종 목격 위치 기준] 실종 어르신');
  assert.equal(activeAlertTitle(null, 0), '[최종 목격 위치 기준] 실종 어르신');
});

test('the home card picks the first alert the list would show, skipping dismissed cases', () => {
  const alerts = [
    { caseId: 'a', area: '[고양시 일산서구] 킨텍스로', age: 81 },
    { caseId: 'b', area: '[서울특별시 마포구] 월드컵로', age: 79 },
  ];
  assert.equal(nearbyAlertCard([], {}), null);
  assert.equal(nearbyAlertCard(undefined, {}), null);
  assert.equal(nearbyAlertCard(alerts, { a: 1, b: 2 }), null);
  assert.deepEqual(nearbyAlertCard(alerts, { a: 1 }), {
    badge: '내 주변 수색 중',
    title: '[서울특별시 마포구 월드컵로] 79세 실종 어르신',
    body: '봤다면 바로 제보해 주세요',
    caseId: 'b',
  });
});

test('two or more alerts say how many others there are and open the list instead of one alert', () => {
  const card = nearbyAlertCard([
    { caseId: 'a', area: '[고양시 일산서구] 킨텍스로', age: 81 },
    { caseId: 'b', area: '', age: null },
    { caseId: 'c', area: '정릉동' },
  ], {});
  assert.equal(card.badge, '내 주변 수색 중 · 외 2건');
  assert.equal(card.title, '[고양시 일산서구 킨텍스로] 81세 실종 어르신');
  assert.equal(card.caseId, null);
});
