import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validateCloudEnv, verifyCloudBundle } from '../scripts/cloud-build-contract.mjs';
const env = { EXPO_PUBLIC_TRANSPORT: 'supabase', EXPO_PUBLIC_USE_MOCK: 'false', EXPO_PUBLIC_SUPABASE_URL: 'https://synthetic.supabase.co', EXPO_PUBLIC_SUPABASE_ANON_KEY: 'sb_publishable_synthetic_key_for_test' };
test('cloud build rejects missing transport, URL, and mock mode', () => {
  for (const change of [{ EXPO_PUBLIC_TRANSPORT: undefined }, { EXPO_PUBLIC_SUPABASE_URL: undefined }, { EXPO_PUBLIC_USE_MOCK: 'true' }]) assert.throws(() => validateCloudEnv({ ...env, ...change }));
});
test('service-role and secret keys cannot enter web bundle', () => {
  const jwt = 'eyJ.' + Buffer.from(JSON.stringify({ role: 'service_role' })).toString('base64url') + '.signature';
  for (const key of ['sb_secret_synthetic_test', jwt]) assert.throws(() => validateCloudEnv({ ...env, EXPO_PUBLIC_SUPABASE_ANON_KEY: key }));
});
function bundle(transport, url = env.EXPO_PUBLIC_SUPABASE_URL) {
  return `__d(function(g,r,i,a,m,e,d){e.CLOUD_TRANSPORT=${transport};e.cloudLogin=async()=>{};e.supabase=()=>r(1).createClient('${url}','${env.EXPO_PUBLIC_SUPABASE_ANON_KEY}',{auth:{persistSession:true}})},1,[]);`;
}
test('stale Metro output with cloud transport OFF is rejected', () => assert.throws(() => verifyCloudBundle(bundle(false), env), /Compiled transport/));
test('compiled URL must match intended project', () => assert.throws(() => verifyCloudBundle(bundle(true, 'https://wrong.supabase.co'), env), /Compiled Supabase URL/));
test('configured compiled cloud bundle passes without exporting the key', () => {
  const result = verifyCloudBundle(bundle(true), env);
  assert.equal(result.transport, 'supabase');
  assert.ok(!JSON.stringify(result).includes(env.EXPO_PUBLIC_SUPABASE_ANON_KEY));
});
