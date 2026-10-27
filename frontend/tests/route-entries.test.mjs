// 스택에 등록된 화면마다 들어올 길이 있는가 — 들어올 길이 없는 화면은 고쳐도 아무도 못 본다.
//
// 10/27: 수색 지도(Search)는 스택에 등록돼 있었지만 `navigate('Search')` 호출이 0건이었다.
// 시민 지도는 AlertSync 가 맡고 있어, Search 는 고쳐도 보이지 않는 화면으로 남아 있었다.
// 반대로 types.ts 에만 있고 스택에 없는 화면은 이동하는 순간 조용히 무시된다(08-11 Search 의 처음 상태).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = path.join(import.meta.dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');

function sourceFiles(dir) {
  return fs.readdirSync(path.join(root, dir), { withFileTypes: true }).flatMap((e) => {
    const rel = path.join(dir, e.name);
    if (e.isDirectory()) return sourceFiles(rel);
    return /\.(ts|tsx)$/.test(e.name) ? [rel] : [];
  });
}

const navigator = read('src/navigation/RootNavigator.tsx');
const registered = [...navigator.matchAll(/<Stack\.Screen\s+name="(\w+)"/g)].map((m) => m[1]);

/** 역할별 루트 — 로그인·역할이 곧 진입 경로다. */
const ROLE_ROOTS = new Set(['Auth', 'GuardianTabs', 'CitizenTabs']);

function entryNames() {
  const names = new Set();
  const code = [...sourceFiles('src'), 'App.tsx'].map(read).join('\n');
  for (const m of code.matchAll(/\b(?:navigate|replace|popTo|push|navigateWhenReady)\(\s*'(\w+)'/g)) names.add(m[1]);
  for (const m of code.matchAll(/\bname:\s*'(\w+)'/g)) names.add(m[1]);
  for (const m of code.matchAll(/initialRouteName=\{[^}]*'(\w+)'/g)) names.add(m[1]);
  // 딥링크(dora://…) 설정의 화면 이름.
  const linking = read('App.tsx').match(/screens:\s*\{([\s\S]*?)\}/);
  for (const m of (linking?.[1] ?? '').matchAll(/(\w+):\s*'/g)) names.add(m[1]);
  return names;
}

test('the stack and the param list name the same screens', () => {
  const types = read('src/navigation/types.ts');
  const block = types.match(/export type RootStackParamList = \{([\s\S]*?)\n\};/)[1];
  const declared = [...block.matchAll(/^\s{2}(\w+):/gm)].map((m) => m[1]);
  assert.deepEqual([...new Set(registered)].sort(), [...new Set(declared)].sort());
});

test('every registered screen has a way in', () => {
  const entries = entryNames();
  const orphans = registered.filter((name) => !ROLE_ROOTS.has(name) && !entries.has(name));
  assert.deepEqual(orphans, [], `screens nobody navigates to: ${orphans.join(', ')}`);
});
