import assert from 'node:assert/strict';
import test from 'node:test';
import { GUIDANCE_FALLBACK, GUIDANCE_LOADING, guidanceLine } from '../src/utils/guidanceLine.ts';

test('the loading line is only for the first request in flight', () => {
  assert.equal(guidanceLine({ text: undefined, loading: true }), GUIDANCE_LOADING);
});

test('an empty or blank answer falls back to general guidance', () => {
  // 10/27 운영: 200 {guidance: "", pending: false}
  assert.equal(guidanceLine({ text: '', loading: false }), GUIDANCE_FALLBACK);
  assert.equal(guidanceLine({ text: '   ', loading: false }), GUIDANCE_FALLBACK);
});

test('a failed request (no data) falls back too', () => {
  assert.equal(guidanceLine({ text: undefined, loading: false }), GUIDANCE_FALLBACK);
  assert.equal(guidanceLine({ text: null, loading: false }), GUIDANCE_FALLBACK);
});

test('server text wins, including the template sent while it is being refined', () => {
  const text = '시간이 지나 이동 범위가 넓어졌어요.';
  assert.equal(guidanceLine({ text, loading: false }), text);
  assert.equal(guidanceLine({ text, loading: true }), text);
});

test('the fallback avoids the expressions the server guidance forbids', () => {
  // backend/app/phase3/storytelling.py _FORBIDDEN_CERTAINTY, _FORBIDDEN_CONDITION
  for (const word of ['에 있습니다', '에 있어요', '임이 확실', '분명히', '틀림없', '치매', '발달장애', '지적장애', '인지저하', '질환', '장애를']) {
    assert.ok(!GUIDANCE_FALLBACK.includes(word), word);
  }
});
