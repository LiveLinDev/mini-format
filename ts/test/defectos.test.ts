/* defectos.test.ts — defectos del núcleo corregidos tras la auditoría V5 (D-3, D-6, D-7).
 * Las expectativas están escritas a mano desde la SPEC (§6: un campo `unique` no puede repetirse),
 * y replican tests/test_nucleo_reparacion.py de la referencia Python.
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { createReader, dumps, mergeRepair, normalizeContract, parse, readRecords, repairRequest, specBlock } from '../src/index.ts';
import { REG, rng } from './helpers.ts';

const CLS = REG.get('cls');
const TAIL = '|question*,feedback,bug,request,praise,other|0.9|';
const rec = (i: number, text = 'texto'): string => `m${i}|${text}${TAIL}`;
const ROTA = 'm2|registro roto sin campos suficientes';
const DOC = ['cls|n=3|k=6', rec(1), ROTA, rec(3, 'tercero')].join('\n'); // la línea 3 es la inválida
const merge = (answer: string, doc: string = DOC) => mergeRepair(doc, answer, CLS, repairRequest(doc, CLS, 'es'));
const ids = (m: ReturnType<typeof merge>): unknown[] => (m.document as NonNullable<typeof m.document>).records.map(r => r.id);

describe('D-3: una corrección no puede quitarle a otro registro válido el valor `unique`', () => {
  test('la solicitud pide solo la línea rota', () => {
    assert.deepEqual(repairRequest(DOC, CLS, 'es').items.map(it => it.line), [3]);
  });

  test('repetir el id de un válido posterior: queda sin resolver y nada se pierde', () => {
    const m = merge('cls|n=1\n' + rec(3, 'corregido'));
    assert.deepEqual(m.replaced, []);
    assert.deepEqual(m.unresolved, [3]);
    assert.equal(m.text, DOC);
    assert.deepEqual(ids(m), ['m1', 'm3']);
    assert.ok(m.notes.some(n => n.includes('unique')));
  });

  test('repetir el id de un válido anterior: queda sin resolver', () => {
    const m = merge('cls|n=1\n' + rec(1, 'corregido'));
    assert.deepEqual([m.replaced, m.unresolved], [[], [3]]);
    assert.equal(m.text, DOC);
  });

  test('un id nuevo se acepta', () => {
    const m = merge('cls|n=1\n' + rec(9, 'corregido'));
    assert.deepEqual([m.replaced, m.unresolved], [[3], []]);
    assert.equal(m.ok, true);
    assert.deepEqual(ids(m), ['m1', 'm9', 'm3']);
  });

  test('la línea corregida puede conservar su propio id', () => {
    const m = merge('cls|n=1\n' + rec(2, 'corregido'));
    assert.deepEqual([m.replaced, m.unresolved], [[3], []]);
    assert.equal(m.ok, true);
  });

  test('dos correcciones no pueden reclamar el mismo id nuevo', () => {
    const doc = ['cls|n=4|k=6', rec(1), ROTA, 'otra línea rota', rec(4)].join('\n');
    const m = merge('cls|n=2\n' + rec(9, 'uno') + '\n' + rec(9, 'dos'), doc);
    assert.deepEqual([m.replaced, m.unresolved], [[3], [4]]);
    assert.deepEqual(ids(m), ['m1', 'm9', 'm4']);
  });

  test('invariante (semilla fija): ningún registro válido del original sale del documento', () => {
    const r = rng(20260930);
    const pool = [1, 2, 3, 4, 5, 6, 7].flatMap(i => [rec(i, 't0'), rec(i, 't1')]).concat(['-', 'basura', 'm1|x']);
    for (let iter = 0; iter < 300; iter++) {
      const pickIds = [1, 2, 3, 4, 5, 6, 7, 8].sort(() => r() - 0.5).slice(0, 3 + Math.floor(r() * 4));
      const lines = pickIds.map(i => rec(i));
      const broken = new Set<number>();
      for (let k = 0; k < 1 + Math.floor(r() * 2); k++) broken.add(Math.floor(r() * lines.length));
      for (const b of broken) lines[b] = 'roto' + b;
      const doc = [`cls|n=${lines.length}|k=6`, ...lines].join('\n');
      const req = repairRequest(doc, CLS, 'es');
      const answer = [`cls|n=${req.items.length}`, ...req.items.map(() => pool[Math.floor(r() * pool.length)])].join('\n');
      const m = mergeRepair(doc, answer, CLS, req);
      const after = new Set((m.document as NonNullable<typeof m.document>).records.map(x => `${x.id}/${x.text}`));
      pickIds.forEach((id, i) => {
        if (!broken.has(i)) assert.ok(after.has(`m${id}/texto`), `registro válido m${id} perdido\n${doc}\n---\n${answer}`);
      });
    }
  });
});

describe('D-6: `max: 0` de una lista no se describe como «sin límite»', () => {
  const c = normalizeContract({ prefix: 'z', core: [{ name: 'id', type: 'str' }, { name: 'tags', type: 'list', item: 'str', optional: true, min: 0, max: 0 }] });
  test('max 0 se imprime como 0', () => {
    assert.ok(specBlock(c, 'en').includes('0 to 0 elements'));
    assert.ok(specBlock(c, 'es').includes('entre 0 y 0 elementos'));
    assert.ok(!(specBlock(c, 'en') + specBlock(c, 'es')).includes('∞'));
  });
  test('sin max sigue siendo ilimitado', () => {
    const open = normalizeContract({ prefix: 'z', core: [{ name: 'id', type: 'str' }, { name: 'tags', type: 'list', item: 'str', min: 1 }] });
    assert.ok(specBlock(open, 'en').includes('1 to ∞ elements'));
  });
});

describe('D-7: ReaderResult.finalRecords (registro final sin LF)', () => {
  const A = REG.get('a');
  const valid = ['a|n=2', 'i1|L1|Bio|¿p?|x*,y,z,w|0.9,-1,0.25|1|b,0.2,low', 'i2|L2|Qui|¿q?|x*,y,z,w|0.9,-1,0.25|1|b,0.2,low'].join('\n');

  test('el último registro sin LF llega en finalRecords y no en push()', () => {
    const reader = createReader(A);
    const pushed = reader.push(valid);
    assert.equal(pushed.length, 1);
    const res = reader.end();
    assert.equal(res.finalRecords.length, 1);
    assert.equal(res.finalRecords[0].record.id, 'i2');
    assert.equal(res.finalRecords[0].line, 3);
    assert.equal(res.finalRecords[0].index, 1);
    assert.equal(res.valid, 2);
  });

  test('con LF final no hay registros finales', () => {
    const reader = createReader(A);
    reader.push(valid + '\n');
    assert.deepEqual(reader.end().finalRecords, []);
  });

  test('readRecords entrega también el último registro sin LF', async () => {
    async function* gen() { yield valid.slice(0, 40); yield valid.slice(40); }
    const got: unknown[] = [];
    const it = readRecords(gen(), A);
    let step = await it.next();
    while (!step.done) { got.push(step.value.record.id); step = await it.next(); }
    assert.deepEqual(got, ['i1', 'i2']);
    assert.equal(step.value.finalRecords.length, 1);
  });
});

// ---------------------------------------------------------------------------------------------
// ADR 0017 (Propuesta, no vigente): B-1 conjunto de blancos y D-1/D-2/D-4 como pruebas «todo».
// ---------------------------------------------------------------------------------------------
const WS = normalizeContract({
  prefix: 'p', records_key: 'rows',
  core: [{ name: 'id', type: 'str' }],
  extensions: [
    { name: 'ls', type: 'list', item: 'str' },
    { name: 'dec', type: 'decimal' },
  ],
});
const TRIMMED = [0x09, 0x0b, 0x0c, 0x0d, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x85, 0xa0, 0x1680,
  0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200a,
  0x2028, 0x2029, 0x202f, 0x205f, 0x3000];
const NOT_TRIMMED = [0x200b, 0x200c, 0x200d, 0x2060, 0xfeff, 0x180e, 0x86, 0xad, 0x2800, 0x3164];

describe('B-1 (ADR 0017): conjunto de blancos que recorta hoy la biblioteca (no normativo; igual que Python)', () => {
  const valueOf = (cp: number): unknown => {
    const ch = String.fromCodePoint(cp);
    return parse('p|n=1\n' + ch + 'x' + ch, WS, { strict: false }).records[0].id;
  };
  test('los caracteres de la lista se recortan en ambos extremos de un campo', () => {
    for (const cp of TRIMMED) assert.equal(valueOf(cp), 'x', `U+${cp.toString(16)}`);
  });
  test('los caracteres vecinos que no son espacio se conservan', () => {
    for (const cp of NOT_TRIMMED) {
      const ch = String.fromCodePoint(cp);
      assert.equal(valueOf(cp), ch + 'x' + ch, `U+${cp.toString(16)}`);
    }
  });
});

describe('D-1, D-2 y D-4 (ADR 0017, propuesta): lo que SPEC §9 exige y hoy no se cumple', () => {
  const back = (rec: Record<string, unknown>): Record<string, unknown> =>
    parse(dumps({ prefix: 'p', header: { n: 1 }, rows: [{ id: 'a', ...rec }] }, WS), WS).records[0];
  test('D-1: el espacio exterior de una cadena sobrevive a la ida y vuelta', { todo: 'ADR 0017' }, () => {
    assert.equal(back({ id: ' a' }).id, ' a');
    assert.equal(back({ id: 'hola ' }).id, 'hola ');
  });
  test('D-2: un elemento de lista con espacio antes de la comilla se puede escribir', { todo: 'ADR 0017' }, () => {
    assert.deepEqual(back({ ls: [' "a'] }).ls, [' "a']);
  });
  test('D-4: el texto emitido para un decimal no canónico es estable', { todo: 'ADR 0017' }, () => {
    const text = dumps({ prefix: 'p', header: { n: 1 }, rows: [{ id: 'a', dec: '007.50' }] }, WS);
    assert.equal(dumps(parse(text, WS).toCanonical(), WS), text);
  });
});
