import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { getStateFromPath } from '../node_modules/@react-navigation/core/lib/module/getStateFromPath.js';
import { getPathFromState } from '../node_modules/@react-navigation/core/lib/module/getPathFromState.js';

test('guardian nested route and Korean query survive URL round trip', () => {
  const path = '/GuardianTabs/GuardianHome?label=' + encodeURIComponent('돌아오길');
  const state = getStateFromPath(path);
  assert.equal(state.routes[0].name, 'GuardianTabs');
  assert.equal(state.routes[0].state.routes[0].name, 'GuardianHome');
  assert.equal(state.routes[0].state.routes[0].params.label, '돌아오길');
  assert.equal(getPathFromState(state), path);
});
test('login and map routes retain query values including encoded signs', () => {
  for (const route of ['Auth', 'GuardianMap']) {
    const state = getStateFromPath('/' + route + '?case_id=synthetic-1&note=a%2Bb+c');
    assert.equal(state.routes[0].name, route);
    assert.equal(state.routes[0].params.case_id, 'synthetic-1');
    assert.equal(state.routes[0].params.note, 'a+b c');
  }
});
test('malformed long percent-encoded URL completes within a bounded child process', () => {
  const moduleUrl = new URL('../node_modules/@react-navigation/core/lib/module/getStateFromPath.js', import.meta.url).href;
  const code = `import {getStateFromPath} from ${JSON.stringify(moduleUrl)};
    const value = '%E0%A4'.repeat(8000);
    const state = getStateFromPath('/Auth?probe='+value);
    if(state.routes[0].name!=='Auth'||typeof state.routes[0].params.probe!=='string') process.exit(2);`;
  const result = spawnSync(process.execPath, ['--input-type=module', '-e', code], { timeout: 5000, encoding: 'utf8' });
  assert.equal(result.error, undefined, 'malformed query parser must not hang');
  assert.equal(result.status, 0, result.stderr);
});

test('route-key generator rejects unsafe sizes without hanging', () => {
  const code = `const {nanoid,customAlphabet}=require('nanoid/non-secure');
    if(nanoid().length!==21) process.exit(2);
    try { nanoid(-1); } catch {}
    try { customAlphabet('abc',0)(); } catch {}`;
  const result = spawnSync(process.execPath, ['-e', code], {
    cwd: new URL('..', import.meta.url), timeout: 3000, encoding: 'utf8',
  });
  assert.equal(result.error, undefined, 'invalid generator sizes must not hang');
  assert.equal(result.status, 0, result.stderr);
});
