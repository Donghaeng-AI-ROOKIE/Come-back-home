import assert from 'node:assert/strict';
import test from 'node:test';
import { placeNotice } from '../src/utils/placeNotice.ts';

test('a road-level match asks the guardian to check the map and search a building or station', () => {
  // 10/27 운영: "경기 고양시 일산서구 킨텍스로 217-60" → 도로 중심(실제 위치에서 약 2.5km).
  const text = placeNotice('road');
  assert.match(text, /도로 단위로만 찾았습니다/);
  assert.match(text, /지도의 위치가 맞는지 확인해 주세요/);
  assert.match(text, /건물이나 역 이름으로 다시 검색/);
});

test('an area-level match says so in the same way', () => {
  assert.match(placeNotice('area'), /동네 단위로만 찾았습니다/);
});

test('a point match, an old server without the field, or an unknown value shows nothing', () => {
  for (const g of ['point', undefined, null, '', 'something-new']) assert.equal(placeNotice(g), null);
});
