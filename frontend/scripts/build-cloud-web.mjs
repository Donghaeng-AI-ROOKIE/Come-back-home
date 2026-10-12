import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { validateCloudEnv, verifyCloudBundle } from './cloud-build-contract.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const env = { ...process.env };
const args = process.argv.slice(2);
if (args.length && (args.length !== 2 || args[0] !== '--env-file')) throw new Error('Usage: build-cloud-web.mjs [--env-file PATH]');
if (args.length) {
  for (const line of fs.readFileSync(args[1], 'utf8').split(/\r?\n/)) {
    if (!line.trim() || line.trimStart().startsWith('#')) continue;
    const match = line.match(/^(EXPO_PUBLIC_[A-Z0-9_]+)=(.*)$/);
    if (!match) throw new Error('Cloud env file may contain only EXPO_PUBLIC_ assignments');
    let value = match[2].trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) value = value.slice(1, -1);
    env[match[1]] = value;
  }
}
validateCloudEnv(env);
// Prevent untracked local dotenv files from overriding the selected deployment config.
env.EXPO_NO_DOTENV = '1';
const require = createRequire(import.meta.url);
function run(file, args) {
  const r = spawnSync(process.execPath, [file, ...args], { cwd: root, env, stdio: 'inherit' });
  if (r.error) throw r.error;
  if (r.status !== 0) process.exit(r.status ?? 1);
}
run(require.resolve('expo/bin/cli'), ['export', '--platform', 'web', '--clear']);
run(path.join(root, 'scripts/patch-boot-guard.mjs'), []);
const dist = path.join(root, 'dist');
const html = fs.readFileSync(path.join(dist, 'index.html'), 'utf8');
const js = [...html.matchAll(/<script[^>]+src="([^"]+\.js)"/g)].map(m => m[1]);
if (js.length !== 1) throw new Error('Expected one entry bundle in Expo index.html');
const source = fs.readFileSync(path.join(dist, js[0].replace(/^\//, '')), 'utf8');
const verified = verifyCloudBundle(source, env);
const git = spawnSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' });
const manifest = { ...verified, mock: false, built_at: new Date().toISOString(), source_commit: git.stdout.trim(), entry_bundle: js[0], entry_sha256: crypto.createHash('sha256').update(source).digest('hex') };
fs.writeFileSync(path.join(dist, 'cloud-build.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log('Cloud bundle verified:', JSON.stringify(manifest));
