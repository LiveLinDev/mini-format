/* schema.test.ts — HU14: contrato .mini desde un esquema Zod (vía JSON Schema).
 * Zod es devDependency: sin `npm install` en ts/ las pruebas con Zod se omiten.
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  MiniError, Registry, checkFork, dumps, encodeRecord, fromJsonSchema, fromZod, normalizeContract, parse, roundtripOk,
  specBlock,
} from '../src/index.ts';
import type { Contract, ContractJSON } from '../src/index.ts';

type Zod = typeof import('zod');
let z: Zod['z'] | null = null;
try {
  z = (await import('zod')).z;
} catch {
  z = null;
}
const skip = z ? false : 'zod no está instalado (npm install en ts/)';

/** Invariantes verificables de un contrato aislado: normalización, I2 (n obligatorio), registro sin violaciones. */
function assertInvariants(json: ContractJSON): Contract {
  const c = normalizeContract(json);
  assert.equal(c.headerKeys.n.required, true, 'I2: n obligatorio');
  const reg = Registry.from([c]);
  assert.deepEqual(reg.check(), []);
  assert.deepEqual(checkFork(c, c), [], 'I3/I4 respecto de sí mismo');
  assert.ok(specBlock(c, 'es').includes(`familia '${c.prefix}'`));
  return c;
}

/** Documento .mini de una sola línea de registro, escrita a mano. */
function oneLine(c: Contract, line: string): string {
  return `${c.prefix}|n=1\n${line}`;
}

/** Salida de .mini -> entrada Zod: un campo vacío es null; en campos solo opcionales (no anulables) se omite. */
function toZodInput(rec: Record<string, unknown>, nullable: Set<string>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(rec)) if (!(v === null && !nullable.has(k))) out[k] = v;
  return out;
}

function codes(c: Contract, text: string): string[] {
  return parse(text, c, { strict: false }).errors.map(e => e.code);
}

describe('HU14: contrato desde Zod', { skip }, () => {
  test('esquema plano con todos los tipos representables', () => {
    const Z = z!;
    const Ticket = Z.object({
      id: Z.string().describe('identificador'),
      prioridad: Z.number().int().min(1).max(5),
      puntaje: Z.number().min(0).max(1),
      urgente: Z.boolean(),
      estado: Z.enum(['abierto', 'cerrado', 'pendiente']),
      etiquetas: Z.array(Z.string()).min(1).max(4),
      medidas: Z.array(Z.number()),
      niveles: Z.array(Z.enum(['bajo', 'alto'])),
      nota: Z.string().optional(),
      horas: Z.number().nullable(),
      canal: Z.literal('web'),
      activo: Z.boolean().default(true),
    });
    const json = fromZod(Ticket, { prefix: 'tk', name: 'tickets', unique: ['id'] });
    const c = assertInvariants(json);
    assert.deepEqual(c.fields.map(f => [f.name, f.type, f.optional]), [
      ['id', 'str', false], ['prioridad', 'int', false], ['puntaje', 'float', false], ['urgente', 'bool', false],
      ['estado', 'enum', false], ['etiquetas', 'list', false], ['medidas', 'list', false], ['niveles', 'list', false],
      ['nota', 'str', true], ['horas', 'float', true], ['canal', 'enum', false], ['activo', 'bool', true],
    ]);
    assert.equal(c.fields[0].desc, 'identificador');
    assert.equal(c.fields[0].unique, true);
    assert.deepEqual([c.fields[1].min, c.fields[1].max], [1, 5]);
    assert.deepEqual([c.fields[5].min, c.fields[5].max], [1, 4]);
    assert.deepEqual(c.fields[7].item_values, ['bajo', 'alto']);
    assert.equal(c.fields[11].default, true);

    const nullable = new Set(['horas']);
    // Datos que Zod acepta: el contrato también los acepta y el objeto decodificado pasa Zod.
    const accepted = [
      't1|3|0.5|true|abierto|a,b|1.5,2|bajo,alto|texto libre|2.5|web|false',
      't2|1|0|false|cerrado|x|||||web|',
      't3|5|1|true|pendiente|a,b,c,d|0|alto||0|web|true',
    ];
    for (const line of accepted) {
      const doc = parse(oneLine(c, line), c);
      assert.equal(doc.records.length, 1);
      const zr = Ticket.safeParse(toZodInput(doc.records[0], nullable));
      assert.ok(zr.success, `Zod rechaza ${line}: ${zr.success ? '' : zr.error.message}`);
    }
    // Datos que Zod rechaza: el contrato los rechaza con el código esperado.
    const base = {
      id: 't9', prioridad: 2, puntaje: 0.3, urgente: true, estado: 'abierto', etiquetas: ['a'], medidas: [],
      niveles: [], horas: null, canal: 'web', activo: true,
    };
    const rejected: [Record<string, unknown>, string, string][] = [
      [{ prioridad: 'alta' }, 't9|alta|0.3|true|abierto|a|||||web|true', 'E06'],
      [{ prioridad: 2.5 }, 't9|2.5|0.3|true|abierto|a|||||web|true', 'E06'],
      [{ prioridad: 9 }, 't9|9|0.3|true|abierto|a|||||web|true', 'E13'],
      [{ puntaje: 1.5 }, 't9|2|1.5|true|abierto|a|||||web|true', 'E13'],
      [{ urgente: 'quizá' }, 't9|2|0.3|quizá|abierto|a|||||web|true', 'E06'],
      [{ estado: 'resuelto' }, 't9|2|0.3|true|resuelto|a|||||web|true', 'E10'],
      [{ etiquetas: [] }, 't9|2|0.3|true|abierto||||||web|true', 'E07'],
      [{ etiquetas: ['a', 'b', 'c', 'd', 'e'] }, 't9|2|0.3|true|abierto|a,b,c,d,e|||||web|true', 'E07'],
      [{ medidas: ['x'] }, 't9|2|0.3|true|abierto|a|x||||web|true', 'E06'],
      [{ niveles: ['medio'] }, 't9|2|0.3|true|abierto|a||medio|||web|true', 'E10'],
      [{ canal: 'app' }, 't9|2|0.3|true|abierto|a|||||app|true', 'E10'],
      [{ id: undefined }, '|2|0.3|true|abierto|a|||||web|true', 'E06'],
    ];
    for (const [patch, line, code] of rejected) {
      const data = { ...base, ...patch };
      assert.equal(Ticket.safeParse(data).success, false, `Zod debería rechazar ${JSON.stringify(patch)}`);
      assert.deepEqual(codes(c, oneLine(c, line)), [code], line);
    }
    // Unicidad declarada en la conversión.
    assert.deepEqual(codes(c, `tk|n=2\nt1|1|0|false|cerrado|x|||||web|\nt1|1|0|false|cerrado|x|||||web|`), ['E11']);
  });

  test('ida y vuelta (I5) con datos que Zod acepta', () => {
    const Z = z!;
    const Producto = Z.object({
      sku: Z.string(),
      nombre: Z.string(),
      precio: Z.number().nonnegative(),
      stock: Z.number().int().nonnegative(),
      colores: Z.array(Z.string()),
      categoria: Z.enum(['hogar', 'oficina']).nullable(),
    });
    const c = assertInvariants(fromZod(Producto, { prefix: 'prod' }));
    const records = [
      { sku: 'A-1', nombre: 'Silla | ergonómica', precio: 120.5, stock: 3, colores: ['negro', 'gris, claro'], categoria: 'oficina' },
      { sku: 'A-2', nombre: 'Lámpara\ncon salto', precio: 0, stock: 0, colores: [], categoria: null },
    ];
    for (const r of records) assert.ok(Producto.safeParse(r).success);
    const obj = { header: {}, records };
    assert.equal(roundtripOk(obj, c), true);
    const back = parse(dumps(obj, c), c).records;
    for (const r of back) assert.ok(Producto.safeParse(r).success);
    // I1: cada línea es válida de forma independiente.
    for (const r of records) assert.equal(parse(`prod|n=1\n${encodeRecord(r, c)}`, c).records.length, 1);
    // Zod rechaza stock negativo y precio negativo; el contrato también.
    assert.equal(Producto.safeParse({ ...records[0], stock: -1 }).success, false);
    assert.deepEqual(codes(c, 'prod|n=1\nA-3|x|1|-1||'), ['E13']);
    assert.deepEqual(codes(c, 'prod|n=1\nA-3|x|-0.5|1||'), ['E13']);
    assert.equal(Producto.safeParse({ ...records[0], stock: 1.5 }).success, false);
    assert.deepEqual(codes(c, 'prod|n=1\nA-3|x|1|1.5||'), ['E06']);
  });

  test('lista de registros z.array(z.object(...)) y conversor inyectado', () => {
    const Z = z!;
    const Fila = Z.object({ k: Z.string(), v: Z.number().int().positive() });
    const json = fromZod(Z.array(Fila), { prefix: 'kv', toJSONSchema: Z.toJSONSchema as never });
    const c = assertInvariants(json);
    assert.equal(c.fields[1].min, 1);
    assert.deepEqual(codes(c, 'kv|n=1\na|0'), ['E13']);
    assert.equal(Fila.safeParse({ k: 'a', v: 0 }).success, false);
  });

  test('estructuras no representables fallan con E20 explícito', () => {
    const Z = z!;
    const cases: [string, unknown, RegExp][] = [
      ['anidado', Z.object({ a: Z.object({ b: Z.string() }) }), /nested object/],
      ['lista de objetos', Z.object({ a: Z.array(Z.object({ b: Z.string() })) }), /nested object/],
      ['lista de listas', Z.object({ a: Z.array(Z.array(Z.string())) }), /nested array/],
      ['unión', Z.object({ a: Z.union([Z.string(), Z.number()]) }), /not representable/],
      ['fecha', Z.object({ a: Z.date() }), /without a type/],
      ['enum numérico', Z.object({ a: Z.literal(3) }), /string enums/],
      ['patrón', Z.object({ a: Z.string().regex(/^x/) }), /pattern/],
      ['correo', Z.object({ a: Z.email() }), /format|pattern/],
      ['longitud', Z.object({ a: Z.string().min(3) }), /minLength/],
      ['raíz escalar', Z.string(), /root schema/],
    ];
    for (const [name, schema, re] of cases) {
      assert.throws(() => fromZod(schema as never, { prefix: 'x' }), (e: unknown) => {
        assert.ok(e instanceof MiniError, name);
        assert.equal(e.code, 'E20', name);
        assert.match(e.message, re, name);
        return true;
      });
    }
  });

  test("unsupported: 'ignore' descarta restricciones y avisa", () => {
    const Z = z!;
    const warnings: string[] = [];
    const json = fromZod(Z.object({ correo: Z.email(), nombre: Z.string().max(20) }), {
      prefix: 'u', unsupported: 'ignore', warnings,
    });
    assertInvariants(json);
    assert.ok(warnings.some(w => w.includes('correo')) && warnings.some(w => w.includes('maxLength')));
  });
});

describe('fromJsonSchema sin Zod', () => {
  test('JSON Schema escrito a mano', () => {
    const json = fromJsonSchema({
      type: 'object',
      title: 'Evento',
      properties: {
        id: { type: 'integer', exclusiveMinimum: 0 },
        tipo: { anyOf: [{ type: 'string', enum: ['alta', 'baja'] }, { type: 'null' }] },
        pesos: { type: 'array', items: { type: 'number' }, maxItems: 3 },
      },
      required: ['id', 'tipo', 'pesos'],
    }, { prefix: 'ev' });
    const c = assertInvariants(json);
    assert.equal(c.name, 'Evento');
    assert.deepEqual(c.fields.map(f => [f.name, f.type, f.optional, f.min, f.max]), [
      ['id', 'int', false, 1, null], ['tipo', 'enum', true, null, null], ['pesos', 'list', false, null, 3],
    ]);
    assert.deepEqual(parse('ev|n=1\n7||1,2', c).records, [{ id: 7, tipo: null, pesos: [1, 2] }]);
    assert.throws(() => fromJsonSchema({ type: 'object', properties: {} }, { prefix: 'ev' }), MiniError);
    assert.throws(() => fromJsonSchema({ type: 'object', properties: { a: { $ref: '#/x' } } }, { prefix: 'ev' }), /not representable/);
  });
});

describe('fromJsonSchema: tipos date y decimal (SPEC 1.1)', () => {
  test('format date y decimal se convierten con sus límites', () => {
    const json = fromJsonSchema({
      type: 'object',
      properties: {
        id: { type: 'integer' },
        fecha: { type: 'string', format: 'date', formatMinimum: '2020-01-01' },
        monto: { type: 'string', format: 'decimal', pattern: '^-?[0-9]+(\.[0-9]+)?$' },
        pagos: { type: 'array', items: { type: 'string', format: 'date' } },
      },
      required: ['id', 'fecha', 'monto', 'pagos'],
    }, { prefix: 'fac' });
    const c = assertInvariants(json);
    assert.deepEqual(c.fields.map(f => [f.name, f.type, f.min]), [
      ['id', 'int', null], ['fecha', 'date', '2020-01-01'], ['monto', 'decimal', null], ['pagos', 'list', null],
    ]);
    assert.equal(c.fields[3].item, 'date');
    const doc = parse('fac|n=1\n1|2024-02-29|10.50|2024-01-01,2024-02-01\n', c);
    assert.equal(doc.records[0].fecha, '2024-02-29');
    assert.throws(() => parse('fac|n=1\n1|2024-02-30|10.50|2024-01-01\n', c), (e: unknown) => JSON.stringify(e).includes('E06') || String(e).includes('E06'));
    assert.throws(() => parse('fac|n=1\n1|2019-12-31|1|2024-01-01\n', c), (e: unknown) => JSON.stringify(e).includes('E13') || String(e).includes('E13'));
  });
});
