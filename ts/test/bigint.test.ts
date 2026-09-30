/* bigint.test.ts — documenta el comportamiento ACTUAL con enteros fuera de ±2^53 (auditoría V5).
 *
 * La SPEC (§4, §6) define `int` como `-?[0-9]+` sin precisión máxima, y la referencia Python es exacta;
 * TypeScript usa números de JavaScript y pierde precisión SIN error ni aviso. Arreglarlo exige una
 * decisión de norma o un cambio de API pública (ver docs/adr/0018-enteros-grandes-en-typescript.md,
 * estado «Propuesta»), así que estas pruebas fijan lo que hoy ocurre para que cualquier cambio sea
 * deliberado: si se adopta la propuesta, estas pruebas deben cambiar junto con la norma.
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { dumps, normalizeContract, parse } from '../src/index.ts';

const C = normalizeContract({ prefix: 'bi', records_key: 'rows', core: [{ name: 'id', type: 'int' }], extensions: [{ name: 'ref', type: 'decimal' }] });

describe('enteros fuera de ±2^53 (comportamiento documentado, no normativo)', () => {
  test('dentro de ±2^53 - 1 la ida y vuelta es exacta', () => {
    for (const v of [0, 1, -1, 9007199254740991, -9007199254740991]) {
      const text = dumps({ prefix: 'bi', header: { n: 1 }, rows: [{ id: v }] }, C);
      assert.equal(parse(text, C).toCanonical().rows[0].id, v);
    }
  });

  test('2^53 + 1 se redondea al par más cercano al leer, sin error ni aviso', () => {
    const doc = parse('bi|n=1\n9007199254740993', C);
    assert.deepEqual(doc.errors, []);
    assert.equal(doc.records[0].id, 9007199254740992); // Python devuelve 9007199254740993
  });

  test('un entero de 30 dígitos se convierte en un número aproximado, sin error', () => {
    const doc = parse('bi|n=1\n123456789012345678901234567890', C);
    assert.deepEqual(doc.errors, []);
    assert.equal(doc.records[0].id, 1.2345678901234568e29);
  });

  test('la escritura de un entero mayor que 2^53 tampoco es exacta: 2^60 sale como 1152921504606847000', () => {
    const text = dumps({ prefix: 'bi', header: { n: 1 }, rows: [{ id: 2 ** 60 }] }, C);
    // String(2 ** 60) usa la representación más corta que identifica el double, no sus dígitos exactos
    // (2^60 = 1152921504606846976): el valor escrito NO es el valor entregado y no hay aviso.
    assert.equal(text, 'bi|n=1\n1152921504606847000');
    assert.notEqual(text.split('\n')[1], String(2n ** 60n));
  });

  test('`decimal` es la vía exacta: conserva todos los dígitos como cadena', () => {
    const doc = parse('bi|n=1\n1|123456789012345678901234567890', C);
    assert.deepEqual(doc.errors, []);
    assert.equal(doc.records[0].ref, '123456789012345678901234567890');
  });
});
