/* cortes.test.ts — V5 (b): streaming con cortes de bytes en CADA frontera (createReader de ts/src y de js/mini.js).
 *
 * Cada documento se entrega en dos trozos de bytes UTF-8, b[:k] y b[k:], para todo k entre 0 y len(b): incluye
 * el corte en mitad de un carácter multibyte (2, 3 y 4 bytes), en mitad de una secuencia de escape, entre CR y
 * LF y dentro del BOM. El resultado debe ser idéntico al de parsear el texto entero en modo tolerante (objeto
 * canónico, errores con línea, diagnósticos) y los registros emitidos por push() más `finalRecords` deben ser
 * exactamente los registros válidos, en orden. Equivale a tests/test_nucleo_cortes.py para la referencia Python.
 * Base: fixtures valid/escaping/bad_* de las 14 familias, casos strict/lenient de la conformidad y documentos propios.
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { createReader, normalizeContract, parse } from '../src/index.ts';
import type { Contract } from '../src/index.ts';
import { ALL, ROOT } from './helpers.ts';

const require = createRequire(import.meta.url);

/** Superficie común de ts/src y del bundle js/mini.js que usa esta prueba. */
interface Motor {
  nombre: string;
  parse: (text: string, c: unknown, o: { strict: boolean }) => any;
  createReader: (c: unknown, o?: object) => any;
  normalize: (c: unknown) => any;
}

const MOTORES: Motor[] = [
  { nombre: 'ts/src', parse, createReader: createReader as Motor['createReader'], normalize: normalizeContract },
  (() => {
    const M = require(path.join(ROOT, 'js', 'mini.js'));
    return { nombre: 'js/mini.js', parse: M.parse, createReader: M.createReader, normalize: M.normalizeContract };
  })(),
];

interface Doc { etiqueta: string; texto: string; contrato: object }

function base(): Doc[] {
  const docs: Doc[] = [];
  const vistos = new Set<string>();
  const add = (etiqueta: string, texto: string, contrato: object, clave: string): void => {
    const k = clave + '\u0000' + texto;
    if (vistos.has(k)) return;
    vistos.add(k);
    docs.push({ etiqueta, texto, contrato });
  };
  for (const fx of ALL) {
    const c = fx.contract as unknown as { prefix: string };
    const cj = JSON.parse(fs.readFileSync(path.join(fx.dir, '..', 'contract.json'), 'utf8'));
    add(`${c.prefix}/valid`, fx.valid, cj, c.prefix);
    if (fx.escaping !== null) add(`${c.prefix}/escaping`, fx.escaping, cj, c.prefix);
    for (const b of fx.bad) add(`${c.prefix}/${b.name}`, b.text, cj, c.prefix);
  }
  const dir = path.join(ROOT, 'conformance', 'cases');
  for (const f of fs.readdirSync(dir).filter(x => x.endsWith('.json')).sort()) {
    for (const caso of JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8')).cases) {
      if (caso.mode !== 'strict' && caso.mode !== 'lenient') continue;
      const cj = caso.contract ?? JSON.parse(fs.readFileSync(path.join(ROOT, 'forks', caso.family, 'contract.json'), 'utf8'));
      add(`caso/${caso.id}`, caso.input, cj, caso.family ?? JSON.stringify(caso.contract));
    }
  }
  const cls = JSON.parse(fs.readFileSync(path.join(ROOT, 'forks', 'cls', 'contract.json'), 'utf8'));
  const cola = '|question*,feedback,bug,request,praise,other|0.9|';
  const propios = [
    'cls|n=2|k=6\r\nm1|ñandú € \u{1F600} e\u0301' + cola + 'nota\\npartida\\\\fin\r\nm2|\\|barra y \\, coma' + cola.replace('*,', ',').replace('praise,', 'praise*,') + '',
    '\ufeffcls|n=1|k=6\nm1|texto' + cola + '\\',
    'cls|n=1|k=6\nm1|\u{1F600}\u{1F600}' + cola.replace('0.9', 'x'),
    'cls|n=3\n\n   \nm1|a' + cola + '\n',
  ];
  propios.forEach((t, i) => add(`propio/${i}`, t, cls, 'cls'));
  return docs;
}

const DOCS = base();
const enc = new TextEncoder();
const COMPLETO = process.env.MINI_CORTES_COMPLETO === '1';
const LIMITE_COMPLETO = 300;
const VECINDAD = 3;

/** Posiciones de corte: todas en los documentos pequeños; en los grandes, las zonas críticas (principio, final, cerca de
 *  LF, CR o barra invertida y por dentro de los caracteres multibyte; el resto de los multibyte, muestreado).
 *  MINI_CORTES_COMPLETO=1 corta en absolutamente todas las posiciones de todos los documentos. */
function posiciones(bytes: Uint8Array): number[] {
  const n = bytes.length;
  if (COMPLETO || n <= LIMITE_COMPLETO) return Array.from({ length: n + 1 }, (_, k) => k);
  const criticas = new Set<number>();
  for (let k = 0; k <= Math.min(n, 64); k++) criticas.add(k);
  for (let k = 0; k <= Math.min(n, 16); k++) criticas.add(n - k);
  let multibyte = 0;
  for (let i = 0; i < n;) {
    const b = bytes[i];
    if (b >= 0xc0) {
      const largo = b < 0xe0 ? 2 : b < 0xf0 ? 3 : 4;
      multibyte++;
      if (multibyte <= 20 || multibyte % 7 === 0) for (let k = i; k <= Math.min(n, i + largo); k++) criticas.add(k);
      i += largo;
      continue;
    }
    if (b === 0x0a || b === 0x0d || b === 0x5c) for (let k = Math.max(0, i - VECINDAD); k <= Math.min(n, i + VECINDAD); k++) criticas.add(k);
    i++;
  }
  return [...criticas].sort((x, y) => x - y);
}

function vista(doc: any) {
  return {
    canonico: doc.canonical(),
    errores: doc.errors.map((e: any) => [e.code, e.line, e.field, e.message]),
    diagnostico: doc.diagnostics(),
  };
}

describe('V5 (b): cortes de bytes en cada frontera', () => {
  for (const m of MOTORES) {
    test(`${m.nombre}: todo corte equivale a parsear el texto entero`, () => {
      let cortes = 0;
      const normalizados = new Map<object, Contract>();
      for (const d of DOCS) {
        if (!normalizados.has(d.contrato)) normalizados.set(d.contrato, m.normalize(d.contrato));
        const c = normalizados.get(d.contrato) as Contract;
        const esperado = vista(m.parse(d.texto, c, { strict: false }));
        const validos = esperado.canonico[(c as any).records_key];
        const bytes = enc.encode(d.texto);
        for (const k of posiciones(bytes)) {
          const lector = m.createReader(c);
          const emitidos = [...lector.push(bytes.subarray(0, k)), ...lector.push(bytes.subarray(k))];
          const res = lector.end();
          emitidos.push(...res.finalRecords);
          cortes++;
          const obtenido = vista(res.document);
          if (JSON.stringify(obtenido) !== JSON.stringify(esperado)) {
            assert.fail(`${m.nombre} ${d.etiqueta}: el corte en el byte ${k}/${bytes.length} difiere de parse\n` +
              `  esperado: ${JSON.stringify(esperado).slice(0, 300)}\n  obtenido: ${JSON.stringify(obtenido).slice(0, 300)}`);
          }
          assert.deepEqual(emitidos.map((r: any) => r.record), validos, `${m.nombre} ${d.etiqueta}: registros emitidos en el corte ${k}`);
        }
      }
      assert.ok(DOCS.length > 250 && cortes > (COMPLETO ? 100000 : 15000), `${DOCS.length} documentos, ${cortes} cortes`);
    });
  }

  test('byte a byte y en tres trozos sobre los documentos propios', () => {
    for (const m of MOTORES) {
      for (const d of DOCS.filter(x => x.etiqueta.startsWith('propio/'))) {
        const c = m.normalize(d.contrato);
        const esperado = vista(m.parse(d.texto, c, { strict: false }));
        const bytes = enc.encode(d.texto);
        const solos = m.createReader(c);
        for (let i = 0; i < bytes.length; i++) solos.push(bytes.subarray(i, i + 1));
        assert.deepEqual(vista(solos.end().document), esperado, `${m.nombre} ${d.etiqueta} byte a byte`);
        for (let a = 0; a <= bytes.length; a += 3) {
          for (let b = a; b <= bytes.length; b += 5) {
            const r = m.createReader(c);
            r.push(bytes.subarray(0, a)); r.push(bytes.subarray(a, b)); r.push(bytes.subarray(b));
            assert.deepEqual(vista(r.end().document), esperado, `${m.nombre} ${d.etiqueta} cortes ${a},${b}`);
          }
        }
      }
    }
  });
});
