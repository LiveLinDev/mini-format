/* truncation.test.ts — salidas truncadas: recuperación parcial y detección del registro incompleto.
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { createReader, parse } from '../src/index.ts';
import { ALL, LF, REG, chunk, lf, rng } from './helpers.ts';

describe('truncamiento', () => {
  for (const fx of ALL) {
    const c = fx.contract;
    test(`familia ${c.prefix}: corte en cada posición`, () => {
      const full = lf(fx.valid).replace(/\n$/, '');
      const reference = parse(full, c).records;
      const r = rng(0xbeef + c.prefix.charCodeAt(0));
      const headerEnd = full.indexOf(LF);
      for (let cut = headerEnd + 1; cut < full.length; cut++) {
        const text = full.slice(0, cut);
        const reader = createReader(c);
        for (const p of chunk(text, r)) reader.push(p);
        const res = reader.end();
        const ctx = `${c.prefix} cut=${cut}`;
        // el documento del lector coincide con el análisis tolerante del mismo texto
        assert.deepEqual(res.document.records, parse(text, c, { strict: false }).records, ctx);
        // todo registro completo (línea cerrada con LF) es idéntico al original
        const closed = text.slice(0, text.lastIndexOf(LF)).split(LF).length - 1;
        for (let i = 0; i < closed; i++) assert.deepEqual(res.records[i], reference[i], ctx);
        // el truncamiento siempre queda señalado: registro incompleto, faltan líneas o no terminó en LF
        assert.ok(res.truncated || !res.terminated, ctx);
        assert.equal(res.complete && res.terminated, false, ctx);
        if (text.endsWith(LF)) {
          assert.equal(res.terminated, true, ctx);
          assert.equal(res.incomplete, null, ctx);
          assert.equal(res.missing, reference.length - closed, ctx);
        } else {
          assert.equal(res.terminated, false, ctx);
          assert.equal(res.received, closed + 1, ctx);
          if (res.incomplete) {
            assert.equal(res.incomplete.line, closed + 2, ctx);
            assert.equal(res.incomplete.text, text.slice(text.lastIndexOf(LF) + 1), ctx);
            assert.equal(res.incomplete.isHeader, false, ctx);
            assert.ok(res.incomplete.errors.length > 0, ctx);
            assert.equal(res.records.length, closed, ctx);
          }
        }
      }
    });
  }

  test('ejemplo: respuesta cortada a mitad del tercer registro', () => {
    const A = REG.get('a');
    const lines = lf(ALL[0].valid).split(LF);
    const text = [lines[0], lines[1], lines[2], lines[3].slice(0, 40)].join(LF);
    const reader = createReader(A);
    reader.push(text);
    const res = reader.end();
    assert.equal(res.valid, 2);
    assert.equal(res.expected, 12);
    assert.equal(res.received, 3);
    assert.equal(res.missing, 9);
    assert.equal(res.truncated, true);
    assert.ok(res.incomplete);
    assert.equal(res.incomplete.line, 4);
    assert.equal(res.incomplete.fieldsSeen, 4);
    assert.deepEqual(res.incomplete.errors.map(e => e.code), ['E05']);
    assert.deepEqual(res.errors.map(e => e.code), ['E05', 'E04']);
  });

  test('cabecera truncada sin LF', () => {
    const A = REG.get('a');
    const reader = createReader(A);
    reader.push('a|n=12|bd=1,x');
    const res = reader.end();
    assert.ok(res.incomplete);
    assert.equal(res.incomplete.isHeader, true);
    assert.deepEqual(res.incomplete.errors.map(e => e.code), ['E06']);
    assert.equal(res.missing, 12);
  });

  test('escape colgante al final del fragmento se resuelve con el siguiente', () => {
    const A = REG.get('a');
    const text = lf(ALL[0].valid);
    const at = text.indexOf('\\,') + 1;
    assert.ok(at > 0);
    const reader = createReader(A);
    reader.push(text.slice(0, at));
    reader.push(text.slice(at));
    const res = reader.end();
    assert.equal(res.complete, true);
    assert.equal(res.records.length, 12);
  });
});
