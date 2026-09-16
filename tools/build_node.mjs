/** Build plain ESM without asking end users to execute TypeScript in node_modules. */
import fs from 'node:fs';
import path from 'node:path';
import { stripTypeScriptTypes } from 'node:module';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const out = path.resolve(process.argv[2] || path.join(root, 'ts', 'dist'));
fs.mkdirSync(out, { recursive: true });
for (const name of fs.readdirSync(path.join(root, 'ts', 'src')).sort()) {
  if (!name.endsWith('.ts')) continue;
  const source = fs.readFileSync(path.join(root, 'ts', 'src', name), 'utf8');
  const javascript = stripTypeScriptTypes(source, { mode: 'strip' })
    .replace(/(from\s+['"]\.\.?\/[^'"]+)\.ts(['"])/g, '$1.js$2');
  fs.writeFileSync(path.join(out, name.replace(/\.ts$/, '.js')), javascript, 'utf8');
}
console.log(`Built Node ESM: ${out}`);
