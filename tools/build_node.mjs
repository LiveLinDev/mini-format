/** Build plain ESM (+ .d.ts declarations) without asking end users to execute TypeScript in node_modules.
 *
 *   node tools/build_node.mjs [outDir] [--no-types]
 *
 * JavaScript is produced with Node's built-in type stripping (no dependencies). Declarations are
 * emitted with the TypeScript compiler from ts/node_modules (run `npm ci` in ts/ first); pass
 * --no-types to build only the JavaScript.
 */
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createRequire, stripTypeScriptTypes } from 'node:module';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const noTypes = args.includes('--no-types');
const positional = args.filter(a => !a.startsWith('--'));
const out = path.resolve(positional[0] || path.join(root, 'ts', 'dist'));
const relativeTs = /((?:from|import)\s*\(?\s*['"]\.\.?\/[^'"]+)\.ts(['"])/g;

fs.mkdirSync(out, { recursive: true });
for (const name of fs.readdirSync(path.join(root, 'ts', 'src')).sort()) {
  if (!name.endsWith('.ts')) continue;
  const source = fs.readFileSync(path.join(root, 'ts', 'src', name), 'utf8');
  const javascript = stripTypeScriptTypes(source, { mode: 'strip' }).replace(relativeTs, '$1.js$2');
  fs.writeFileSync(path.join(out, name.replace(/\.ts$/, '.js')), javascript, 'utf8');
}
console.log(`Built Node ESM: ${out}`);

if (!noTypes) {
  let tsc;
  try {
    const require = createRequire(path.join(root, 'ts', 'package.json'));
    tsc = path.join(path.dirname(require.resolve('typescript/package.json')), 'bin', 'tsc');
  } catch {
    console.error('TypeScript is not installed: run `npm ci` in ts/ to emit declarations, or pass --no-types.');
    process.exit(1);
  }
  const result = spawnSync(process.execPath, [
    tsc, '-p', path.join(root, 'ts', 'tsconfig.json'),
    '--noEmit', 'false', '--declaration', '--emitDeclarationOnly',
    '--rootDir', path.join(root, 'ts', 'src'), '--outDir', out,
  ], { stdio: 'inherit' });
  if (result.status !== 0) process.exit(result.status ?? 1);
  for (const name of fs.readdirSync(out)) {
    if (!name.endsWith('.d.ts')) continue;
    const file = path.join(out, name);
    fs.writeFileSync(file, fs.readFileSync(file, 'utf8').replace(relativeTs, '$1.js$2'), 'utf8');
  }
  console.log(`Emitted declarations: ${out}`);
}
