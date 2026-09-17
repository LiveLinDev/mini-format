/* dist.test.ts — HU13: compilación ESM usable sin Node (navegador) y declaraciones .d.ts.
 * Construye dist con tools/build_node.mjs en un directorio temporal y
 *  1) analiza los imports: solo módulos relativos del propio paquete, ningún `node:` ni require;
 *  2) carga dist en un contexto vm sin APIs de Node (sin process, require, Buffer, fs) con solo
 *     globales de navegador (TextEncoder/TextDecoder/URL) y valida documentos allí;
 *  3) si TypeScript está instalado, compila un consumidor estricto contra dist/index.d.ts.
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { after, before, describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { ROOT, lf, read } from './helpers.ts';

let tmp = '';
let dist = '';
let hasTypeScript = true;
try {
  createRequire(path.join(ROOT, 'ts', 'package.json')).resolve('typescript/package.json');
} catch {
  hasTypeScript = false;
}

before(() => {
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'mini-dist-'));
  dist = path.join(tmp, 'dist');
  const args = ['--no-warnings', path.join(ROOT, 'tools', 'build_node.mjs'), dist];
  if (!hasTypeScript) args.push('--no-types');
  const r = spawnSync(process.execPath, args, { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stdout + r.stderr);
});

after(() => {
  if (tmp) fs.rmSync(tmp, { recursive: true, force: true });
});

/** Especificadores de import/export estáticos y dinámicos de un módulo ESM. */
function specifiers(code: string): string[] {
  const out: string[] = [];
  const re = /(?:^|[;\s}])(?:import|export)\s*(?:[\w*{}\s,$]+\s*from\s*)?['"]([^'"]+)['"]|import\s*\(\s*['"]([^'"]+)['"]\s*\)/g;
  for (const m of code.matchAll(re)) out.push(m[1] ?? m[2]);
  return out;
}

describe('HU13 escenario 3: la compilación ESM valida documentos sin Node', () => {
  test('dist/*.js solo importa módulos relativos del paquete', () => {
    const files = fs.readdirSync(dist).filter(f => f.endsWith('.js'));
    assert.ok(files.includes('index.js') && files.includes('repair.js') && files.includes('adapters.js'));
    for (const f of files) {
      const code = fs.readFileSync(path.join(dist, f), 'utf8');
      for (const spec of specifiers(code)) {
        assert.match(spec, /^\.\/[\w-]+\.js$/, `${f} importa '${spec}'`);
        assert.ok(fs.existsSync(path.join(dist, spec)), `${f} -> ${spec} no existe`);
      }
      assert.doesNotMatch(code, /\brequire\s*\(|from\s*['"]node:|import\s*\(\s*['"]node:/, f);
    }
  });

  test('carga y valida en un contexto sin APIs de Node', () => {
    const contract = JSON.parse(read(path.join(ROOT, 'forks', 'cls', 'contract.json')));
    const valid = lf(read(path.join(ROOT, 'forks', 'cls', 'fixtures', 'valid.mini')));
    const script = path.join(tmp, 'sandbox.mjs');
    fs.writeFileSync(script, `
import vm from 'node:vm';
import fs from 'node:fs';
import path from 'node:path';
const [dist, input] = process.argv.slice(2);
const { contract, valid } = JSON.parse(fs.readFileSync(input, 'utf8'));
// Solo globales disponibles en un navegador; nada de process, require, Buffer, setImmediate.
const context = vm.createContext({ TextEncoder, TextDecoder, URL, console });
const cache = new Map();
async function load(file) {
  if (cache.has(file)) return cache.get(file);
  const mod = new vm.SourceTextModule(fs.readFileSync(file, 'utf8'), { context, identifier: 'https://example.test/' + path.basename(file) });
  cache.set(file, mod);
  return mod;
}
const entry = await load(path.join(dist, 'index.js'));
await entry.link(async spec => {
  if (!spec.startsWith('./')) throw new Error('import no relativo: ' + spec);
  return load(path.join(dist, spec));
});
await entry.evaluate();
context.lib = entry.namespace;
context.input = { contract, valid };
const code = \`(async () => {
  const m = lib;
  const out = { env: [typeof process, typeof require, typeof Buffer, typeof fetch] };
  const doc = m.parse(input.valid, input.contract);
  out.records = doc.records.length;
  const bad = input.valid.replace('|0.91|', '|x|');
  out.codes = m.parse(bad, input.contract, { strict: false }).errors.map(e => e.code);
  const reader = m.createReader(input.contract);
  for (const ch of input.valid) reader.push(ch);
  out.stream = reader.end().valid;
  const req = m.repairRequest(bad, input.contract, 'es');
  out.repair = req.lines;
  out.merged = m.mergeRepair(bad, 'cls|n=1\\\\n' + input.valid.split('\\\\n')[1], input.contract, req).ok;
  const c = m.fromJsonSchema({ type: 'object', properties: { a: { type: 'integer' } }, required: ['a'] }, { prefix: 'z' });
  out.schema = m.parse('z|n=1\\\\n5', c).records[0].a;
  const sim = new m.SimulatedAdapter('sim', { responses: [input.valid] });
  let n = 0;
  const it = m.streamRecords(sim, input.contract, { system: '', user: '', maxTokens: 4096 });
  for (let s = await it.next(); !s.done; s = await it.next()) n++;
  out.adapter = n;
  try { m.Registry.load(); out.registry = 'loaded'; } catch (e) { out.registry = String(e.message); }
  return JSON.stringify(out);
})()\`;
const result = await vm.runInContext(code, context);
process.stdout.write(result);
`);
    const input = path.join(tmp, 'input.json');
    fs.writeFileSync(input, JSON.stringify({ contract, valid }));
    const r = spawnSync(process.execPath, ['--experimental-vm-modules', '--no-warnings', script, dist, input], { encoding: 'utf8' });
    assert.equal(r.status, 0, r.stderr);
    const out = JSON.parse(r.stdout);
    assert.deepEqual(out.env, ['undefined', 'undefined', 'undefined', 'undefined']);
    assert.equal(out.records, 12);
    assert.deepEqual(out.codes, ['E06']);
    assert.equal(out.stream, 12);
    assert.deepEqual(out.repair, [2]);
    assert.equal(out.merged, true);
    assert.equal(out.schema, 5);
    assert.equal(out.adapter, 12);
    assert.match(out.registry, /requires Node\.js/);
  });
});

describe('HU13: declaraciones .d.ts', { skip: hasTypeScript ? false : 'TypeScript no instalado (npm install en ts/)' }, () => {
  test('dist incluye .d.ts y un consumidor estricto compila contra ellas', () => {
    for (const f of fs.readdirSync(dist).filter(x => x.endsWith('.js'))) {
      const dts = path.join(dist, f.replace(/\.js$/, '.d.ts'));
      assert.ok(fs.existsSync(dts), dts);
      assert.doesNotMatch(fs.readFileSync(dts, 'utf8'), /from '\.\/[\w-]+\.ts'/, dts);
    }
    const pkg = JSON.parse(read(path.join(ROOT, 'ts', 'package.json')));
    assert.equal(pkg.types, './dist/index.d.ts');
    assert.equal(pkg.exports['.'].types, './dist/index.d.ts');
    assert.deepEqual(pkg.dependencies ?? {}, {});
    const consumer = path.join(tmp, 'consumer.ts');
    fs.writeFileSync(consumer, [
      "import { parse, repairRequest, fromJsonSchema, SimulatedAdapter, streamRecords } from './dist/index.js';",
      "import type { Contract, MiniRecord, ModelAdapter, RepairRequest } from './dist/index.js';",
      "const c = fromJsonSchema({ type: 'object', properties: { a: { type: 'string' } }, required: ['a'] }, { prefix: 'q' });",
      "const recs: MiniRecord[] = parse('q|n=1\\nx', c).records;",
      "const req: RepairRequest = repairRequest('q|n=1\\nx', c);",
      "const adapter: ModelAdapter = new SimulatedAdapter();",
      "export async function run(contract: Contract): Promise<number> {",
      "  let n = recs.length + req.items.length;",
      "  for await (const r of streamRecords(adapter, contract, { system: '', user: '', maxTokens: 10 })) n += r.index;",
      "  return n;",
      '}',
      '',
    ].join('\n'));
    fs.writeFileSync(path.join(tmp, 'tsconfig.json'), JSON.stringify({
      compilerOptions: {
        strict: true, noEmit: true, target: 'ES2022', module: 'NodeNext', moduleResolution: 'NodeNext',
        lib: ['ES2022', 'DOM'], types: [], skipLibCheck: false,
      },
      files: ['consumer.ts'],
    }));
    fs.writeFileSync(path.join(tmp, 'package.json'), '{"type":"module"}');
    const tsc = path.join(path.dirname(createRequire(path.join(ROOT, 'ts', 'package.json')).resolve('typescript/package.json')), 'bin', 'tsc');
    const r = spawnSync(process.execPath, [tsc, '-p', path.join(tmp, 'tsconfig.json')], { encoding: 'utf8' });
    assert.equal(r.status, 0, r.stdout + r.stderr);
  });
});
