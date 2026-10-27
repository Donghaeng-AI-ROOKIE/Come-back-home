import assert from 'node:assert/strict';
import test from 'node:test';
import { resolvedMessage, resolvedThanks } from '../src/utils/resolvedCopy.ts';

test('closed-case copy credits the tips by count, not by people', () => {
  assert.equal(resolvedMessage(3), '여러분의 제보 3건 덕분에 가족의 품으로 무사히 돌아갔습니다.');
  assert.equal(resolvedThanks(3), '제보해 주셔서 감사합니다.');
});

test('a case closed without tips thanks attention instead of showing zero', () => {
  for (const none of [0, null, undefined]) {
    assert.equal(resolvedMessage(none), '여러분의 관심 덕분에 가족의 품으로 무사히 돌아갔습니다.');
    assert.equal(resolvedThanks(none), '함께 지켜봐 주셔서 감사합니다.');
  }
});
