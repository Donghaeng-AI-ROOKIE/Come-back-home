import assert from 'node:assert/strict';
import test from 'node:test';
import { activeCases } from '../src/utils/guardianSearchCard.ts';
import { citizenTabAccent, guardianEmergency, guardianTabAccent } from '../src/utils/tabAccent.ts';

// 진행 중 판정은 홈 "수색 중" 카드와 같은 함수(activeCases)로 센다 — 화면도 그렇게 부른다.
const caseOf = (id, status) => ({ id, status, created_at: '2026-10-27T03:00:00', tips: [] });
const accentFor = (cases, inReportFlow = false) =>
  guardianTabAccent(guardianEmergency(inReportFlow, activeCases(cases).length));

test('a guardian with no case and outside the report flow keeps the guardian green', () => {
  assert.equal(accentFor([]), 'guardian');
});

test('the report flow (Report, ReportSent) is an emergency even before the case shows up in the list', () => {
  assert.equal(accentFor([], true), 'figmaRed');
});

test('any ongoing case (intake, predicted, searching) turns the guardian tabs red', () => {
  for (const status of ['intake', 'predicted', 'searching']) {
    assert.equal(accentFor([caseOf('c1', status)]), 'figmaRed', status);
  }
});

test('once every case is found, closed or withdrawn the tabs go back to green', () => {
  assert.equal(accentFor([caseOf('a', 'found'), caseOf('b', 'closed'), caseOf('c', 'withdrawn')]), 'guardian');
  // 하나라도 진행 중이면 아직 긴급이다.
  assert.equal(accentFor([caseOf('a', 'found'), caseOf('b', 'searching')]), 'figmaRed');
});

test('citizen tabs: only the emergency alert tab is red, the others keep the brand colour', () => {
  assert.equal(citizenTabAccent('alert'), 'figmaRed');
  for (const tab of ['home', 'register', 'profile', null]) assert.equal(citizenTabAccent(tab), 'brand', String(tab));
});
