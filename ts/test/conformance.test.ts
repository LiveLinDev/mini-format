/* conformance.test.ts — runner de la suite de conformidad compartida (../conformance/).
 * Se omite si la carpeta no existe (MINI_CONFORMANCE_DIR permite apuntar a otra ruta). Formato admitido para cada caso:
 *   { id, contrato | familia, entrada, modo, esperado: { canonical | errores: [{codigo, linea}] } }
 * - contrato: objeto contract.json, o texto con el prefijo de una familia de forks/.
 * - familia:  prefijo de una familia de forks/.
 * - entrada:  texto .mini (o `entrada_archivo`: ruta relativa al JSON del caso).
 * - modo:     "estricto" | "strict" (por defecto) | "tolerante" | "lenient".
 * Cada archivo *.json puede contener un caso, un arreglo de casos o { casos | cases: [...] }.
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { MiniValidationError, canonicalEqual, normalizeContract, parse } from '../src/index.ts';
import type { Contract, ContractJSON, Document, MiniError } from '../src/index.ts';
import { REG, ROOT } from './helpers.ts';

const DIR = process.env.MINI_CONFORMANCE_DIR ? path.resolve(process.env.MINI_CONFORMANCE_DIR) : path.join(ROOT, 'conformance');
const EXISTS = fs.existsSync(DIR) && fs.statSync(DIR).isDirectory();

interface ExpectedError {
  codigo?: string;
  code?: string;
  linea?: number;
  line?: number;
}

interface Case {
  id?: string;
  contrato?: ContractJSON | string;
  familia?: string;
  entrada?: string;
  entrada_archivo?: string;
  modo?: string;
  esperado?: { canonical?: Record<string, unknown>; errores?: ExpectedError[] };
  __file: string;
}

function listJson(dir: string): string[] {
  const out: string[] = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...listJson(p));
    else if (e.isFile() && e.name.endsWith('.json')) out.push(p);
  }
  return out.sort();
}

function loadCases(): Case[] {
  const cases: Case[] = [];
  for (const file of listJson(DIR)) {
    let data: unknown;
    try {
      data = JSON.parse(fs.readFileSync(file, 'utf8'));
    } catch {
      continue;
    }
    const arr = Array.isArray(data)
      ? data
      : data && typeof data === 'object' && Array.isArray((data as { casos?: unknown }).casos)
        ? (data as { casos: unknown[] }).casos
        : data && typeof data === 'object' && Array.isArray((data as { cases?: unknown }).cases)
          ? (data as { cases: unknown[] }).cases
          : [data];
    for (const c of arr) {
      if (c && typeof c === 'object' && ('entrada' in c || 'entrada_archivo' in c) && 'esperado' in c) {
        cases.push({ ...(c as object), __file: file } as Case);
      }
    }
  }
  return cases;
}

function resolveContract(k: Case): Contract {
  const ref = k.contrato ?? k.familia;
  if (typeof ref === 'string') return REG.get(ref);
  if (ref && typeof ref === 'object') return normalizeContract(ref);
  throw new Error(`caso ${k.id}: falta 'contrato' o 'familia'`);
}

function isStrict(modo: string | undefined): boolean {
  const m = (modo || 'estricto').toLowerCase();
  return !(m.startsWith('toler') || m === 'lenient' || m === 'leniente');
}

function sameErrors(got: readonly MiniError[], want: readonly ExpectedError[]): boolean {
  const norm = (code: string | undefined, line: number | undefined) => `${code}@${line === undefined ? '*' : line}`;
  const w = want.map(e => norm(e.codigo ?? e.code, e.linea ?? e.line)).sort();
  const withLine = want.every(e => (e.linea ?? e.line) !== undefined);
  const g = got.map(e => norm(e.code, withLine ? e.line : undefined)).sort();
  if (!withLine) return JSON.stringify([...new Set(g)]) === JSON.stringify([...new Set(w)]);
  return JSON.stringify(g) === JSON.stringify(w);
}

describe('conformidad (../conformance)', { skip: EXISTS ? false : 'no existe la carpeta conformance/' }, () => {
  const cases = EXISTS ? loadCases() : [];

  test('hay casos de conformidad', () => {
    assert.ok(cases.length > 0, `sin casos en ${DIR}`);
  });

  for (const k of cases) {
    const name = `${k.id ?? path.basename(k.__file)}`;
    test(name, () => {
      const c = resolveContract(k);
      const text = k.entrada !== undefined ? k.entrada : fs.readFileSync(path.resolve(path.dirname(k.__file), k.entrada_archivo as string), 'utf8');
      const strict = isStrict(k.modo);
      const want = k.esperado || {};
      const wantErrors = want.errores || [];
      let doc: Document | null = null;
      let thrown: MiniValidationError | null = null;
      try {
        doc = parse(text, c, { strict });
      } catch (e) {
        if (e instanceof MiniValidationError) thrown = e;
        else throw e;
      }
      if (strict) {
        if (wantErrors.length) {
          assert.ok(thrown, `${name}: se esperaba rechazo`);
          assert.ok(sameErrors(thrown.errors, wantErrors), `${name}: errores ${thrown.errors.map(String).join('; ')}`);
        } else {
          assert.equal(thrown, null, `${name}: ${thrown && thrown.message}`);
        }
      } else {
        assert.ok(doc);
        assert.ok(sameErrors(doc.errors, wantErrors), `${name}: errores ${doc.errors.map(String).join('; ')}`);
      }
      if (want.canonical !== undefined) {
        assert.ok(doc, `${name}: se esperaba documento`);
        assert.ok(canonicalEqual(doc.toCanonical(), want.canonical), `${name}: canonical distinto`);
      }
    });
  }
});
