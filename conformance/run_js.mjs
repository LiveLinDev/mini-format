/* Runner de la suite de conformidad para el motor JavaScript del playground (js/mini.js).
 *
 *     node conformance/run_js.mjs              # resumen por categoría (sale con 1 si algo falla)
 *     node conformance/run_js.mjs -v           # motivo de cada fallo
 *     node conformance/run_js.mjs -k quotes    # filtra por id o categoría
 *     node conformance/run_js.mjs --engine ruta/a/otro-motor.js
 *
 * Reproduce la lógica de conformance/run_python.py descrita en conformance/README.md.
 * Correspondencia de API: en modo tolerante `parse` devuelve un Document con E01 y sin
 * cabecera cuando el documento no se puede construir (la referencia lanza excepción).
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const CASES_DIR = path.join(ROOT, 'conformance', 'cases');

export function loadEngine(file = path.join(ROOT, 'js', 'mini.js')) {
  return require(path.resolve(file));
}

export function loadCases(dir = CASES_DIR) {
  const out = [];
  for (const f of fs.readdirSync(dir).filter(x => x.endsWith('.json')).sort()) {
    out.push(...JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8')).cases);
  }
  return out;
}

/** Igualdad estructural: claves como conjunto y números con tolerancia 1e-12 (README §Canónico). */
export function canonicalEqual(a, b) {
  if (Array.isArray(a) || Array.isArray(b)) {
    return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((x, i) => canonicalEqual(x, b[i]));
  }
  if (a && b && typeof a === 'object' && typeof b === 'object') {
    const ka = Object.keys(a);
    const kb = new Set(Object.keys(b));
    return ka.length === kb.size && ka.every(k => kb.has(k) && canonicalEqual(a[k], b[k]));
  }
  if (typeof a === 'number' && typeof b === 'number') {
    return a === b || Math.abs(a - b) <= Math.max(1e-12 * Math.max(Math.abs(a), Math.abs(b)), 1e-12);
  }
  return a === b;
}

const pairs = errors => new Set(errors.map(e => `${e.code}@${Number(e.line)}`));
const fmt = s => [...s].sort().join(', ') || '(none)';

function checkErrors(expected, got) {
  const exp = pairs(expected);
  const act = pairs(got);
  return exp.size === act.size && [...exp].every(p => act.has(p)) ? null : `errors: expected ${fmt(exp)}, got ${fmt(act)}`;
}

/** Ejecuta un caso contra `MINI`; devuelve null si pasa o el motivo del fallo. */
export function runCase(MINI, k) {
  const exp = k.expected;
  const isMiniError = e => e instanceof MINI.MiniError;
  const family = prefix => MINI.normalizeContract(JSON.parse(fs.readFileSync(path.join(ROOT, 'forks', prefix, 'contract.json'), 'utf8')));
  const caseContract = () => (k.contract !== undefined ? MINI.normalizeContract(k.contract) : family(k.family));
  try {
    if (k.mode === 'contract') {
      let got = [];
      try {
        MINI.normalizeContract(k.input);
      } catch (e) {
        if (!isMiniError(e)) throw e;
        got = [e];
      }
      return checkErrors(exp.errors || [], got);
    }
    if (k.mode === 'fork') {
      const parent = typeof k.parent === 'string' ? family(k.parent) : MINI.normalizeContract(k.parent);
      return checkErrors(exp.errors || [], MINI.checkFork(caseContract(), parent));
    }
    const contract = caseContract();
    if (k.mode === 'dumps') {
      let text;
      try {
        text = MINI.dumps(k.input, contract);
      } catch (e) {
        if (!isMiniError(e)) throw e;
        if (!exp.rejected) return `serializer rejected the object: ${e}`;
        if (exp.errors && !pairs(exp.errors).has(`${e.code}@${Number(e.line)}`)) {
          return `serializer error: expected ${fmt(pairs(exp.errors))}, got ${e.code}@${e.line}`;
        }
        return null;
      }
      if (exp.rejected) return `serializer should reject, produced ${JSON.stringify(text)}`;
      if (text !== exp.mini) return `dumps: expected ${JSON.stringify(exp.mini)}, got ${JSON.stringify(text)}`;
      try {
        MINI.parse(text, contract);
      } catch (e) {
        if (e instanceof MINI.MiniValidationError) return `serialized text does not parse: ${e.message}`;
        throw e;
      }
      return null;
    }
    if (k.mode === 'strict') {
      let doc;
      try {
        doc = MINI.parse(k.input, contract, { strict: true });
      } catch (e) {
        if (!(e instanceof MINI.MiniValidationError)) throw e;
        if (exp.errors === undefined) return `unexpected rejection: ${fmt(pairs(e.errors))}`;
        return checkErrors(exp.errors, e.errors);
      }
      if (exp.errors && exp.errors.length) return `should be rejected with ${fmt(pairs(exp.errors))}`;
      const canon = doc.canonical();
      if (!canonicalEqual(canon, exp.canonical)) return 'canonical mismatch: got ' + JSON.stringify(canon).slice(0, 400);
      if (exp.mini !== undefined) {
        const text = MINI.dumps(canon, contract);
        if (text !== exp.mini) return `re-serialization: expected ${JSON.stringify(exp.mini)}, got ${JSON.stringify(text)}`;
        if (!canonicalEqual(MINI.parse(text, contract).canonical(), exp.canonical)) return 'round-trip mismatch after re-serialization';
      }
      return null;
    }
    if (k.mode === 'lenient') {
      const doc = MINI.parse(k.input, contract, { strict: false });
      if (doc.headerLine === 0 && doc.errors.some(e => e.code === 'E01')) {
        if (exp.canonical !== undefined) return `lenient parse produced no document: ${fmt(pairs(doc.errors))}`;
        return checkErrors(exp.errors || [], doc.errors);
      }
      if (exp.canonical === undefined) return 'lenient parse should fail at document level';
      const msg = checkErrors(exp.errors || [], doc.errors);
      if (msg) return msg;
      const canon = doc.canonical();
      if (!canonicalEqual(canon, exp.canonical)) return 'canonical mismatch: got ' + JSON.stringify(canon).slice(0, 400);
      if (exp.diagnostics) {
        const got = { invalid_lines: doc.invalidLines(), missing_records: doc.missingRecords };
        for (const [key, v] of Object.entries(exp.diagnostics)) {
          if (JSON.stringify(got[key]) !== JSON.stringify(v)) {
            return `diagnostics.${key}: expected ${JSON.stringify(v)}, got ${JSON.stringify(got[key])}`;
          }
        }
      }
      return null;
    }
    return `unknown mode ${JSON.stringify(k.mode)}`;
  } catch (e) {
    return `crash: ${e instanceof Error ? `${e.name}: ${e.message}` : String(e)}`;
  }
}

/** Ejecuta la suite; devuelve {total, failures: [[id, msg]], categories: {cat: {pass, fail}}}. */
export function runSuite(MINI, cases = loadCases()) {
  const categories = {};
  const failures = [];
  for (const k of cases) {
    const msg = runCase(MINI, k);
    const cat = (categories[k.category] ||= { pass: 0, fail: 0 });
    if (msg === null) cat.pass++;
    else {
      cat.fail++;
      failures.push([k.id, msg]);
    }
  }
  return { total: cases.length, failures, categories };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const opt = name => {
    const i = args.indexOf(name);
    return i >= 0 ? args[i + 1] : undefined;
  };
  const MINI = loadEngine(opt('--engine'));
  const filter = opt('-k');
  let cases = loadCases();
  if (filter) cases = cases.filter(k => k.id.includes(filter) || k.category === filter);
  const res = runSuite(MINI, cases);
  for (const cat of Object.keys(res.categories).sort()) {
    const c = res.categories[cat];
    console.log(`${cat.padEnd(12)} ${String(c.pass).padStart(4)}/${String(c.pass + c.fail).padEnd(4)}`);
  }
  for (const [id, msg] of res.failures) console.log(args.includes('-v') ? `FAIL ${id}: ${msg}` : `FAIL ${id}`);
  console.log(`${res.total - res.failures.length}/${res.total} cases passed`);
  process.exit(res.failures.length ? 1 : 0);
}
