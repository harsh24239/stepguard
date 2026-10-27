// Compile tests with the same JSX transform as Vite; run with Node's built-in runner.
import { build } from 'esbuild';
import { mkdtemp, readdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

const directory = await mkdtemp(join(tmpdir(), 'stepguard-tests-'));
try {
  const files = (await readdir('tests')).filter(file => /\.test\.tsx?$/.test(file));
  await build({ entryPoints: files.map(file => `tests/${file}`), outdir: directory, outExtension: { '.js': '.cjs' }, bundle: true, platform: 'node', format: 'cjs', jsx: 'automatic', logLevel: 'warning' });
  const result = spawnSync(process.execPath, ['--test', ...files.map(file => join(directory, file.replace(/\.tsx?$/, '.cjs')))], { stdio: 'inherit' });
  process.exitCode = result.status ?? 1;
} finally {
  await rm(directory, { recursive: true, force: true });
}
