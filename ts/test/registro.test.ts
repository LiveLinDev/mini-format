/* registro.test.ts — V5 (N6): Registry y roundtripOk con pruebas reales sobre disco y sobre contratos embebidos.
 * Las expectativas salen de SPEC §10 (protocolo de bifurcación) y §9 (ida y vuelta), no del código.
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { after, describe, test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { MiniError, Registry, defaultForksDir, loadContract, normalizeContract, roundtripOk } from '../src/index.ts';
import type { ContractJSON } from '../src/index.ts';
import { FORKS, REG } from './helpers.ts';

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'mini-registro-'));
after(() => fs.rmSync(TMP, { recursive: true, force: true }));

const base = (prefix: string, extra: Partial<ContractJSON> = {}): ContractJSON => ({
  prefix, records_key: 'rows', core: [{ name: 'id', type: 'str' }], ...extra,
} as ContractJSON);

function carpeta(nombre: string, contenido: string | null, bom = false): string {
  const dir = path.join(TMP, nombre);
  fs.mkdirSync(dir, { recursive: true });
  if (contenido !== null) fs.writeFileSync(path.join(dir, 'contract.json'), (bom ? '\ufeff' : '') + contenido, 'utf8');
  return dir;
}

describe('Registry en memoria', () => {
  test('from, add, get, has, size e iteración', () => {
    const r = Registry.from([base('x'), normalizeContract(base('y'))]);
    assert.equal(r.size, 2);
    assert.ok(r.has('x') && !r.has('z'));
    assert.deepEqual([...r].map(c => c.prefix), ['x', 'y']);
    assert.equal(r.add(base('z')).prefix, 'z');
    assert.equal(r.get('z').prefix, 'z');
  });
  test('un prefijo repetido o desconocido es E21', () => {
    const r = new Registry([base('x')]);
    for (const accion of [() => r.add(base('x')), () => r.get('no')]) {
      assert.throws(accion, (e: unknown) => e instanceof MiniError && e.code === 'E21');
    }
  });
  test('check: un padre desconocido es E21 y un fork correcto no da violaciones', () => {
    const huerfano = new Registry([base('h', { parent: 'nadie' } as Partial<ContractJSON>)]);
    const errs = huerfano.check();
    assert.deepEqual(errs.map(e => e.code), ['E21']);
    assert.ok(errs[0].message.includes("unknown parent 'nadie'"));
    assert.deepEqual(REG.check(), []);
  });
  test('linaje: hijo, padre y ciclo', () => {
    assert.deepEqual(REG.lineage('q'), ['q', 'a']);
    assert.deepEqual(REG.lineage('a'), ['a']);
    const ciclo = new Registry([base('p', { parent: 'q' } as Partial<ContractJSON>), base('q', { parent: 'p' } as Partial<ContractJSON>)]);
    assert.throws(() => ciclo.lineage('p'), (e: unknown) => e instanceof MiniError && e.message.includes('cyclic lineage'));
  });
  test('toIndex describe cada familia', () => {
    const idx = REG.toIndex();
    assert.equal(idx.length, 14);
    const q = idx.find(e => e.prefix === 'q');
    assert.ok(q && q.parent === 'a' && q.extensions === 3 && q.signature.length > 20);
  });
});

describe('Registry desde disco', () => {
  test('load del directorio de familias del repositorio: catorce, en orden alfabético de carpeta', () => {
    const r = Registry.load(FORKS);
    assert.equal(r.size, 14);
    assert.deepEqual([...r.paths.keys()], [...r.paths.keys()].sort());
    assert.equal(r.paths.get('a'), path.join(path.resolve(FORKS), 'a'));
    assert.equal(Registry.load().size, 14, 'sin argumento usa las familias del repositorio');
    assert.ok(defaultForksDir().replace(/\\/g, '/').endsWith('/forks/'));
  });
  test('una carpeta sin contract.json se omite y un contract.json con BOM se lee', () => {
    const dir = path.join(TMP, 'a-medida');
    fs.mkdirSync(dir);
    carpeta('a-medida/vacia', null);
    carpeta('a-medida/conbom', JSON.stringify(base('conbom')), true);
    const r = Registry.load(dir);
    assert.deepEqual([...r].map(c => c.prefix), ['conbom']);
    assert.equal(loadContract(path.join(dir, 'conbom', 'contract.json')).prefix, 'conbom');
  });
  test('la carpeta debe llamarse como el prefijo (E21)', () => {
    const dir = path.join(TMP, 'nombre-mal');
    fs.mkdirSync(dir);
    carpeta('nombre-mal/carpeta', JSON.stringify(base('otro')));
    assert.throws(() => Registry.load(dir), (e: unknown) => e instanceof MiniError && e.code === 'E21' && e.message.includes("must be named after prefix 'otro'"));
  });
  test('un prefijo registrado dos veces es E21', () => {
    const dir = path.join(TMP, 'doble');
    fs.mkdirSync(dir);
    carpeta('doble/uno', JSON.stringify(base('uno')));
    carpeta('doble/zdos', JSON.stringify(base('uno')));
    assert.throws(() => Registry.load(dir), (e: unknown) => e instanceof MiniError && e.message.includes('registered twice'));
  });
  test('sin process.getBuiltinModule (navegador) cargar de disco dice que requiere Node', () => {
    const proc = process as unknown as { getBuiltinModule?: unknown };
    const original = proc.getBuiltinModule;
    proc.getBuiltinModule = undefined;
    try {
      assert.throws(() => Registry.load(FORKS), /requires Node\.js/);
      assert.throws(() => loadContract(path.join(FORKS, 'a', 'contract.json')), /requires Node\.js/);
    } finally {
      proc.getBuiltinModule = original;
    }
    assert.equal(Registry.load(FORKS).size, 14);
  });
});

describe('roundtripOk (SPEC §9)', () => {
  const C = base('rt', {
    core: [{ name: 'id', type: 'str' }],
    extensions: [{ name: 'tags', type: 'list', item: 'str' }, { name: 'pick', type: 'mlist', item: 'str', marker: 'exactly_one', json: { items: 'opts', selected: 'ok' } },
      { name: 'note', type: 'str' }],
  } as Partial<ContractJSON>);
  test('objeto sin cabecera ni campos de extensión: se completan con null', () => {
    assert.equal(roundtripOk({ prefix: 'rt', rows: [{ id: 'a' }, { id: 'b', tags: ['x'] }] }, C), true);
  });
  test('los registros pueden venir bajo la clave genérica "records"', () => {
    assert.equal(roundtripOk({ prefix: 'rt', records: [{ id: 'a', note: 'n' }] }, C), true);
  });
  test('cabecera explícita con v y lista marcada presente', () => {
    const obj = { prefix: 'rt', header: { v: 1 }, rows: [{ id: 'a', tags: [], opts: ['x', 'y'], ok: 1, note: 'n' }] };
    assert.equal(roundtripOk(obj, C), false, 'una lista opcional vacía vuelve como null: no es un objeto canónico (SPEC §6)');
    assert.equal(roundtripOk({ prefix: 'rt', header: { v: 1 }, rows: [{ id: 'a', opts: ['x', 'y'], ok: 1, note: 'n' }] }, C), true);
  });
  test('una selección que no es un índice lanza E08 con la línea del registro', () => {
    assert.throws(() => roundtripOk({ prefix: 'rt', rows: [{ id: 'a', opts: ['x'], ok: 'z' }] }, C), (e: unknown) => e instanceof MiniError && e.code === 'E08' && e.line === 2);
  });
});
