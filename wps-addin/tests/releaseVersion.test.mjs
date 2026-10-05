import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('package, installation manifest and diagnostic events identify the same release', async () => {
  const root = new URL('../', import.meta.url);
  const pkg = JSON.parse(await readFile(new URL('package.json', root), 'utf8'));
  const manifest = await readFile(new URL('public/manifest.xml', root), 'utf8');
  const recorder = await readFile(new URL('src/diagnostics.ts', root), 'utf8');
  assert.equal(manifest.match(/<Version>([^<]+)<\/Version>/)?.[1], pkg.version);
  assert.equal(recorder.match(/const PLUGIN_VERSION = '([^']+)'/)?.[1], pkg.version);
});
