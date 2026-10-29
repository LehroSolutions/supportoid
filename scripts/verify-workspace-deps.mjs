import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
for (const [workspace, dependency, kind] of [
  ['frontend', 'vite', 'devDependencies'],
  ['frontend', 'react-router-dom', 'dependencies'],
  ['.', '@playwright/test', 'devDependencies'],
]) {
  const manifestPath = resolve(root, workspace, 'package.json');
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
  const require = createRequire(manifestPath);
  const installed = require(`${dependency}/package.json`).version;
  const expected = manifest[kind][dependency];
  if (installed !== expected) throw new Error(`${workspace}: ${dependency} resolves ${installed}, expected ${expected}. Remove stale generated dependency trees and reinstall from the root lockfile.`);
  console.log(`${workspace}: ${dependency}@${installed}`);
}
