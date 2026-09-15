/* stream.test.ts — lector incremental: fragmentos aleatorios de 1–7 caracteres dan el mismo resultado que parse.
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { MiniValidationError, createReader, parse, readRecords } from '../src/index.ts';
import type { Contract, Document, MiniRecord, ReaderResult } from '../src/index.ts';
import { ALL, BOM, CR, LF, REG, chunk, errKeys, lf, mutate, rng } from './helpers.ts';

function assertSameDocument(got: Document, want: Document, ctx: string): void {
  assert.equal(got.prefix, want.prefix, ctx);
  assert.equal(got.version, want.version, ctx);
  assert.equal(got.lines, want.lines, ctx);
  assert.deepEqual(got.header, want.header, ctx);
  assert.deepEqual(got.records, want.records, ctx);
  assert.deepEqual(errKeys(got.errors), errKeys(want.errors), ctx);
  assert.deepEqual(got.toCanonical(), want.toCanonical(), ctx);
}

function streamParse(text: string, c: Contract, pieces: string[]): { result: ReaderResult; emitted: MiniRecord[]; pushed: MiniRecord[] } {
  const emitted: MiniRecord[] = [];
  const pushed: MiniRecord[] = [];
  const reader = createReader(c, { onRecord: r => emitted.push(r.record) });
  for (const p of pieces) for (const r of reader.push(p)) pushed.push(r.record);
  const result = reader.end();
  return { result, emitted, pushed };
}

/** Corpus por familia: fixtures, variantes CRLF/BOM y 25 mutaciones aleatorias. */
function corpus(fx: (typeof ALL)[number], r: () => number): string[] {
  const base = [fx.valid, lf(fx.valid), ...(fx.escaping ? [fx.escaping] : []), ...fx.bad.map(b => b.text)];
  const docs = [...base, BOM + lf(fx.valid).split(LF).join(CR + LF), lf(fx.valid).replace(/\n$/, ''), '', LF + LF];
  for (let i = 0; i < 25; i++) docs.push(mutate(lf(base[i % base.length]), r));
  return docs;
}

describe('streaming con fragmentos aleatorios de 1–7 caracteres', () => {
  for (const fx of ALL) {
    const c = fx.contract;
    test(`familia ${c.prefix}`, () => {
      const r = rng(0xc0ffee + c.prefix.charCodeAt(0) * 31 + c.prefix.length);
      for (const text of corpus(fx, r)) {
        const want = parse(text, c, { strict: false });
        for (let rep = 0; rep < 5; rep++) {
          const pieces = chunk(text, r);
          assert.equal(pieces.join(''), text);
          const { result, emitted, pushed } = streamParse(text, c, pieces);
          const ctx = `${c.prefix}: ${JSON.stringify(pieces).slice(0, 200)}`;
          assertSameDocument(result.document, want, ctx);
          assert.deepEqual(emitted, want.records, ctx);
          // lo emitido durante push() es un prefijo de los registros finales
          assert.deepEqual(pushed, want.records.slice(0, pushed.length), ctx);
          assert.equal(result.complete, want.errors.length === 0, ctx);
        }
        // modo estricto: mismo resultado que parse estricto
        let strictParse: unknown = null;
        let strictDoc: Document | null = null;
        try { strictDoc = parse(text, c); } catch (e) { strictParse = e; }
        const reader = createReader(c, { strict: true });
        for (const p of chunk(text, r)) reader.push(p);
        if (strictParse) {
          assert.throws(() => reader.end(), (e: unknown) => {
            assert.ok(e instanceof MiniValidationError);
            assert.deepEqual(errKeys(e.errors), errKeys((strictParse as MiniValidationError).errors));
            return true;
          });
        } else {
          assertSameDocument(reader.end().document, strictDoc as Document, c.prefix);
        }
      }
    });
  }

  test('fragmentos de bytes UTF-8 partidos a mitad de carácter', () => {
    const r = rng(99);
    const enc = new TextEncoder();
    for (const fx of ALL) {
      const text = fx.valid;
      const bytes = enc.encode(text);
      const reader = createReader(fx.contract);
      let i = 0;
      while (i < bytes.length) {
        const k = 1 + Math.floor(r() * 7);
        reader.push(bytes.subarray(i, i + k));
        i += k;
      }
      assertSameDocument(reader.end().document, parse(text, fx.contract, { strict: false }), fx.contract.prefix);
    }
  });

  test('registros emitidos en cuanto se cierra la línea; cabecera y progreso', () => {
    const A = REG.get('a');
    const text = lf(ALL[0].valid);
    const lines = text.split(LF);
    const headers: string[] = [];
    const reader = createReader(A, { onHeader: h => headers.push(h.prefix) });
    assert.equal(reader.header, null);
    assert.deepEqual(reader.push(lines[0]), []);
    assert.equal(reader.header, null);
    assert.deepEqual(reader.push(LF), []);
    assert.deepEqual(headers, ['a']);
    assert.equal(reader.progress.expected, 12);
    const half = lines[1].slice(0, 20);
    assert.deepEqual(reader.push(half), []);
    assert.equal(reader.pending, half);
    const got = reader.push(lines[1].slice(20) + LF);
    assert.equal(got.length, 1);
    assert.equal(got[0].line, 2);
    assert.equal(got[0].index, 0);
    assert.equal(got[0].record.id, 'i1');
    assert.deepEqual(reader.progress, { expected: 12, received: 1, valid: 1, errors: 0 });
    for (const l of lines.slice(2)) reader.push(l + LF);
    const res = reader.end();
    assert.equal(res.complete, true);
    assert.equal(res.truncated, false);
    assert.equal(res.received, 12);
    assert.equal(res.missing, 0);
    assert.throws(() => reader.push('x'));
  });

  test('onError recibe cada error una vez, incluido E04 al final', () => {
    const A = REG.get('a');
    const text = lf(ALL[0].valid).replace('cloroplastos*', 'cloroplastos').replace('n=12', 'n=13');
    const seen: string[] = [];
    const reader = createReader(A, { onError: e => seen.push(e.code) });
    for (const p of chunk(text, rng(5))) reader.push(p);
    const res = reader.end();
    assert.deepEqual(seen, ['E08', 'E04']);
    assert.deepEqual(res.errors.map(e => e.code), ['E08', 'E04']);
  });

  test('readRecords sobre un iterable asíncrono', async () => {
    const fx = ALL[0];
    async function* gen() {
      for (const p of chunk(fx.valid, rng(3))) yield p;
    }
    const it = readRecords(gen(), fx.contract);
    const ids: unknown[] = [];
    let step = await it.next();
    while (!step.done) {
      ids.push(step.value.record.id);
      step = await it.next();
    }
    assert.equal(ids.length, 12);
    assert.equal(step.value.complete, true);
  });

  test('flujo vacío: E01', () => {
    const res = createReader(REG.get('a')).end();
    assert.deepEqual(res.errors.map(e => e.code), ['E01']);
    assert.equal(res.expected, null);
    assert.equal(res.terminated, true);
  });
});
