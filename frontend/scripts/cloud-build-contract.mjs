import assert from 'node:assert/strict';
import vm from 'node:vm';

export function validateCloudEnv(env) {
  assert.equal(env.EXPO_PUBLIC_TRANSPORT, 'supabase', 'Cloud build requires EXPO_PUBLIC_TRANSPORT=supabase');
  assert.equal(env.EXPO_PUBLIC_USE_MOCK, 'false', 'Cloud build requires EXPO_PUBLIC_USE_MOCK=false');
  assert.match(env.EXPO_PUBLIC_SUPABASE_URL ?? '', /^https:\/\/[a-z0-9]+\.supabase\.co\/?$/, 'Missing/invalid Supabase URL');
  const key = env.EXPO_PUBLIC_SUPABASE_ANON_KEY ?? '';
  if (key.startsWith('sb_publishable_') && key.length > 25) return;
  // Legacy anon JWTs are public; never accept a service-role JWT in a web build.
  let payload;
  try { payload = JSON.parse(Buffer.from(key.split('.')[1], 'base64url').toString()); } catch {}
  assert.equal(payload?.role, 'anon', 'Only a publishable/anon key may enter the cloud bundle');
}

export function verifyCloudBundle(source, env) {
  validateCloudEnv(env);
  // Execute only our compiled auth configuration module, with all imports stubbed.
  // This checks the actual Expo output, including a stale Metro env substitution.
  const moduleSource = source.split(/\n(?=__d\()/).find(s =>
    s.includes('CLOUD_TRANSPORT') && /\.cloudLogin\s*=/.test(s) && /\.supabase\s*=/.test(s));
  assert.ok(moduleSource, 'Compiled Supabase module missing');
  let factory;
  vm.runInNewContext(moduleSource, { __d: fn => { factory = fn; } }, { timeout: 1000 });
  assert.equal(typeof factory, 'function', 'Compiled Supabase module is invalid');
  let captured;
  const exports = {};
  const deps = {
    createClient: (url, key, options) => { captured = { url, key, options }; return {}; },
    safeStorage: {},
  };
  factory({}, () => deps, null, null, { exports }, exports, []);
  assert.equal(exports.CLOUD_TRANSPORT, true, 'Compiled transport is not Supabase (stale/missing build env)');
  exports.supabase();
  assert.equal(captured.url, env.EXPO_PUBLIC_SUPABASE_URL, 'Compiled Supabase URL differs from build env');
  assert.equal(captured.key, env.EXPO_PUBLIC_SUPABASE_ANON_KEY, 'Compiled public key differs from build env');
  assert.equal(captured.options.auth.persistSession, true);
  return { transport: 'supabase', supabase_host: new URL(captured.url).hostname, public_key_type: captured.key.startsWith('sb_publishable_') ? 'publishable' : 'anon' };
}
