/* conformance.test.ts — runner TypeScript de la suite de conformidad compartida (../conformance/).
 * Reproduce la lógica de conformance/run_python.py descrita en conformance/README.md:
 * modos strict, lenient, dumps, contract y fork; errores comparados como conjunto de pares
 * (code, line); canónico por igualdad estructural tolerante a int/float.
 * Correspondencias con la API de TypeScript:
 * - lenient sin `expected.canonical` ("el documento no se puede construir"): la referencia lanza
 *   excepción; `parse` de TS devuelve un Document con E01 y sin cabecera. Se trata como no construido.
 * - diagnostics.invalid_lines / missing_records -> Document.invalidLines() / Document.missingRecords.
 * Se omite si la carpeta no existe (MINI_CONFORMANCE_DIR permite apuntar a otra ruta).
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {
  MiniError, MiniValidationError, canonicalEqual, checkFork, dumps, loadContract, normalizeContract, parse,
} from '../src/index.ts';
import type { Contract, ContractJSON, Document } from '../src/index.ts';
import { FORKS, ROOT } from './helpers.ts';

const DIR = process.env.MINI_CONFORMANCE_DIR ? path.resolve(process.env.MINI_CONFORMANCE_DIR) : path.join(ROOT, 'conformance');
const CASES_DIR = fs.existsSync(path.join(DIR, 'cases')) ? path.join(DIR, 'cases') : DIR;
const EXISTS = fs.existsSync(CASES_DIR) && fs.statSync(CASES_DIR).isDirectory();

interface ErrorPair { code: string; line: number }

interface ConformanceCase {
  id: string;
  category: string;
  description?: string;
  mode: 'strict' | 'lenient' | 'dumps' | 'contract' | 'fork';
  family?: string;
  contract?: ContractJSON;
  parent?: string | ContractJSON;
  input: unknown;
  expected: {
    canonical?: Record<string, unknown>;
    errors?: ErrorPair[];
    mini?: string;
    rejected?: boolean;
    diagnostics?: { invalid_lines?: number[]; missing_records?: number };
  };
}

export function loadCases(dir: string = CASES_DIR): ConformanceCase[] {
  const out: ConformanceCase[] = [];
  for (const f of fs.readdirSync(dir).filter(x => x.endsWith('.json')).sort()) {
    const doc = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
    out.push(...(doc.cases as ConformanceCase[]));
  }
  return out;
}

const familyCache = new Map<string, Contract>();
function familyContract(prefix: string): Contract {
  let c = familyCache.get(prefix);
  if (!c) {
    c = loadContract(path.join(FORKS, prefix, 'contract.json'));
    familyCache.set(prefix, c);
  }
  return c;
}

function caseContract(k: ConformanceCase): Contract {
  if (k.contract !== undefined) return normalizeContract(k.contract);
  return familyContract(k.family as string);
}

function pairs(errors: readonly (ErrorPair | MiniError)[]): Set<string> {
  return new Set(errors.map(e => `${e.code}@${Number(e.line)}`));
}

function fmt(s: Set<string>): string {
  return [...s].sort().join(', ') || '(none)';
}

function checkErrors(expected: readonly ErrorPair[], got: readonly (ErrorPair | MiniError)[]): string | null {
  const exp = pairs(expected);
  const act = pairs(got);
  const same = exp.size === act.size && [...exp].every(p => act.has(p));
  return same ? null : `errors: expected ${fmt(exp)}, got ${fmt(act)}`;
}

/** Documento tolerante que "no se pudo construir" (equivale a la excepción de la referencia). */
function notBuilt(doc: Document): boolean {
  return doc.headerLine === 0 && doc.errors.some(e => e.code === 'E01');
}

/** Ejecuta un caso; devuelve null si pasa o el motivo del fallo. */
export function runCase(k: ConformanceCase): string | null {
  const exp = k.expected;
  try {
    if (k.mode === 'contract') {
      let got: MiniError[] = [];
      try {
        normalizeContract(k.input as ContractJSON);
      } catch (e) {
        if (!(e instanceof MiniError)) throw e;
        got = [e];
      }
      return checkErrors(exp.errors || [], got);
    }

    if (k.mode === 'fork') {
      const child = caseContract(k);
      const parent = typeof k.parent === 'string' ? familyContract(k.parent) : normalizeContract(k.parent as ContractJSON);
      return checkErrors(exp.errors || [], checkFork(child, parent));
    }

    const contract = caseContract(k);

    if (k.mode === 'dumps') {
      let text: string;
      try {
        text = dumps(k.input as Record<string, unknown>, contract);
      } catch (e) {
        if (!(e instanceof MiniError)) throw e;
        return exp.rejected ? null : `serializer rejected the object: ${e}`;
      }
      if (exp.rejected) return `serializer should reject, produced ${JSON.stringify(text)}`;
      if (text !== exp.mini) return `dumps: expected ${JSON.stringify(exp.mini)}, got ${JSON.stringify(text)}`;
      try {
        parse(text, contract);
      } catch (e) {
        if (e instanceof MiniValidationError) return `serialized text does not parse: ${e.message}`;
        throw e;
      }
      return null;
    }

    if (k.mode === 'strict') {
      let doc: Document;
      try {
        doc = parse(k.input as string, contract, { strict: true });
      } catch (e) {
        if (!(e instanceof MiniValidationError)) throw e;
        if (exp.errors === undefined) return `unexpected rejection: ${fmt(pairs(e.errors))}`;
        return checkErrors(exp.errors, e.errors);
      }
      if (exp.errors && exp.errors.length) return `should be rejected with ${fmt(pairs(exp.errors))}`;
      const canon = doc.toCanonical();
      if (!canonicalEqual(canon, exp.canonical)) return 'canonical mismatch: got ' + JSON.stringify(canon).slice(0, 400);
      if (exp.mini !== undefined) {
        const text = dumps(canon, contract);
        if (text !== exp.mini) return `re-serialization: expected ${JSON.stringify(exp.mini)}, got ${JSON.stringify(text)}`;
        const back = parse(text, contract).toCanonical();
        if (!canonicalEqual(back, exp.canonical)) return 'round-trip mismatch after re-serialization';
      }
      return null;
    }

    if (k.mode === 'lenient') {
      const doc = parse(k.input as string, contract, { strict: false });
      if (notBuilt(doc)) {
        if (exp.canonical !== undefined) return `lenient parse produced no document: ${fmt(pairs(doc.errors))}`;
        return checkErrors(exp.errors || [], doc.errors);
      }
      if (exp.canonical === undefined) return 'lenient parse should fail at document level';
      const msg = checkErrors(exp.errors || [], doc.errors);
      if (msg) return msg;
      const canon = doc.toCanonical();
      if (!canonicalEqual(canon, exp.canonical)) return 'canonical mismatch: got ' + JSON.stringify(canon).slice(0, 400);
      if (exp.diagnostics) {
        const got: Record<string, unknown> = { invalid_lines: doc.invalidLines(), missing_records: doc.missingRecords };
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

describe('conformidad (../conformance)', { skip: EXISTS ? false : 'no existe la carpeta conformance/' }, () => {
  const cases = EXISTS ? loadCases() : [];
  if (EXISTS && !cases.length) {
    test('la suite no tiene casos', () => assert.fail(`sin casos en ${CASES_DIR}`));
  }
  const byCategory = new Map<string, ConformanceCase[]>();
  for (const k of cases) {
    if (!byCategory.has(k.category)) byCategory.set(k.category, []);
    (byCategory.get(k.category) as ConformanceCase[]).push(k);
  }
  for (const [category, list] of [...byCategory].sort((a, b) => (a[0] < b[0] ? -1 : 1))) {
    describe(category, () => {
      for (const k of list) {
        test(k.id, () => {
          const msg = runCase(k);
          assert.equal(msg, null, `${k.id}: ${msg}`);
        });
      }
    });
  }
});
