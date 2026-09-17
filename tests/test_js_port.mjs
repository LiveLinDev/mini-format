// Playground engine conformance (HU06). js/mini.js is generated from ts/src by
// tools/build_js.mjs; this test checks that the committed file is up to date, runs
// EVERY case of conformance/cases against it, and keeps the fixture checks against
// the Python reference output (parse -> canonical, dumps -> text, negative fixtures).
//   node tests/test_js_port.mjs
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const require = createRequire(import.meta.url);
const MINI = require('../js/mini.js');
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const eq = (a, b) => JSON.stringify(norm(a)) === JSON.stringify(norm(b));
function norm(x) { if (Array.isArray(x)) return x.map(norm); if (x && typeof x === 'object') { const o = {}; for (const k of Object.keys(x).sort()) o[k] = norm(x[k]); return o; } if (typeof x === 'number') return Number(x.toFixed(9)); return x; }
let fails = 0, checks = 0;
{
  const { buildBundle } = await import('../tools/build_js.mjs');
  checks++;
  if (fs.readFileSync(path.join(ROOT, 'js/mini.js'), 'utf8').replace(/\r\n/g, '\n') !== buildBundle()) {
    console.log('FAIL js/mini.js is out of date: run node --no-warnings tools/build_js.mjs'); fails++;
  }
  const { runSuite } = await import('../conformance/run_js.mjs');
  const res = runSuite(MINI);
  checks += res.total;
  for (const [id, msg] of res.failures) { console.log('FAIL conformance', id, msg); fails++; }
  if (res.total < 300) { console.log('FAIL conformance suite too small', res.total); fails++; }
}
for (const dir of fs.readdirSync(path.join(ROOT, 'forks'), { withFileTypes: true })) {
  if (!dir.isDirectory()) continue;
  const p = path.join(ROOT, 'forks', dir.name);
  const c = MINI.normalizeContract(JSON.parse(fs.readFileSync(path.join(p, 'contract.json'), 'utf8')));
  const text = fs.readFileSync(path.join(p, 'fixtures/valid.mini'), 'utf8');
  const ref = JSON.parse(fs.readFileSync(path.join(p, 'fixtures/canonical.json'), 'utf8'));
  const doc = MINI.parse(text, c); checks++;
  if (!eq(doc.canonical(), ref)) { console.log('FAIL canonical', dir.name); fails++; }
  checks++; if (MINI.dumps(ref, c) !== text.replace(/\r\n/g, '\n').replace(/\n$/, '')) { console.log('FAIL dumps', dir.name); fails++; }
  const esc = path.join(p, 'fixtures/escaping.mini');
  if (fs.existsSync(esc)) { checks++; const r2 = JSON.parse(fs.readFileSync(path.join(p, 'fixtures/escaping.json'), 'utf8')); if (!eq(MINI.parse(fs.readFileSync(esc, 'utf8'), c).canonical(), r2)) { console.log('FAIL escaping', dir.name); fails++; } }
  for (const f of fs.readdirSync(path.join(p, 'fixtures'))) if (f.startsWith('bad_')) { checks++; try { MINI.parse(fs.readFileSync(path.join(p, 'fixtures', f), 'utf8'), c); console.log('FAIL should reject', dir.name, f); fails++; } catch (e) { if (!e.errors) { console.log('FAIL wrong error', dir.name, f, e); fails++; } } }
  if (c.parent) { checks++; const parent = MINI.normalizeContract(JSON.parse(fs.readFileSync(path.join(ROOT, 'forks', c.parent, 'contract.json'), 'utf8'))); if (MINI.checkFork(c, parent).length) { console.log('FAIL fork check', dir.name); fails++; } }
}
{
  const c = MINI.normalizeContract(JSON.parse(fs.readFileSync(path.join(ROOT, 'forks/a/contract.json'), 'utf8')));
  const lines = fs.readFileSync(path.join(ROOT, 'forks/a/fixtures/valid.mini'), 'utf8').trim().split('\n');
  lines[0] += '|v=2';
  lines[1] += '|future';
  checks++;
  try { if (MINI.parse(lines.join('\n'), c).records.length !== 12) { console.log('FAIL newer-version tail'); fails++; } }
  catch (e) { console.log('FAIL newer-version tail', e); fails++; }
}
console.log(`${checks - fails}/${checks} checks passed`);
process.exit(fails ? 1 : 0);
