/* roundtrip.test.ts — ida y vuelta parse(dumps(obj)) == obj y dumps(parse(t)) == t (SPEC §9).
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  canonicalEqual, dumps, escapeElement, escapeScalar, formatNumber, parse, roundtripOk, splitFields, splitList,
  textOf, tokenize, MiniError,
} from '../src/index.ts';
import type { Contract, Field } from '../src/index.ts';
import { ALL, ALPHABET, BS, LF, REG, pick, randInt, rng } from './helpers.ts';

type R = () => number;

function randText(r: R, maxLen: number): string {
  let s = '';
  const len = randInt(r, 0, maxLen);
  for (let i = 0; i < len; i++) s += pick(r, ALPHABET);
  return s.trim();
}

function randNumber(r: R, f: Field, integer: boolean): number {
  // min/max son numéricos para int/float (string solo en date/decimal)
  const lo = f.min !== null ? Number(f.min) : -1000;
  const hi = f.max !== null ? Number(f.max) : 1000;
  if (integer) return randInt(r, Math.ceil(lo), Math.floor(hi));
  const special = [0.1 + 0.2, 1e-7, 1.5e-5, 123456789.125, 1e16, 1e22, 2.5e-300, -0.00001, 3];
  if (f.min === null && f.max === null && r() < 0.3) return pick(r, special);
  const v = Math.round((lo + r() * (hi - lo)) * 1000) / 1000;
  return Math.min(hi, Math.max(lo, v));
}

function randScalar(r: R, f: Field, asItem: boolean): unknown {
  const t = asItem ? f.item : f.type;
  const values = asItem ? f.item_values : f.values;
  if (t === 'int') return randNumber(r, asItem ? { ...f, min: null, max: null } : f, true);
  if (t === 'float') return randNumber(r, asItem ? { ...f, min: null, max: null } : f, false);
  if (t === 'bool') return r() < 0.5;
  if (t === 'enum') return pick(r, values as string[]);
  const s = randText(r, 10);
  return s === '' ? 'x' : s;
}

/** Registro aleatorio válido para el contrato (claves en el orden del objeto canónico). */
function randRecord(r: R, c: Contract, header: Record<string, unknown>, idx: number): Record<string, unknown> {
  const rec: Record<string, unknown> = {};
  for (const f of c.fields) {
    if (f.unique) {
      rec[f.name] = f.type === 'int' ? idx : `u${idx}`;
      continue;
    }
    if (f.type === 'list' || f.type === 'mlist') {
      const k = f.count_key && typeof header[f.count_key] === 'number' ? (header[f.count_key] as number) : null;
      const lo = f.min !== null ? Number(f.min) : 0;
      const hi = f.max !== null ? Number(f.max) : lo + 4;
      const size = k !== null ? k : randInt(r, f.type === 'mlist' ? Math.max(lo, 1) : lo, hi);
      const items = Array.from({ length: size }, () => randScalar(r, f, true));
      if (f.type === 'list') {
        rec[f.name] = items;
        continue;
      }
      rec[f.json_items] = items;
      const all = items.map((_, i) => i).filter(() => r() < 0.5);
      if (f.marker === 'exactly_one') rec[f.json_selected] = randInt(r, 0, size - 1);
      else if (f.marker === 'at_most_one') rec[f.json_selected] = r() < 0.5 ? null : randInt(r, 0, size - 1);
      else if (f.marker === 'at_least_one') rec[f.json_selected] = all.length ? all : [randInt(r, 0, size - 1)];
      else rec[f.json_selected] = all;
      continue;
    }
    if (f.optional && r() < 0.3) {
      rec[f.name] = null;
      continue;
    }
    if (f.type === 'tuple') {
      const o: Record<string, unknown> = {};
      for (const cmp of f.items) o[cmp.name] = cmp.optional && r() < 0.3 ? null : randScalar(r, cmp, false);
      rec[f.name] = o;
      continue;
    }
    rec[f.name] = randScalar(r, f, false);
  }
  return rec;
}

function randHeader(r: R, c: Contract, n: number): Record<string, unknown> {
  const h: Record<string, unknown> = { n };
  for (const [k, hk] of Object.entries(c.headerKeys)) {
    if (k === 'n') continue;
    if (k === 'v') {
      h.v = r() < 0.8 ? 1 : 2;
      continue;
    }
    if (!hk.required && r() < 0.3) continue;
    if (hk.type === 'int') h[k] = k === 'k' ? randInt(r, 2, 6) : randInt(r, -50, 50);
    else if (hk.type === 'float') h[k] = Math.round(r() * 1e4) / 100;
    else if (hk.type === 'bool') h[k] = r() < 0.5;
    else if (hk.type === 'enum') h[k] = pick(r, hk.values as string[]);
    else if (hk.type === 'list') h[k] = Array.from({ length: randInt(r, 1, 5) }, () => (hk.item === 'int' ? randInt(r, 0, 9) : randText(r, 6) || 'x'));
    else if (hk.type === 'tuple') {
      const o: Record<string, unknown> = {};
      for (const cmp of hk.items) o[cmp.name] = randScalar(r, cmp, false);
      h[k] = o;
    } else h[k] = randText(r, 12);
  }
  // clave extra desconocida: se conserva como texto
  if (r() < 0.5) h.model = randText(r, 8);
  return h;
}

describe('ida y vuelta', () => {
  for (const fx of ALL) {
    const c = fx.contract;
    test(`familia ${c.prefix}: 60 objetos aleatorios`, () => {
      const r = rng(0x5eed + c.prefix.length * 7919 + c.prefix.charCodeAt(0));
      for (let i = 0; i < 60; i++) {
        const n = randInt(r, 0, 6);
        const header = randHeader(r, c, n);
        // count_key: el valor de la cabecera debe respetar min/max de la lista
        for (const f of c.fields) {
          if (f.count_key && typeof header[f.count_key] === 'number') {
            const lo = f.min !== null ? Number(f.min) : 1;
            const hi = f.max !== null ? Number(f.max) : 6;
            header[f.count_key] = randInt(r, lo, hi);
          }
        }
        const records = Array.from({ length: n }, (_, j) => randRecord(r, c, header, j));
        const obj = { prefix: c.prefix, header, [c.records_key]: records };
        const text = dumps(obj, c);
        const back = parse(text, c).toCanonical();
        assert.ok(canonicalEqual(back, obj), `parse(dumps(obj)) != obj${LF}${text}${LF}${JSON.stringify(back)}${LF}${JSON.stringify(obj)}`);
        assert.equal(dumps(back, c), text);
        assert.ok(roundtripOk(obj, c));
      }
    });
  }

  test('dumps omite v=1 por defecto y las extensiones nulas finales', () => {
    const q = REG.get('q');
    const a = fixtureRecord();
    const text = dumps({ header: { v: 1, n: 99 }, items: [{ ...a, feedback: 'ok', hint: null, objective: null }] }, q);
    assert.equal(text.split(LF)[0], 'q|n=1');
    assert.ok(text.split(LF)[1].endsWith('|ok'));
  });

  test('el serializador rechaza valores fuera del contrato', () => {
    const a = REG.get('a');
    const rec = fixtureRecord();
    const bad = (patch: Record<string, unknown>, code: string) => {
      assert.throws(() => dumps({ header: {}, items: [{ ...rec, ...patch }] }, a), (e: unknown) => e instanceof MiniError && e.code === code);
    };
    bad({ bloom: 'L9' }, 'E10'); // SPEC 1.1 §9: código del parser
    bad({ id: null }, 'E06');
    bad({ correct: null }, 'E08');
    bad({ correct: 7 }, 'E08');
    bad({ options: null }, 'E06');
    bad({ irt: { a: 1, b: 2 } }, 'E06');
  });
});

function fixtureRecord(): Record<string, unknown> {
  const fx = ALL.find(x => x.contract.prefix === 'a');
  return { ...((fx as (typeof ALL)[number]).canonical.items as Record<string, unknown>[])[0] };
}

describe('codec', () => {
  const RESERVED = ['|', ',', '*', BS, LF, '"', ';', '=', ' '];

  test('escapeScalar ida y vuelta (2000 casos)', () => {
    const r = rng(7);
    const alphabet = [...'abcXYZ019 áéñ¿?'.split(''), ...RESERVED];
    for (let i = 0; i < 2000; i++) {
      let s = '';
      for (let k = randInt(r, 0, 12); k > 0; k--) s += pick(r, alphabet);
      s = s.trim();
      const toks = splitFields(escapeScalar(s), ',', 1);
      assert.equal(toks.length, 1);
      assert.equal(textOf(toks[0]), s);
    }
  });

  test('escapeElement ida y vuelta con marcador (2000 casos)', () => {
    const r = rng(11);
    const alphabet = [...'ab 9é'.split(''), ...RESERVED];
    for (let i = 0; i < 2000; i++) {
      const elems = Array.from({ length: randInt(r, 1, 5) }, () => {
        let s = '';
        for (let k = randInt(r, 1, 8); k > 0; k--) s += pick(r, alphabet);
        return s.trim() || 'x';
      });
      const marked = randInt(r, 0, elems.length - 1);
      const enc = elems.map((e, j) => escapeElement(e, ',') + (j === marked ? '*' : '')).join(',');
      const toks = splitFields(enc, ',', 1);
      assert.equal(toks.length, 1);
      const parsed = splitList(toks[0], ',');
      assert.deepEqual(parsed.map(p => p[0]), elems, enc);
      assert.deepEqual(parsed.map((p, j) => (p[1] ? j : -1)).filter(j => j >= 0), [marked]);
    }
  });

  test('barra invertida final es E09; sobre-escapar es inocuo', () => {
    assert.throws(() => tokenize('abc' + BS, ',', 3), (e: unknown) => e instanceof MiniError && e.code === 'E09' && e.line === 3);
    assert.equal(textOf(splitFields('Si 3x+6=18' + BS + ', x?', ',', 1)[0]), 'Si 3x+6=18, x?');
  });

  test('formatNumber coincide con la referencia', () => {
    // pares [valor, texto] obtenidos de minifmt.values.format_number
    const table: [number, string][] = [
      [0, '0'], [3, '3'], [-2.5, '-2.5'], [0.1 + 0.2, '0.30000000000000004'], [1e-7, '0.0000001'],
      [1.5e-5, '0.000015'], [1 / 65536, '1.52587890625e-05'], [123456789.125, '123456789.125'],
      [1e15, '1000000000000000.0'], [1e16, '10000000000000000'], [1e21, '1000000000000000000000'],
      [1e22, '10000000000000000000000'], [1.2345e-10, '0.00000000012345'], [1.23456789e-10, '1.23456789e-10'],
      [2.5e-300, '2.5e-300'], [123456789012345678, '123456789012345680'], [-1e-5, '-0.00001'], [5e-324, '5e-324'],
      [0.3, '0.3'], [100, '100'], [1e-4, '0.0001'], [1.234e-4, '0.0001234'],
    ];
    for (const [v, s] of table) assert.equal(formatNumber(v), s, String(v));
    assert.equal(formatNumber(1.7976931348623157e308).length, 309);
  });
});
