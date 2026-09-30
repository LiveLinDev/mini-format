/* esquema_ramas.test.ts — V5 (N6): ramas de fromJsonSchema/fromZod que las pruebas de Zod no ejercen.
 * Las expectativas salen de la semántica de JSON Schema y de SPEC §6/§12 (qué se representa y qué es E20), no del código.
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { MiniError, fromJsonSchema, fromZod, normalizeContract } from '../src/index.ts';
import type { FieldJSON, JsonSchema } from '../src/index.ts';

const reg = (props: Record<string, unknown>, extra: JsonSchema = {}): JsonSchema => ({ type: 'object', properties: props, ...extra });
const one = (schema: unknown, required = true, opts: Record<string, unknown> = {}): FieldJSON => {
  const json = fromJsonSchema(reg({ x: schema }, required ? { required: ['x'] } : {}), { prefix: 'p', ...opts });
  return json.core[0];
};
const rechaza = (schema: JsonSchema, opts: Record<string, unknown> = {}): MiniError => {
  try {
    fromJsonSchema(schema, { prefix: 'p', ...opts });
  } catch (e) {
    assert.ok(e instanceof MiniError, String(e));
    assert.equal(e.code, 'E20');
    return e;
  }
  return assert.fail('se esperaba E20');
};

describe('variantes nulas y uniones', () => {
  test('anyOf/oneOf con una variante nula: campo opcional del tipo no nulo', () => {
    for (const key of ['anyOf', 'oneOf']) {
      const f = one({ [key]: [{ type: 'integer', minimum: 1 }, { type: 'null' }] });
      assert.deepEqual([f.type, f.min, f.optional], ['int', 1, true], key);
    }
  });
  test('type [X, null] y enum con null son anulables', () => {
    assert.equal(one({ type: ['string', 'null'] }).optional, true);
    const f = one({ enum: ['a', 'b', null] });
    assert.deepEqual([f.type, f.values, f.optional], ['enum', ['a', 'b'], true]);
    assert.equal(one({ type: 'string', enum: ['a', null] }).optional, true);
  });
  test('uniones no representables (SPEC §12)', () => {
    for (const s of [
      { anyOf: [{ type: 'string' }, { type: 'integer' }] },
      { oneOf: [{ type: 'string' }, { type: 'integer' }, { type: 'null' }] },
      { type: ['string', 'integer'] },
      { type: ['string', 'integer', 'null'] },
      { anyOf: [{ type: 'string' }, true] },
    ]) rechaza(reg({ x: s }));
  });
  test('esquema booleano o vacío como propiedad', () => {
    rechaza(reg({ x: true }));
    rechaza(reg({ x: {} }));
  });
});

describe('números y límites', () => {
  test('exclusiveMinimum/Maximum de un entero se convierten en min y max', () => {
    const f = one({ type: 'integer', exclusiveMinimum: 0, exclusiveMaximum: 10 });
    assert.deepEqual([f.min, f.max], [1, 9]);
    const g = one({ type: 'integer', minimum: 5, exclusiveMinimum: 2, maximum: 3, exclusiveMaximum: 100 });
    assert.deepEqual([g.min, g.max], [5, 3], 'se conserva el límite más estricto de cada extremo');
  });
  test('exclusiveMinimum/Maximum de un número es una restricción que .mini no valida', () => {
    const e = rechaza(reg({ x: { type: 'number', exclusiveMinimum: 0 } }));
    assert.ok(e.message.includes('exclusiveMinimum'));
    rechaza(reg({ x: { type: 'number', exclusiveMaximum: 1 } }));
    const avisos: string[] = [];
    const f = one({ type: 'number', exclusiveMinimum: 0, exclusiveMaximum: 1 }, true, { unsupported: 'ignore', warnings: avisos });
    assert.equal(f.type, 'float');
    assert.equal(avisos.length, 2);
  });
  test('los límites centinela de entero seguro no se copian al contrato', () => {
    const f = one({ type: 'integer', minimum: -9007199254740991, maximum: 9007199254740991 });
    assert.equal(f.min, undefined);
    assert.equal(f.max, undefined);
  });
  test('límites de número y de entero dentro de una lista no son representables', () => {
    rechaza(reg({ x: { type: 'array', items: { type: 'integer', minimum: 0 } } }));
    rechaza(reg({ x: { type: 'array', items: { type: 'integer', maximum: 9 } } }));
  });
});

describe('date, decimal, enumeraciones y escalares', () => {
  test('date y decimal con límites por formatMinimum/formatMaximum o x-mini', () => {
    const d = one({ type: 'string', format: 'date', formatMinimum: '2000-01-01', formatMaximum: '2099-12-31' });
    assert.deepEqual([d.type, d.min, d.max], ['date', '2000-01-01', '2099-12-31']);
    const m = one({ type: 'string', 'x-mini': { type: 'decimal', min: '0', max: 100 } });
    assert.deepEqual([m.type, m.min, m.max], ['decimal', '0', 100]);
    assert.equal(one({ type: 'string', format: 'decimal' }).type, 'decimal');
  });
  test('un límite que no es texto ni número es inválido; en una lista no es representable', () => {
    rechaza(reg({ x: { type: 'string', format: 'date', formatMinimum: true } }));
    rechaza(reg({ x: { type: 'array', items: { type: 'string', format: 'date', formatMinimum: '2000-01-01' } } }));
    rechaza(reg({ x: { type: 'array', items: { type: 'string', format: 'decimal', formatMaximum: '9' } } }));
  });
  test('enumeraciones: const es una enumeración de un valor; solo se admiten textos', () => {
    const f = one({ const: 'fijo' });
    assert.deepEqual([f.type, f.values], ['enum', ['fijo']]);
    assert.deepEqual(one({ enum: ['a', 'a', 'b'] }).values, ['a', 'b']);
    rechaza(reg({ x: { enum: [1, 2] } }));
    rechaza(reg({ x: { enum: [] } }));
  });
  test('tipos que no se representan', () => {
    for (const s of [{}, { type: 'object' }, { type: 'array', items: { type: 'array', items: { type: 'string' } } },
      { type: 'null' }, { description: 'sin tipo' }]) rechaza(reg({ x: s }));
    rechaza(reg({ x: { type: 'array' } }));
    rechaza(reg({ x: { type: 'array', items: true } }));
    rechaza(reg({ x: { type: 'array', items: { type: ['string', 'null'] } } }));
  });
  test('palabras clave que no se validan: error por omisión, aviso con unsupported ignore', () => {
    for (const s of [{ type: 'string', minLength: 1 }, { type: 'string', pattern: 'a' }, { type: 'boolean', const2: 1 },
      { type: 'integer', multipleOf: 2 }, { type: 'string', properties: {} }, { type: 'array', items: { type: 'string' }, uniqueItems: true },
      { type: 'string', allOf: [] }, { type: 'string', not: {} }]) rechaza(reg({ x: s }));
    const avisos: string[] = [];
    one({ type: 'string', minLength: 1, pattern: 'a' }, true, { unsupported: 'ignore', warnings: avisos });
    assert.equal(avisos.length, 2);
  });
});

describe('listas, valores por omisión y descripciones', () => {
  test('lista con minItems, maxItems y enumeración de elementos', () => {
    const f = one({ type: 'array', items: { enum: ['u', 'v'] }, minItems: 1, maxItems: 3 });
    assert.deepEqual([f.type, f.item, f.item_values, f.min, f.max], ['list', 'enum', ['u', 'v'], 1, 3]);
  });
  test('default hace opcional el campo y se copia; la descripción puede estar en la variante', () => {
    const f = one({ type: 'string', default: 'es', description: 'idioma' });
    assert.deepEqual([f.optional, f.default, f.desc], [true, 'es', 'idioma']);
    const g = one({ anyOf: [{ type: 'string', description: 'texto', default: 'x' }, { type: 'null' }] });
    assert.deepEqual([g.optional, g.default, g.desc], [true, 'x', 'texto']);
  });
  test('campo no requerido es opcional; requerido no lo es', () => {
    assert.equal(one({ type: 'string' }, false).optional, true);
    assert.equal(one({ type: 'string' }, true).optional, undefined);
  });
});

describe('raíz y opciones', () => {
  test('raíz: lista de registros, título y descripción como nombre y descripción', () => {
    const json = fromJsonSchema({ type: 'array', items: { type: 'object', title: 'Nombre', description: 'Desc', properties: { a: { type: 'string' } } } },
      { prefix: 'p' });
    assert.deepEqual([json.name, json.description, json.records_key, json.list_separator, json.version], ['Nombre', 'Desc', 'records', ',', 1]);
  });
  test('las opciones sustituyen a los valores del esquema', () => {
    const json = fromJsonSchema(reg({ a: { type: 'string' }, b: { type: 'integer' } }, { title: 'T', required: ['a'] }), {
      prefix: 'p', name: 'N', description: 'D', version: 3, records_key: 'rows', list_separator: ';', domain: 'dom',
      unique: ['a'], header: { required: ['n', 'src'], keys: { src: { type: 'str' } } },
    });
    assert.deepEqual([json.name, json.description, json.version, json.records_key, json.list_separator, json.domain],
      ['N', 'D', 3, 'rows', ';', 'dom']);
    assert.equal(json.core[0].unique, true);
    assert.equal(normalizeContract(json).headerKeys.src.required, true);
  });
  test('raíz inválida o sin propiedades', () => {
    rechaza({ type: 'string' });
    rechaza({ type: 'object' });
    rechaza({ type: 'object', properties: {} });
    rechaza({ type: 'array', items: { type: 'string' } });
    rechaza(reg({ a: { type: 'string' } }, { additionalProperties: true }));
    rechaza(reg({ a: { type: 'string' } }, { minProperties: 1 }));
    rechaza(reg({ a: { type: 'string' } }), { unique: ['no_existe'] });
    assert.throws(() => fromJsonSchema(reg({ a: { type: 'string' } }), {} as never), MiniError);
  });
  test('additionalProperties false es admisible', () => {
    assert.equal(fromJsonSchema(reg({ a: { type: 'string' } }, { additionalProperties: false }), { prefix: 'p' }).core.length, 1);
  });
});

describe('fromZod sin Zod: conversor inyectado y errores', () => {
  const plano = { type: 'object', properties: { a: { type: 'string' } }, required: ['a'] };
  test('usa options.toJSONSchema, o el método del esquema, y rechaza un esquema sin ninguno', () => {
    let recibido: unknown;
    const c1 = fromZod({}, { prefix: 'p', toJSONSchema: ((_s: unknown, params: unknown) => { recibido = params; return plano; }) as never });
    assert.equal(c1.core[0].name, 'a');
    assert.deepEqual(recibido, { io: 'input', unrepresentable: 'any', target: 'draft-2020-12' });
    assert.equal(fromZod({ toJSONSchema: () => plano }, { prefix: 'p' }).core[0].name, 'a');
    assert.throws(() => fromZod({}, { prefix: 'p' }), (e: unknown) => e instanceof MiniError && e.code === 'E20');
    assert.throws(() => fromZod({ toJSONSchema: () => 'no es un objeto' }, { prefix: 'p' }), (e: unknown) => e instanceof MiniError && e.code === 'E20');
  });
});
